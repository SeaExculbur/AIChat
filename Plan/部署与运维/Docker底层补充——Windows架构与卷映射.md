# Docker 底层补充——Windows 架构、Socket 共享与卷映射原理

> 项目：AIChat v1.0
> 日期：2026-07-27
> 覆盖：Docker Desktop 的 Windows 架构（WSL 2 + 9P 桥接）、Socket 的本质与完整收发过程（recv/send + 内核缓冲区 + 中断 + TCP 分包封装）、Gunicorn pre-fork 端口共享、CMD vs RUN 时机、绑定挂载 vs 命名卷、FHS 标准目录结构、HTTP 请求的 socket 全程追踪

---

## 一、Docker Desktop 在 Windows 上的真实架构

### 不是"共享 Windows NT 内核"

Linux 容器只能跑在 Linux 内核上。Docker Desktop for Windows 的做法是**背后启动一个 WSL 2 轻量虚拟机，里面运行真 Linux 内核**。

```
你的 Windows 电脑
├── Windows NT 内核（桌面、文件、WiFi）
│
└── WSL 2 轻量虚拟机
    └── Linux 内核 ← Docker 容器共享的是这个内核
        ├── Flask 容器
        └── Nginx 容器
```

Windows NT 和 Linux 是两套完全不同的内核，系统调用接口不兼容。Windows 程序调用 `CreateFileW()`，Linux 程序调用 `open()`。Docker Desktop 不能把 Linux 容器直接放到 Windows NT 上跑——必须背后跑一个 Linux 内核。

### 跨 OS 的 I/O 桥接——9P 协议

当容器进程读写挂载的宿主机文件时，两个内核都参与：

```
Flask 容器进程：write("/app/instance/aichat.db", bytes)
    │
    ▼ 系统调用，进 Linux 内核（WSL 2 内的真 Linux）
Linux 内核：文件在挂载的共享目录上 → 不能走 ext4 块设备路径
    │
    ▼ 9P 协议（文件系统共享协议）→ 通过虚拟网络转发给 Windows 端
    │
    ▼ Windows NT 内核（NTFS 驱动）→ 写磁盘扇区
宿主机磁盘 ← 数据落盘
```

一条 `write()`，两次进内核——Linux 内核收系统调用，Windows NT 内核做实际磁盘 I/O。9P 是跑在 WSL 虚拟网络上的文件共享协议，相当于 smb/nfs 的同类品。

### 卷映射的路径——两边格式不同是正常的

```yaml
volumes:
  - ./data:/app/instance
      ↑        ↑
   相对路径   绝对路径
   (Windows)  (Linux)
```

