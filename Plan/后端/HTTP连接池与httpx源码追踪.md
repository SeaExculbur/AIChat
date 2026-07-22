# HTTP 连接池与 httpx 源码追踪

> 项目：AIChat v1.0  
> 日期：2026-07-20  
> 覆盖：Python 连接池机制、httpx 源码链追踪、线程安全与锁、对象生命周期  

---

## 一、为什么需要连接池——每次请求 rebuild TCP 的代价

你去年写的 socket 代码每条请求都新建 + 销毁 TCP 连接：

```python
# 每条请求一整套三件套
s = socket.socket()             # ① 创建 socket
s.connect(('api.deepseek.com', 443))  # ② TCP 三次握手 + TLS 握手
s.send(request_bytes)           # ③ 发送 HTTP 报文
s.recv(response_bytes)          # ④ 接收 HTTP 响应
s.close()                       # ⑤ 关闭连接——TCP 四次挥手
```

每次请求要 1-2 次往返（TCP + TLS 握手）。连接池的做法：建好的连接用完后不关，放回池子里；下次借走直接复用，省了握手。

## 二、连接池怎么实现——加锁的列表

```
连接池（Python 对象，httpx 底层 httpcore.ConnectionPool 类）
┌─────────────────────────────┐
│ connections: [   ← 一个 Python list                │
│   socket(fd=15),  ← 文件描述符 15——空闲 TCP 连接       │
│   socket(fd=16),  ← 文件描述符 16——空闲 TCP 连接       │
│ ]                           │
│ lock: threading.Lock()      ← 保证多线程安全           │
│ max_connections: 100        ← 池子总上限——来自 httpx._config.Limits   │
│ max_keepalive_connections: 20 ← 最多保留 20 条空闲连接          │
└─────────────────────────────┘
```

不是线程池——是 socket 文件描述符池。一个 socket 就是一个整数（操作系统分配的文件描述符号），和线程无关。连接池只存 fd，不创建线程。

### 借的流程

```python
def borrow(pool):
    with pool.lock:                            # ① 拿锁——其它线程别动
        if pool.connections:                   # ② 有空闲连接？
            conn = pool.connections.pop()      # ③ 取出一个
            if conn.is_alive():                # ④ 还活着吗？
                return conn                     # ⑤ 借走——省了 TCP + TLS 握手
            # 死的就继续循环
        # 池子空 → 新建 socket → connect() → TLS 握手 → 返回
        return 新建连接()
```

### 还的流程

```python
def release(pool, conn):
    with pool.lock:                                     # ① 拿锁
        if len(pool.connections) < pool.max_keepalive_connections:  # ② 还有空闲槽位？
            pool.connections.append(conn)               # ③ 放回列表——下次借
        else:
            conn.close()                                # ④ 空闲槽位满了——直接关掉
```

### 池子默认值——httpx 源码证据

```python
# httpx/_config.py 第 247 行
DEFAULT_LIMITS = Limits(max_connections=100, max_keepalive_connections=20)
```

全程操作就三样：`list.pop()`、`list.append()`、`threading.Lock()`。不是黑箱——是标准库的基本数据结构。

---

## 三、为什么需要锁——数据竞争

`list.pop()` 不是一步完成——Python 拆成了多条 CPU 指令：

```python
# 你写的：
conn = pool.connections.pop()

# Python 内部：
① len = 列表当前长度          # 读指令
② item = 列表[len - 1]        # 读指令
③ 列表长度 = len - 1          # 写指令
```

两个线程同时 pop，CPU 穿插执行：

```
线程 1：① len = 2           ← 读：列表长度 2
线程 2：① len = 2           ← 也读：列表长度 2
线程 1：② 取 socket_A       ← 拿了最后一个
线程 2：② 取 socket_A       ← 也拿了同一个
线程 1：③ 长度 = 1          ← 写回
线程 2：③ 长度 = 1          ← 也写回（都按 len=2 减 1）
```

同一个 socket 被借走两次 → 两个请求同时往同一个 TCP 连接上写数据 → 字节交错乱码。`with lock` 强制串行——一个人做完三个步骤，下一个人才拿锁。

---

## 四、对象生命周期——函数内 vs 模块顶层

### 放在函数里（原代码：每次 new OpenAI）

```
请求 A：new OpenAI() → 创建空池子 → 建 socket ① → 用完 → chat() 返回 → 池子引用归零 → Python 回收 → socket ① 关闭
请求 B：new OpenAI() → 创建空池子 → 建 socket ② → 用完 → chat() 返回 → 池子引用归零 → Python 回收 → socket ② 关闭

每次从零开始建连接，从未有机会复用上一次的那条 socket。
```

### 放在模块顶层（优化后：全局单例）

```
请求 A：池子空 → 建 socket ① → 用完 → 还回池（池现在有 1 条空闲）
请求 B：池子拿 socket ① → 用完 → 还回（池还是 1 条）
请求 C 同时到达 → 池子空 → 建 socket ② → 用完 → 还回（池现在有 2 条）

池子和 Flask 进程同寿——四条请求后的空闲连接被后续请求复用，不新建。
```

### 和 `db = SQLAlchemy()` 的类比

`db` 是模块级单例——不在每次请求里创建。连接池同理——一次创建，全局复用。

---

## 五、源码追踪链

从你的代码调用开始，一步一步追到底层配置：

```
chat.py: client.chat.completions.create(...)
  → openai._client.py: self._send_with_auth_retry(request)
  → httpx._client.py: self._send_handling_auth(request)
  → httpx._client.py: self._transport.handle_request(request)
  → httpx._transports/default.py:
      - 初始化时创建 httpcore.ConnectionPool(ssl_context, max_connections=...)
      - 每次请求调 pool.request() → 内部借还连接
  → httpx._config.py:
      - DEFAULT_LIMITS = Limits(max_connections=100, max_keepalive_connections=20)
```

不是黑盒——每层都是可读的纯 Python 文件。

---

## 六、其他速记

| 知识点 | 一句话 | 用途 |
|--------|--------|------|
| `list.pop()` 非原子性 | Python 的一条 `pop()` 被 CPU 拆成多条指令——多线程穿插执行会导致数据竞争 | 为什么需要锁 |
| `threading.Lock()` | 一次只让一个线程进入被保护区域 | 连接池借还的互斥保护 |
| 文件描述符 vs 线程 | `socket(fd=15)` 是一个整数——操作系统分配的文件标识符，不是线程 | 连接池不创建线程 |
| `max_keepalive_connections` | 用完的空闲连接最多保留 20 条——超出就关闭 | 防止冗余空闲连接占系统资源 |
| `keepalive_expiry` | 空闲连接多久没用则关闭（默认 5 秒左右——具体看 httpx 版本） | 防止半天不用旧连接还赖在池子里 |
| `CACHE_NAME` vs 连接池 | 同一种模式：把用过的东西留下来，下次复用——缓存是 HTTP 响应缓存，连接池是 TCP socket 复用 | 两个时间尺度上的复用——秒级复用和分钟级复用 |
| `httpcore` vs `httpx` | httpcore 是 httpx 的底层引擎——管理连接池和 TLS 临时证书，httpx 是最外层的用户 API | 库的一层设计——分开借还逻辑和 API 入口 |
