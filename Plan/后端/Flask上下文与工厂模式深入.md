# Flask 上下文与工厂模式 — 源码级深入

> 项目：AIChat v1.0  
> 日期：2026-07-06  
> 内容：工厂模式原理 → AppContext 源码分析 → 栈 vs 队列 → 线程安全  

---

## 一、工厂模式深入

### 为什么用 `create_app()` 而不是直接 `app = Flask(__name__)`

#### 问题 1：循环引用

假设没有工厂函数，`app` 写在全局：

```python
# app.py
from flask import Flask
from auth import auth_bp      # ← 第 2 行：导入时跳进 auth.py

app = Flask(__name__)          # ← 第 4 行：app 在这里才创建
app.register_blueprint(auth_bp)
```

```python
# auth.py
from app import app            # ← 需要 app 对象

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/register")
def register():
    token_expiry = app.config["JWT_ACCESS_TOKEN_EXPIRES"]   # 读配置
```

执行流程：

```
Python 读 app.py
  第 2 行：from auth import auth_bp → 跳进 auth.py

Python 跳进 auth.py
  第 1 行：from app import app → 跳回 app.py

Python 跳回 app.py
  Python 发现 app.py 已在导入中（sys.modules 里有半成品）
  → 从半成品里找 "app" 这个名字
  → app.py 才执行到第 2 行，app 变量在第 4 行还没定义
  → ImportError
```

**根因**：`app` 还没创建就被 `auth.py` 引用了。

#### 问题 2：测试隔离

直接创建时，全局只有一个 `app` 对象。两个测试文件导入的是同一个 `app`——测试 A 注册的用户残留在数据库，测试 B 的用户名查重直接报错。

### 工厂函数的保护机制

```python
def create_app():
    app = Flask(__name__)           # ① 先建 app
    from auth import auth_bp         # ② 再导入——app 已存在
    app.register_blueprint(auth_bp)  # ③ 再注册
    return app
```

`from auth import auth_bp` 在**函数体内部**——不调用 `create_app()` 就不会执行。保护来自**函数推迟了 import 的执行时机**。

**比较三种写法**：

| | 导入时执行 | 循环引用风险 |
|------|---------|------------|
| 写在模块顶层 | 立刻 | 有 |
| 写在类体里 | 立刻 | 有——和模块顶层一样 |
| 写在函数体里 | 调用时才执行 | 无 |

保护不是来自类封装——是来自**函数把代码推迟到了被调用的那一刻**。

### 工厂的一切：每次调用返回独立实例

| 层 | 工厂 | 每次产出 |
|------|------|------|
| Flask 应用 | `create_app()` | 全新的 Flask 实例 |
| 上下文 | `app.app_context()` | 全新的 AppContext 实例 |
| 用户数据 | `User(username="张三")` | 全新的 User 实例 |

同一模式跨了三层：**消灭全局变量，每个实例独立持有自己的状态**。并发时多个请求不会互相踩踏全局 app 的属性，测试时多个 test 各自有独立的数据库。

---

## 二、AppContext 源码分析

### `app.app_context()` 实际做了什么

```python
# flask/ctx.py — 源码级等价
app.app_context()           # 实际等价于
return AppContext(self)      # 把 app 自身传给 AppContext 的 __init__
```

### `__init__` 构造

```python
class AppContext:
    def __init__(self, app: Flask) -> None:
        self.app = app                                    # 记住"我是谁的上下文"
        self.url_adapter = app.create_url_adapter(None)   # URL 适配器
        self.g: _AppCtxGlobals = app.app_ctx_globals_class()  # 临时存储
        self._cv_tokens: list[contextvars.Token] = []     # ← 这就是"栈"
```

| 属性 | 干什么 |
|------|--------|
| `self.app` | 引用对应的 Flask 应用对象 |
| `self._cv_tokens` | Python list——记录每次 push 的 token（即"栈"） |
| `self.g` | 请求级临时存储（Flask 的 `g` 对象） |

### `push` — 压栈

```python
def push(self) -> None:
    self._cv_tokens.append(_cv_app.set(self))
```