- 左边 `./data`：宿主机路径。`.` = `docker-compose.yml` 所在的目录。Windows 上实际路径为 `E:\My_project\AIChat_v1.0\data\`。
- 右边 `/app/instance`：容器内路径。容器跑 Linux，只认 Linux 路径格式（`/` 开头，正斜杠）。`/app` 是 `WORKDIR /app` 设定的，不是发行版给的。

两边路径格式不一样——各自活在各自的操作系统里，Docker Desktop 做 IO 桥接。

---

## 二、Socket 与 I/O 的核心逻辑链

### 总哲学：一切皆文件

在 Linux 中，"文件"不是狭义上的硬盘文件，而是所有 I/O 操作的统一入口。无论是读写磁盘、收发网络数据、还是键盘屏幕交互，程序都用同一套接口：`open`/`read`/`write`/`close`。程序操作的只是一个整数——文件描述符（file descriptor），它指向内核里的一个结构体。

### 总规矩：任何 I/O 都必须经过内核

用户程序无权直接碰硬件。所有 I/O 操作的本质，是程序向内核发申请，内核代劳。程序通过系统调用（如 `read`、`write`）陷入内核，内核操作硬件，再把结果复制回用户空间。这是安全和稳定的基石。也是一切皆文件成立的底层原因——文件描述符之所以统一，是因为 I/O 路径统一经过内核。

### Socket 的本质

Socket 是应用程序访问内核网络协议栈的 I/O 操作入口，也是一个文件描述符。它本身不存数据，只在内核中指向一个包含**接收缓冲区**和**发送缓冲区**的复杂结构体。数据到了→内核塞进接收缓冲区→等你来取。你要发→内核把你的数据塞进发送缓冲区→异步替你打包发出。

### 跨进程共享的秘密：fork + 文件描述符继承

这是高性能服务器（如 Gunicorn pre-fork）的理论基础：

- **Socket 对象是内核资源，不属任何进程私有。** 进程只有"访问权"（文件描述符），真正的东西在内核里。
- **fork 会复制文件描述符表**，因此子进程能继承父进程的 Socket 文件描述符，且指向**同一个内核 Socket 对象**。
- **端口只绑定在这一个内核对象上**，所以多个子进程可以共享同一端口，绝不会冲突。
- **COW（写时复制）不影响此过程**。COW 优化的是进程用户空间内存页的复制（fork 后父/子进程修改内存时触发拷贝），而 Socket 对象稳稳地位于内核空间——fork 复制的只是指向它的文件描述符，COW 不涉及内核数据结构。

### 并发模型的实现

1. 多个 Worker 子进程共享同一个监听 Socket，一起阻塞在 `accept()` 上
2. 新连接到达时，内核只唤醒**一个** Worker
3. 该 Worker 获得全新的连接 Socket，去处理业务
4. 其他 Worker 继续阻塞等待下一个连接
5. Worker 处理完业务后，关闭连接 Socket，重新回到 `accept()` 参与竞争

---

## 三、Socket 的完整收发过程

### socket 的本质

Socket 是应用程序访问内核网络协议栈的 I/O 操作入口，表现为一个整数（文件描述符）。

**对程序而言**：它是一个"遥控器编号"，代表了读写网络数据的权限和通道。你不需要懂 TCP 分段、IP 路由——只需要往这个编号里写数据、从这个编号里读数据。

**对内核而言**：它是"文件描述符表"里的一项，指向内核中一个包含发送缓冲区和接收缓冲区的复杂数据结构。Socket 本身不存数据，它只管理缓冲区。

```c
// socket 在内核里的数据结构（简化）
struct socket {
    接收缓冲区 (recv buffer)      ← 内核内存区域，TCP 栈把收到的字节暂存在这
    发送缓冲区 (send buffer)      ← 内核内存区域，待发送的字节暂存在这
    连接状态 (ESTABLISHED)        ← TCP 状态机
    四元组 (源IP:端口, 目标IP:端口) ← 唯一标识这条连接
    等待队列                      ← 等待这个 socket 的进程列表
};
```

### 数据如何流入 Socket（接收过程）——内核自动完成

程序调用 `recv()` 后休眠，后续全部由内核和硬件自动处理：

1. **网卡收包**：数据以电/光信号到达，转成二进制帧
2. **内核层层解析**：剥以太网头 → 剥 IP 头 → 剥 TCP 头（检查序列号、重排、去重）
3. **存入缓冲区**：将剥离所有头部后得到的纯应用层数据（HTTP 报文），按顺序放入 socket 的接收缓冲区队列尾部
4. **流量控制**：若缓冲区满，内核通过 TCP 窗口机制告知对方暂停发送
5. **唤醒进程**：内核检查 socket 的等待队列 → 有进程在等 → 唤醒 → 数据从内核缓冲区复制到进程内存 → `recv()` 返回

### 程序如何写入 Socket（发送数据）——程序主动发起

1. **程序调用** `send(sockfd, buf, len, 0)`
2. **系统调用**：CPU 陷入内核态，内核将 buf 中的数据复制到 socket 的发送缓冲区队列尾部
3. **立即返回**：复制完毕后 `send` 即刻返回——**此时数据并未真正发送到网络上**，只是成功递交给了内核

### 数据如何从 Socket 发出——内核异步自动完成

1. **TCP 分包**：内核查看发送缓冲区，将数据切割成符合要求大小的报文段
2. **层层封装**：为每个报文段加 TCP 头（序列号等）→ 加 IP 头 → 加 MAC 帧头
3. **网卡发出**：将封装好的包交给网卡驱动，以电或光信号发送到物理链路

**一句话**：Socket 是一个由内核管理的收发通道。数据收进来时，内核默默拆包、排队，等你来取；你要发出去时，只需把数据交给内核，它会自动封装打包，帮你运走。

### 一条 TCP 连接 = 两个 Socket，各管一端

"TCP 通道"是口语说法——物理上没有额外的实体通路。一条 TCP 连接由**两端各一个 socket + 内核 TCP 协议状态机**共同组成：

```
客户端                                服务端
──────                                ──────
sock = socket()                       listen_sock = socket() → bind(5000) → listen()
connect(sock, "flask", 5000)          conn_sock = accept(listen_sock)
    ↓                                     ↓
  sock                                  conn_sock
  (本地端口 54321)                       (本地端口 5000)
          ────── TCP 连接 ──────
```

内核通过四元组 `(源IP, 源端口, 目标IP, 目标端口)` 唯一标识这条连接。中间不需要第三个 socket——两端各一个，内核 TCP 栈在底层用序列号、重传、窗口控制把这两个 socket 的收发缓冲区串起来。

### Gunicorn pre-fork 怎么共享同一个端口

按常理，4 个独立进程不能同时绑同一个端口。解决方案——端口只绑定一次，socket 通过 fork 继承：

```
1. Master 进程：socket() → bind(5000) → listen()
2. Master fork 出 4 个 Worker
3. fork 复制整个进程内存空间，包括 socket 文件描述符
4. 4 个 Worker 各持有一个指向**同一个 socket** 的文件描述符
5. 新连接到达 → 4 个 Worker 同时 accept() 竞争 → 内核把连接交给抢到的那个
```

端口只被 bind 了一次（master 做的），4 个 worker 共享同一个监听 socket。这是 Unix 经典 pre-fork 模式——Nginx 和 Apache 也用同一套方法。

### 一条 HTTP 请求的 socket 全程追踪——从 JS `fetch()` 到 AI 回复

```
1. 浏览器 fetch('/api/chat') → 创建 socket → connect(localhost:80)
                                ↓ TCP 三次握手
2. Nginx listen socket: accept() → 新 client_socket
   Nginx 收到请求 → 发现 /api/ → 创建 upstream_socket → connect(flask:5000)
3. Gunicorn master 的 listen socket: 4 个 worker 竞争 accept()
   Worker 1 抢到 → 新 conn_socket → recv() → 拿到的就是 Nginx 转发的 HTTP 请求全文
4. Flask 业务函数处理 → 调 DeepSeek API（又创建新 socket → connect(api.deepseek.com:443)）
5. 回复原路返回：Flask → Gunicorn conn_socket → Nginx upstream_socket → Nginx client_socket → 浏览器 socket → JS 收到回复
```

**socket 从头到尾只做一件事：让两个进程把对方当成"一个可以读写字节的文件"。** 每经过一跳，新的一对 socket 被创建。TCP 协议在 socket 底层默默做 I/O 工作——但写代码的人只看到 `send()` 和 `recv()`。

---

## 四、CMD vs RUN——什么时候执行

| | `RUN` | `CMD` |
|------|------|------|
| 执行时机 | **构建时**（docker build） | **容器启动时**（docker run / compose up） |
| 典型用途 | 安装依赖（`pip install`、`npm ci`） | 启动主进程（`gunicorn ...`、`nginx ...`） |
| 可以被覆盖？ | ❌ 写在镜像层里 | ✅ compose 的 `command:` 或 `docker run` 后的参数 |

```dockerfile
RUN pip install -r requirements.txt   # 构建时执行——依赖装进镜像层
CMD ["gunicorn", "-c", "gunicorn_config.py", "app:create_app()"]  # 容器启动时执行
```

---

## 五、绑定挂载 vs 命名卷

两者都是"把宿主机存储映射进容器，删容器不丢数据"。区别在于**谁选存储路径**。

| | 绑定挂载（bind mount） | 命名卷（named volume） |
|------|------|------|
| 路径 | 你手动指定：`./data:/app/instance` | Docker 管理：`aichat_data:/app/instance` |
| 物理位置 | `E:\My_project\...\data\` | Docker 内部存储（`\\wsl$\docker-desktop-data\...`） |
| 生产环境 | 绑定宿主机路径——容器攻破可写宿主机 | Docker 隔离存储——容器不知道宿主机路径 |

---

## 六、FHS——Linux 标准目录结构

所有 Linux 发行版遵循同一套基本目录布局（FHS = Filesystem Hierarchy Standard）：

```
/              ← 根目录
├── bin/       ← 基础命令（ls、sh）
├── lib/       ← 动态链接库（libc.so）
├── usr/       ← 用户软件（python3、pip 包）
├── etc/       ← 配置文件（DNS、SSL 证书）
├── var/       ← 可变数据（日志、数据库）
├── tmp/       ← 临时文件
└── home/      ← 用户目录
```

不管 Ubuntu、Debian、Alpine——`/bin/sh`、`/lib/libc.so`、`/usr/bin/python3` 这些路径完全一致。`/app` 不是 FHS 标准——是 `WORKDIR /app` 自己创建的，应用代码放在哪由你决定。