`_cv_app` 是一个 `ContextVar`——Python 3.7+ 的线程安全变量。`.set(self)` 把当前 AppContext 设为活跃上下文，返回一个 token。`.append(token)` 把 token 存入 `_cv_tokens` 列表。

### `pop` — 弹栈

```python
def pop(self, exc: BaseException | None = _sentinel) -> None:
    ctx = _cv_app.get()                           # 取当前活跃上下文
    _cv_app.reset(self._cv_tokens.pop())          # 弹出最后一个 token，用它的旧值恢复
    if ctx is not self:                           # 安全检查
        raise AssertionError(...)                 # 弹错人了——直接报错
```

### `__enter__` / `__exit__` — with 语句

```python
def __enter__(self) -> AppContext:
    self.push()
    return self

def __exit__(self, exc_type, exc_value, tb) -> None:
    self.pop(exc_value)
```

`with app.app_context()` → `__enter__` 调 `push` → 块内执行 → `__exit__` 调 `pop`。即使在块内抛异常，`__exit__` 仍然执行——`pop` 保证发生。

### 栈不是 C 调用栈

Flask 内部的"栈"就是一个 Python `list`——`push` = `list.append()`，`pop` = `list.pop()`。和 CPU 硬件调用栈没有关系，只是借用了"栈"这个名词。

---

## 三、为什么是栈而不是队列

### 场景：嵌套 with

```python
with app_a.app_context():          # push app_a → 栈顶 = app_a
    with app_b.app_context():      # push app_b → 栈顶 = app_b
        db.create_all()            # 活跃 = 栈顶 = app_b ✅
    # app_b 的 __exit__ → pop → 栈顶恢复为 app_a ✅
```

**栈**：后进先出——内层上下文覆盖外层，退出后外层自动恢复。嵌套天然支持。

**队列**：先进先出——内层 app_b 被压入后，谁当活跃？

| 队中策略 | 后果 |
|------|------|
| 活跃 = 队头（app_a） | `db.create_all()` 建到 app_a——但你在 app_b 的 with 块里 |
| 活跃 = 队尾（app_b） | 你选了最近加入的——这就是栈——只是改名 |

**栈是"临时切换当前状态、用完恢复旧值"这个需求的唯一正确形状**。队列适合排队等资源的场景，不适合临时覆盖。

---

## 四、为什么包一层 AppContext 而不是直接压入 app

### 如果直接压 app

```python
# 假设 Flask 这样设计（不包装）
_app_stack = []

def push_app(app):
    _app_stack.append(app)
```

**问题 1**：token 没地方存。每次 push 需要 token 来在 pop 时恢复旧值——这些 token 不能挂在 `app` 上（线程共享），也不能挂在全局变量上（多线程覆盖）。

**问题 2**：app 的生命周期 ≠ 上下文的生命周期。`app` 对象从启动到关闭只存在一次，但 `AppContext` 每次 `with` 都新建一个。栈状态是临时的，不应该污染 app 本身。

### 比较：装饰器 vs AppContext

| | 装饰器 | AppContext |
|------|------|------|
| 包谁 | 函数 | app 对象 |
| 外套叫什么 | 闭包 | AppContext 实例 |
| 外套寿命 | 永久——函数被替换 | 临时——`with` 退出就扔 |
| 会不会污染原件 | 不——闭包在外面 | 不——app 只是被引用 |

同一模式，不同使用周期——都是给原件套一层外套，不修改原件的完整内容。

---

## 五、线程安全：ContextVar

### 为什么不能用普通全局变量

```python
current_app = None   # 全局变量，所有线程共享

# 线程 A 设置        # 线程 B 设置
current_app = app_a   current_app = app_b
# A 读到的是 B 刚写的 app_b——数据污染
```

### ContextVar 怎么做到的

```python
_cv_app: ContextVar[AppContext] = ContextVar("flask.app_ctx")
```

操作系统为每个线程维护了独立的变量拷贝。**名字是全局同一个，底层存储是分开的：**

```
线程 1 调用 _cv_app.set(app_a)
    → OS 在线程 1 的专属存储区写：{_cv_app: app_a}
    → 线程 2 完全看不到

线程 2 调用 _cv_app.set(app_b)
    → OS 在线程 2 的专属存储区写：{_cv_app: app_b}
    → 线程 1 完全看不到
```

这就是为什么两个请求同时到达时，各自读自己的 `request.get_json()`，互不串数据。不是 Flask 自己实现了线程隔离——是 Python 3.7 的 `contextvars` 标准库在底层做了这件事。

---

## 六、工厂模式的全景

```
同一个进程里：
  create_app()          → N 个测试各有独立的 Flask 实例
  app.app_context()     → N 个请求各有独立的 AppContext 实例
  User(username="...")  → N 个用户各有独立的 User 实例

共同目标：消灭全局变量，每个实例独立持有自己的状态
```

| 要避免的问题 | 解决方案 |
|------------|---------|
| 循环引用 | 工厂函数把 import 推迟到调用时 |
| 测试隔离 | 工厂函数每次返回全新实例 |
| 线程串数据 | ContextVar 线程隔离 |
| 嵌套上下文顺序混乱 | 栈（后进先出） |
| pop 弹错上下文 | `is not self` 安全检查 |
| 退出时忘记清理 | `with` 保证 `__exit__` 必然执行 |

---

## 十、生成器与上下文——SSE 流式通信的时序缺陷

### 问题

SSE 流式接口中，`generate()` 生成器在 `return Response(generate())` 之后的 Werkzeug 发送阶段才被迭代。此时 `chat()` 已返回，Flask 自动销毁了请求上下文。生成器内部调用 `db.session.commit()` 时找不到应用上下文 → `RuntimeError: Working outside of application context`。

### 根因

```
① chat() 调用 return Response(generate()) → Response 包装了生成器的迭代器引用
② chat() 返回 → Flask 清理应用上下文（pop）
③ 数毫秒后 Werkzeug 开始发送 HTTP 响应 → 遍历 Response 的迭代器
④ 生成器终于开始执行 → for 循环 yield 打字 ✅
⑤ 准备 db.session.commit() → db 查询当前活跃上下文 → ❌ 上下文在步骤② 已出栈
```

为什么 `db` 对象在闭包里但上下文不在：`db` 是显式赋值给变量的 Python 对象（闭包自动捕获），而 Flask 应用上下文是 `ContextVar` 维护的隐式标记位——闭包不自动捕获它。

### 解法：手动抓 app 进闭包 + with app.app_context()

```python
def chat():
    ...
    app = current_app._get_current_object()   # 在上下文销毁前抓取 app 对象引用

    def generate():
        ...
        with app.app_context():               # 生成器内部手动临时建立上下文
            db.session.add(ai_message)
            db.session.commit()
```

`app` 被闭包显式捕获取——生成器在任何时候调用它都能独立创建临时上下文。`with app.app_context()` 是 push/pop 的语法糖，退出时自动清理。

### 和 create_app 里 with app.app_context() 的对比

`create_app()` 里的 `with app.app_context(): db.create_all()` 也是手动建上下文——应用启动时没有请求，Flask 不会自动创建上下文。和生成器内部的 `with app.app_context()` 是同一机制——**在没有自动上下文的时机手动临时建立。**

---

## 十一、Python 异常层级与 GeneratorExit

### 问题

`except:`（裸 except）捕获一切异常，包括 `GeneratorExit`、`KeyboardInterrupt`、`SystemExit`。生成器在销毁时 Python 向其中抛出 `GeneratorExit` 来清理它——裸 `except:` 捕获了这个信号，生成器以为自己不会被关，继续往下跑。但其后的代码无法再被正确执行——生成器的生命周期被强行中断。

### 根因

```
BaseException
├── GeneratorExit          ← 生成器被销毁时 Python 内部抛出。不应被捕获
├── KeyboardInterrupt      ← Ctrl+C。不应被捕获
├── SystemExit             ← sys.exit()。不应被捕获
└── Exception              ← 99% 的日常异常
    ├── ValueError、TypeError、KeyError ...
```

### 正确写法

```python
# ❌ 裸 except——吃到不该吃的信号
except:
    ...

# ✅ except Exception——放过 GeneratorExit 等系统级异常
except Exception:
    ...
```

### 在 SSE 生成器中的影响

裸 `except:` 在 `for chunk in response:` 循环中吃到 `GeneratorExit` → 执行了 `yield "[ERROR]"` 之后再被 Python 强行销毁 → `for` 循环之后的 commit 代码永远执行不到 → AI 消息一条没存进数据库。

---

## 七、Flask.__call__ — WSGI 入口源码

```python
# flask/app.py — Flask 应用实例能被调用的唯一原因
def __call__(self, environ, start_response):
    return self.wsgi_app(environ, start_response)
```

**在通信链路中的位置**：

```
Werkzeug 解析 HTTP → 生成 environ → 调 app(environ, start_response)
                                          ↓
                                    Flask.__call__
                                          ↓
                                    wsgi_app()
                                          ↓
                              路由匹配 → 你的 register()
```

`start_response` 是 Werkzeug 传进来的回调——Flask 在构建 HTTP 响应头后调用它，服务器拿到后立刻在 TCP 连接上发送响应头。你之前学的"元数据和数据分两路返回"的证据就在这一行源码里。

---

## 八、完整链路：从 curl 到 ContextVar

### ① curl 发请求 → TCP 连接

```bash
curl -X POST http://localhost:5000/api/auth/register ...
```

三次握手 → TCP 连接建立 → HTTP 报文通过通道发送。

### ② Werkzeug 收到连接

```python
while True:
    client_socket, addr = server_socket.accept()   # 收到新 TCP 连接
```

### ③ 分配线程

```python
    t = threading.Thread(target=handle_request, args=(client_socket,))
    t.start()                                       # 创建新线程，OS 分配独立存储区
```

线程池优化：Werkzeug 从线程池取空闲线程，没有才新建。请求处理完归还池子，不加底层层新建开销。

### ④ 线程内：解析 HTTP → environ

```python
def handle_request(client_socket):
    raw_http = client_socket.recv(4096)
    environ = {
        "REQUEST_METHOD": "POST",
        "PATH_INFO": "/api/auth/register",
        "wsgi.input": BytesIO(b'{"username":"test","password":"123456"}'),
        ...
    }
```

### ⑤ 调 Flask.__call__

```python
    response = app(environ, start_response)
```

### ⑥ wsgi_app 内部：创建上下文

```python
def wsgi_app(self, environ, start_response):
    ctx = self.request_context(environ)    # 创建 RequestContext
    ctx.push()                              # 压入请求栈
    self.app_context().push()              # 创建 AppContext，压入应用栈
    #                                               ↑
    #                                    这里调了 _cv_app.set(self)
    #                                    当前线程的 ContextVar 存储区写入 app_context
    try:
        response = self.full_dispatch_request()
        return response(environ, start_response)
    finally:
        ctx.pop()
```

### ⑦ 路由匹配 → 你的 register()

```python
data = request.get_json()    # request 代理 → ContextVar → 当前线程的 Request 对象
```

### ⑧ 返回 Response → 线程归还线程池

---

## 九、多线程并发策略

### 每个请求 = 一个独立线程

```
请求 A → 线程 1 → 处理 register()
请求 B → 线程 2 → 处理 chat()
请求 C → 线程 3 → 处理 login()
三个线程并行，OS 在 CPU 上轮转调度
```

### 三种并发策略

| 策略 | 代表 | 怎么并发 |
|------|------|---------|
| **多进程** | Gunicorn 多 worker | N 个独立进程，各有自己的 Python 解释器 |
| **多线程**（你） | Werkzeug 开发服务器 | N 个线程共享一个进程 |
| **异步/协程** | FastAPI、Node.js | 1 个线程在多个任务间跳转 |

### 多线程 vs 异步

| | 多线程 | 异步 |
|------|------|------|
| 怎么并发 | N 个线程同时跑 | 1 个线程在任务间切换 |
| 阻塞 | OS 挂起线程，换另一个 | 协程挂起自己，让出执行权 |
| 你的聊天接口 | `yield` 在同一线程内交替暂停/恢复——不涉及多线程 |

你的项目是**多线程 + 生成器混用**——线程负责并行（3 个请求 = 3 个线程），生成器负责流（每个线程内 `yield` 交替暂停/恢复）。
