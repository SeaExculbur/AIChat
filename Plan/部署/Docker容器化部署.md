# Docker 容器化部署

> 项目：AIChat v1.0
> 日期：2026-07-22
> 覆盖：Docker 核心概念、镜像与容器、多阶段构建、Gunicorn、Nginx 反向代理、Docker Compose、层缓存机制、GIL 与多进程

---

## 一、为什么需要 Docker——环境差异问题

### 没它时

Gunicorn 不能在 Windows 跑 → 需要 WSL。Nginx 也不能在 Windows 跑 → 又需要 WSL。等买了学生服务器，上面是 CentOS/Ubuntu，Python 版本、系统库版本跟 WSL 里的可能不一样 → "我这能跑啊，服务器上怎么不行"。

环境差异是手工部署的核心痛点——代码一样，但操作系统、系统库、Python 版本、依赖版本各自不同。

### 有它后

Docker 把应用和它需要的整个运行环境（OS 用户空间 + 系统库 + Python + 依赖包）打包成一个镜像文件，在任何 Linux 内核上都能原样运行。

```
传统部署                          Docker 部署
──────────                        ──────────
服务器：Ubuntu 22.04              服务器：只要内核是 Linux 5.x+
  ├─ 手动装 Python 3.13             ├─ Docker Engine
  ├─ 手动装 Nginx                   │   ├─ 容器 A：Flask + Gunicorn（镜像自带 Python 3.13）
  ├─ 手动编译装各种系统库           │   ├─ 容器 B：Nginx（镜像自带 Nginx）
  ├─ pip install -r ...             │   └─ 容器 C：Vue 静态文件
  └─ "我机器上能跑啊"              └─ 新服务器：docker compose up -d → 完全一样
```

---

## 二、Docker vs 虚拟机——关键区别

```
虚拟机                              Docker 容器
────────                            ────────
┌──────────────┐                    ┌──────────────┐
│ App          │                    │ App          │
├──────────────┤                    ├──────────────┤
│ 依赖库        │                    │ 依赖库        │
├──────────────┤                    ├──────────────┤
│ 完整的 Guest OS │ ← 独立内核       │ 没有内核      │ ← 共享 Host 内核
│ (Ubuntu)      │   几 GB           │ 只有用户空间   │   几 MB
├──────────────┤                    ├──────────────┤
│ Hypervisor   │                    │ Docker Engine │
├──────────────┤                    ├──────────────┤
│ Host OS      │                    │ Host OS       │
├──────────────┤                    ├──────────────┤
│ 硬件          │                    │ 硬件          │
└──────────────┘                    └──────────────┘
```

虚拟机虚拟了整个硬件 + OS 内核，每个 VM 几 GB 起步。Docker 容器共享 Host 的内核，只隔离用户空间（文件系统、进程、网络），启动是毫秒级，镜像是 MB 级。

**为什么 Docker 能做到而 VM 不这样做**：Linux 内核本身就支持**命名空间（namespace）**隔离——进程命名空间让容器里的进程看不到容器外的进程，网络命名空间让容器有自己独立的 IP 和端口，挂载命名空间让容器有自己独立的文件系统根目录。Docker 不是发明了隔离——是把 Linux 内核已有的隔离能力打包成了一个好用的命令行工具。

---

## 三、镜像到底是什么——分层文件系统 + 元数据

### 镜像 ≠ ISO 文件

一个 Docker 镜像的物理结构是**多个只读文件系统层的叠加，每层是一组文件和目录的变更**。

```
"Layers": [
    "sha256:a1b2c3...",   ← 第 1 层: Debian 基础文件系统 (/bin, /lib, /etc...)
    "sha256:d4e5f6...",   ← 第 2 层: 装了 CA 证书
    "sha256:g7h8i9...",   ← 第 3 层: 装了 Python 3.13 解释器
    "sha256:j0k1l2..."    ← 第 4 层: 设了环境变量
]
```

每层在宿主机磁盘上就是一个**普通目录**，存在 `/var/lib/docker/overlay2/` 下。层里面就是标准的 Linux 目录树——`/bin/sh`、`/lib/libc.so.6`、`/usr/bin/python3`。

传输时是压缩包（tar.gz），下载后解压成普通目录。运行时通过 OverlayFS 合并成一个统一视图。

### 容器启动时怎么"叠"成完整文件系统

用到 OverlayFS——Linux 内核的一个堆叠文件系统，把多个目录树合并成一个虚拟的统一视图：

```
                    ┌─────────────────┐
                    │ 容器可写层 (新建/修改)  │  ← 可读写，容器删除后消失
                    ├─────────────────┤
                    │ 第 4 层 (ENV 变更)    │  ← 只读
                    ├─────────────────┤
                    │ 第 3 层 (Python 3.13) │  ← 只读
                    ├─────────────────┤
                    │ 第 2 层 (CA 证书)     │  ← 只读
                    ├─────────────────┤
                    │ 第 1 层 (Debian 基础) │  ← 只读
                    └─────────────────┘
```

容器里 `ls /usr/bin/python3` → OverlayFS 从上往下找：层 4 没有 → 层 3 有 → 返回层 3 里的文件。容器以为自己有一套完整的文件系统，实际是 OverlayFS 把多层合并成一个视图。

---

## 四、rootfs——为什么 Docker 镜像必须包含操作系统用户空间

### Python 解释器不是悬浮的——它踩在 OS 用户空间上

```
你的代码 (chat.py、auth.py)
    │ 调了 open()、import、网络请求...
    ▼
Python 解释器 (python3)
    │ 每个操作都分解成 C 函数调用
    ▼
C 运行时 (libc、libssl、libpthread)           ← 在 /lib 目录
    │ 系统调用 (open/read/write/socket...)     ← 进内核
    ▼
Linux 内核                                    ← 容器和宿主机共享，不打包进镜像
    │
    ▼
硬件
```

Python 解释器本身是一个 C 语言编译出的可执行文件。任何 C 程序启动时第一条指令不是进 `main()`——是先进 C 运行时库做初始化（栈设置、堆初始化），然后才跳转 `main()`。C 运行时库在 `/lib/libc.so`——所以 Docker 镜像必须有 `/lib` 目录。

| 目录 | 放了什么 | Flask 什么时候碰它 | 没了会怎样 |
|------|---------|-------------------|-----------|
| `/bin` | 基础可执行程序（`sh`、`ls`） | Gunicorn 启动脚本调了 `/bin/sh` | `CMD` 指令无法执行 |
| `/lib` | 动态链接库（`libc.so`、`libssl.so`） | **每行 Python 代码**都间接碰它 | Python 解释器无法启动 |
| `/usr` | 用户态软件（`/usr/bin/python3`、pip 包） | Python 解释器本体 + 所有依赖 | 连 `python` 命令都不存在 |
| `/etc` | 系统配置文件（DNS、SSL 证书） | DNS 解析、HTTPS 证书验证 | 网络请求失败 |

### 和 Windows 的对比

Windows 上你用 `E:/Python/python.exe app.py` 跑 Flask，Python 依赖的底层能力由 Windows 系统目录提供（`C:\Windows\System32\msvcrt.dll`、`kernel32.dll`）。Docker 镜像里带的那份 Linux 用户空间，就是容器里的"Windows 系统目录"——只是精简到了应用实际需要的最小集合。

### slim 版本的选择

| 镜像 | 体积 | 区别 |
|------|------|------|
| `python:3.13`（完整版） | ~1 GB | 完整 Debian + 编译工具链（gcc、make）+ 文档 |
| `python:3.13-slim` | ~150 MB | Debian 基础 + 运行时最小集合，去掉编译工具 |
| `python:3.13-alpine` | ~50 MB | Alpine Linux（musl libc），最激进精简 |

选 slim 的理由：pip 包全是纯 Python 或预编译的 wheel，不需要 gcc。Alpine 的 musl libc 和某些 C 扩展不兼容——slim 是稳妥的最小化。

---

## 五、操作系统内核——子系统的集合体

内核不是一个整体——是多个子系统各管各的：

```
                    系统调用层（用户程序的入口）
                            │
        ┌───────┬───────┬───┴───┬───────┬────────┐
        ▼       ▼       ▼       ▼       ▼        ▼
   进程管理  内存管理  文件系统  I/O 栈  网络栈  IPC
```

| 子系统 | 管什么 | 项目里什么时候碰它 |
|--------|------|------------------|
| 进程管理 | 100 个程序抢 8 个核→调度器决定谁跑谁等 | Gunicorn 的 pre-fork：master 进程 fork 出 4 个 worker |
| 内存管理 | 虚址→物理页映射、换页 | `malloc()`/变量赋值——全在虚址里 |
| 网络栈 | TCP 三次握手、拥塞控制、IP 路由 | Flask 收到 HTTP 请求——TCP 栈已排好序 |
| I/O 栈 | 通用块层→调度层→磁盘驱动 | `db.session.commit()` 的写盘链 |
| 文件系统 | inode→块号映射、权限检查 | `open("chat.py")`→查 inode 表 |
| IPC | 管道、信号、共享内存 | Ctrl+C 发 SIGINT；`ps aux | grep gunicorn` 管道 |

### 文件系统 vs I/O 栈——"哪个"和"怎么"

文件系统负责把文件名/偏移量翻译成块号（**哪个块**），I/O 栈负责把块号变成磁盘控制器的寄存器指令（**怎么读写那个块**）。两者在内核内部是上下层关系：

```
VFS（统一文件操作接口）
    ↓
具体文件系统（ext4）：inode → 块号
    ↓
通用块层：缓冲、合并 I/O 请求
    ↓
I/O 调度层：电梯算法排序
    ↓
磁盘驱动：块号 → 硬件寄存器指令
    ↓
磁盘控制器 → 磁盘
```

### OverlayFS——堆叠文件系统

OverlayFS 是内核里的一个文件系统模块（和 ext4 平级），但它不直接面对磁盘——它站在 ext4 之上，把多个目录树合并成一个视图。用户程序 `open("/app/chat.py")` → VFS → OverlayFS → 找到文件在哪一层 → 转发给 ext4 → ext4 去磁盘读。OverlayFS 和 ext4 都在同一个内核里，是上下层转发关系。

### 内核的两个核心职责

1. **硬件抽象**（原始动机）：换硬盘不需要改 `read()` 调用——内核的驱动层屏蔽硬件差异。这是解耦思想在 OS 层的实例化——和 WSGI、HTTP、ORM 是同一个模式：在两个会独立变化的层之间插入一个稳定的中间约定。

2. **隔离/安全**（多任务时代出现）：CPU 特权级 Ring 0（内核态）/ Ring 3（用户态），普通程序不能直接操作硬件——必须通过系统调用这个门，让内核代劳并检查权限。隔离不是"约定"——是 CPU 电路里的硬门。

---

## 六、Docker 层缓存机制——和 Git blob 的异同

### 缓存原理

Docker 构建时每条指令（`COPY`、`RUN`）生成一层文件系统。缓存判断规则：这条指令本身 + 输入文件的哈希和上次构建对比，一样就跳过。

### 为什么 `COPY requirements.txt .` 要写在 `COPY . .` 前面

```dockerfile
COPY requirements.txt .       # 输入只是 requirements.txt——只有它变了才重跑
RUN pip install -r requirements.txt
COPY . .                      # 输入是整个目录——任何文件变了这层都失效
```

修改 `chat.py` → `requirements.txt` 没变 → 前两条命中缓存跳过 → 只重跑 `COPY . .`。改了 `chat.py` 后构建从 30 秒变成 2 秒。

### Docker 不能自动解析命令依赖

Docker 构建引擎不解析 `RUN` 命令的内容——不知道 `pip install -r requirements.txt` 只读 `requirements.txt`。作为构建系统，它做的最安全假设是：`COPY . .` 之后的所有层可能依赖任何被复制进去的文件。解析命令依赖需要构建追踪（Nix、Bazel 这样做），Docker 的设计哲学是"简单通用"。

### 和 Git blob 的对比

两者都是**内容寻址**——用哈希值当"身份证"。

| | Docker 镜像层 | Git blob |
|------|------|------|
| 哈希输入 | COPY 的文件内容 + 前一层哈希 + 指令文本 | 文件内容（不包含文件名和路径） |
| 去重行为 | 两个项目用同样的基础镜像 → 只存一份 | 两个文件内容完全一样 → 只存一个 blob |
| 分叉点 | 输入是整层 + 上下文 | 输入是单个文件 |

同一个原理——"怎么判断有没有变化，然后只重建变了的部分"——在不同层各长出了不同形态的实现。Docker 重建的是文件系统层，Git 重建的是 commit 链，Flask 热重载重建的是进程。

---

## 七、Gunicorn——生产级 WSGI 服务器

### 为什么需要它

`app.run(debug=True)` 的 Werkzeug 开发服务器是**单进程单线程**——同一时刻只处理一个请求。10 个用户同时发消息，第 10 个排队等前 9 个处理完。DeepSeek 一次回复可能要 10 秒，10 个用户最坏情况等 100 秒。

### pre-fork 模型

```
             ┌──────────────────┐
HTTP 请求 →  │ Master 进程        │
             │ (不处理请求，只管理) │
             └───┬───┬───┬──────┘
          fork   │   │   │  fork
        ┌────────┘   │   └────────┐
        ▼            ▼            ▼
   Worker 1      Worker 2     Worker 3
   (进程)        (进程)       (进程)
   各跑一个      各跑一个      各跑一个
   Flask app    Flask app    Flask app
```

Master 进程在收到任何请求**之前**就 fork 出 N 个 worker 子进程。每个 worker 是独立进程（独立 Python 解释器 + 独立 GIL + 独立 Flask app）。一个 worker 卡在 DeepSeek API 等流式回复时，其他 worker 照常处理新请求——不互相阻塞。

### worker 是进程不是线程

| | 进程 | 线程 |
|------|------|------|
| 内存空间 | 独立——每个进程有自己的地址空间 | 共享——同进程内的线程共享内存 |
| 创建成本 | 高——需要复制整个地址空间（fork + COW） | 低——只需创建栈和寄存器上下文 |
| 隔离性 | 强——一个进程崩了不影响其他 | 弱——一个线程写坏内存，全进程一起死 |
| 服务器选择原因 | ✅ 服务器不允许一个 bug 炸全站 | ❌ 不符合生产隔离要求 |

### 和 Flask 热重载的关系

Flask `debug=True` 的双进程模型（父进程监控文件 + 子进程跑 Flask）和 Gunicorn 的 pre-fork 模型用的是**同一个操作系统原语 `fork()`**，但解决了不同的问题——前者解决"改了代码自动重启"，后者解决"多用户并发不排队"。

### GIL（全局解释器锁）

GIL = CPython 解释器内部的互斥锁。规定：同一时刻只有一个线程能持有这把锁，只有持有锁的线程才能执行 Python 字节码。

**为什么有 GIL**：Python 用"引用计数"管理内存。多线程同时改同一对象的引用计数会产生数据竞争。CPython 选择给整个解释器加一把大锁而不是给每个对象加细粒度锁——后者锁开销比对象还大且极易死锁。

**对 Flask 项目的影响**：I/O 等待时 GIL 自动释放（C 代码在执行系统调用前手动 `Py_BEGIN_ALLOW_THREADS`），其他线程趁机跑。所以 GIL 对 I/O 密集型（你的 Flask API）基本不是瓶颈。Gunicorn 选多进程不是因为 GIL——是因为进程隔离性更强。

### Gunicorn 配置参数详解

```python
workers = 4                 # worker 进程数，经验公式 (2×CPU 核数)+1，I/O 密集可突破
worker_class = "sync"       # 同步模式——每个 worker 一次处理一个请求
threads = 1                 # 每个 worker 内只开一个线程
bind = "0.0.0.0:5000"       # Docker 容器内监听所有接口，其他容器通过 flask:5000 访问
accesslog = "-"             # "-" = stdout，Docker 自动收集
errorlog = "-"
loglevel = "info"
timeout = 120               # SSE 流式设高避免误杀（DeepSeek 回复可能 30-60 秒）
graceful_timeout = 30       # 重启时给旧 worker 的清理时间
proc_name = "aichat"
```

`0.0.0.0` vs `127.0.0.1`：Docker 内部网络中 Nginx 容器和 Flask 容器不在同一个"机器"里，`127.0.0.1` 只对容器自己可见。`0.0.0.0` 让 Gunicorn 监听容器所有网络接口，Nginx 通过 `flask:5000` 能访问。安全边界在 Nginx 那层——Flask 容器的 5000 端口不暴露给外网。

---

## 八、Nginx——反向代理 + 静态文件服务器

### 反向代理是什么

**反向代理 = 浏览器以为在和 Nginx 对话，但 Nginx 把请求原样转发给背后的 Flask，Flask 的回复也原样转发给浏览器。** Nginx 是个透明的中转站。

### "正向"和"反向"的区别

两者都是"代理"，区别在于**站在谁前面**：

| | 正向代理 | 反向代理 |
|------|---------|---------|
| 站在谁前面 | 客户端（浏览器） | 服务端（Flask） |
| 谁不知道谁的存在 | 目标服务器不知道真正的客户端是谁 | 客户端不知道背后有多个服务器 |
| 典型场景 | 翻墙——代理替你访问 Google | 负载均衡——Nginx 背后 3 个 Flask，对外一个地址 |
| 谁配置代理 | 用户配浏览器的代理设置 | 运维配 Nginx 的代理规则 |

Vite 的 `proxy: { '/api': 'localhost:5000' }` 也是反向代理——开发和生产用的是同一个模式，只是执行代理的程序从 Vite 变成了 Nginx。

### Nginx 存在的根本原因

1. **隐藏内部结构**：外界只知道 Nginx 的地址，Flask 容器不暴露公网端口
2. **负载均衡**：背后可以挂多个 Flask 实例，Nginx 分发请求
3. **让专人做专事**：Nginx 用 C 实现，处理 HTTPS 加解密、静态文件返回、请求限流、压缩传输——这些"杂务"从 Python 层卸掉，性能是 C 级别的

### 我们的 nginx.conf 逐行解析

```nginx
server {
    listen 80;                              # 监听 80 端口（HTTP 默认端口）

    # 前端静态文件
    location / {
        root /usr/share/nginx/html;         # 文件根目录 = Vue 构建产出的 dist/
        try_files $uri /index.html;         # SPA 路由回退
    }

    # 后端 API 反向代理
    location /api/ {
        proxy_pass http://flask:5000;       # 转发给 Flask 容器
        proxy_set_header Host $host;        # 保留原始 Host 头
        proxy_set_header X-Real-IP $remote_addr;     # 记录真实客户端 IP
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;  # 完整代理链
        proxy_buffering off;                # SSE 流式——收到就转发，不积攒
        proxy_cache off;                    # 聊天接口不缓存——每次重请求 AI
    }
}
```

### try_files 和 SPA 路由

`try_files $uri /index.html` 从左到右依次尝试：先试 `$uri`（当前请求路径，如 `/chat`），找不到文件就回退到 `/index.html`。Vue Router 在浏览器拿到 `index.html` 后读取 URL 中的 `/chat` 路径来渲染对应组件。

没有这行，用户刷新 `/chat` 页面或直接输入 URL → Nginx 找不到 `/chat` 文件 → 404。

### proxy_buffering off——为什么 SSE 需要

Nginx 默认缓冲后端回复——Flask 返回的 chunk 先攒一定量再一次性发给浏览器。对 SSE 流式致命——打字机效果消失。关掉后 Nginx 收到一个 chunk 就立刻转发一个 chunk。

### proxy_cache off——和缓冲的区别

缓冲 = 攒着一起发（影响**时机**）。缓存 = 记下结果，下次直接返回旧结果（影响**结果**）。

如果启用了缓存，用户 A 发了"你好"，Nginx 记下回复。用户 B 再发"你好"，Nginx 直接从缓存返回——AI 永远不会生成新回复。聊天接口不能缓存。

这和 Redis 缓存的区别：Redis 是你**在代码里主动控制的**（手动 set/get），Nginx proxy_cache 是**在基础设施层对应用完全透明**的——请求可能根本没到 Flask 就被拦截返回。选哪层取决于控制粒度。

### proxy_set_header 三条

**`Host $host`**：保留原始请求的 Host 头（`localhost`），别改成 `flask:5000`。

**`X-Real-IP $remote_addr`**：把和 Nginx 建立 TCP 连接的那一端 IP 传给 Flask。没有这行，Flask 的 `request.remote_addr` 看到的是 Nginx 容器的内网 IP（`172.18.0.x`）——日志里无法追踪真实用户。

**`X-Forwarded-For $proxy_add_x_forwarded_for`**：记录完整的代理链。每经过一个代理，代理把自己的 IP 追加到列表末尾。`$proxy_add_x_forwarded_for` 做的事：如果原始请求已有这个头，就把 `$remote_addr` 追加到末尾（逗号分隔）；如果没有，创一个新的。同样需要设为 `$remote_addr` 以确保追加到列表中的是最靠近 Nginx 的客户端 IP——在多级代理场景下，`$remote_addr` 就是不经过中间任何代理、直接与 Nginx 建立连接的源 IP。

`X-Real-IP` 只记最后一个代理的 IP（不包含之前的代理跳），`X-Forwarded-For` 记整条链（多级代理时能回溯完整转发链路）。项目只有 Nginx 一层时两者效果相同，但后者是多层代理的标准做法。

---

## 九、Docker Compose——多容器编排

### 项目文件结构

```
AIChat_v1.0/
├── backend/
│   ├── Dockerfile            # Flask 容器镜像定义
│   ├── .dockerignore         # 排除不打包的文件
│   ├── gunicorn_config.py    # Gunicorn 启动参数
│   └── .env                  # 环境变量
├── frontend/
│   └── Dockerfile            # Vue 多阶段构建（当前未用，预留）
├── nginx/
│   └── nginx.conf            # 反向代理 + 静态文件
└── docker-compose.yml        # 总控——声明所有服务、网络、数据卷
```

### docker-compose.yml 逐行解析

```yaml
services:
  flask:
    build: ./backend                    # 从 backend/Dockerfile 构建镜像
    volumes:
      - ./data:/app/instance            # SQLite 数据持久化到宿主机
    env_file:
      - ./backend/.env                  # 注入环境变量
    restart: unless-stopped             # 意外退出自动重启，手动停不自动起

  nginx:
    image: nginx:alpine                 # 直接用官方镜像，不自己构建
    ports:
      - "80:80"                          # 宿主机 80 → 容器 80
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/conf.d/default.conf:ro  # 挂载配置
      - ./frontend/dist:/usr/share/nginx/html:ro               # 挂载静态文件
    depends_on:
      - flask                            # 启动顺序：先 Flask 后 Nginx
    restart: unless-stopped
```

### volumes——数据持久化

Docker 容器的文件系统是临时的——容器删除，内部所有文件消失。`volumes` 把需要持久化的数据（数据库）和需要替换的配置/代码（nginx.conf、dist 目录）绕过容器的临时文件系统，直接落在宿主机磁盘上。

Flask 容器的 `./data:/app/instance`：Flask 写 `/app/instance/aichat.db` 时，实际写到宿主机 `./data/aichat.db`。容器删了重建，数据不丢。

Nginx 的两个挂载都加了 `:ro`（read-only）——Nginx 不需要写这些文件，只读。即使容器被攻破，也改不了宿主机配置文件。

### EXPOSE vs ports

`Dockerfile` 里的 `EXPOSE 5000` 是文档性质的声明——不实际发布端口。真正让外部访问到的是 `docker-compose.yml` 里的 `ports: "80:80"`。`EXPOSE` 是文档，`ports` 是真正的门。

### depends_on

保证启动顺序（先 Flask 后 Nginx），但不保证 Flask 已经初始化好。Nginx 启动时 Flask 可能还在加载中——收到请求会返回 502。生产级做法是加健康检查。

### 服务名 vs 域名

`proxy_pass http://flask:5000` 里的 `flask` 是 Docker compose 里的**服务名**——Docker 内置 DNS 把服务名解析成容器的内网 IP。容器 IP 可能从 `172.18.0.3` 变成 `172.18.0.4`，但 `flask` 这个域名自动跟过去。

这和公网 DNS（`www.baidu.com` → `110.242.68.66`）是同一个机制，不同作用域。Docker 内置 DNS 在 `127.0.0.11`，只在 Docker 内部网络有效。

---

## 十、Dockerfile 详解

### backend/Dockerfile

```dockerfile
FROM python:3.13-slim              # 基础镜像：Debian + Python 3.13
WORKDIR /app                        # 设置工作目录
ENV PYTHONDONTWRITEBYTECODE=1 \     # 不生成 .pyc 字节码缓存
    PYTHONUNBUFFERED=1               # 关闭 Python 输出缓冲（日志立刻可见）
COPY requirements.txt .             # 先只复制依赖清单（利用层缓存）
RUN pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
COPY . .                            # 再复制全量代码
EXPOSE 5000                         # 声明端口（文档性质）
CMD ["gunicorn", "-c", "gunicorn_config.py", "app:create_app()"]
```

### frontend/Dockerfile——多阶段构建

```dockerfile
# 第一阶段：构建 Vue 应用
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci                          # 精确还原 lock 文件
COPY . .
RUN npm run build                   # 产出 /app/dist/

# 第二阶段：最小化运行时镜像
FROM nginx:alpine                    # 全新的基础镜像——不含 Node.js
COPY --from=build /app/dist /usr/share/nginx/html  # 只复制构建产出
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]  # 前台运行
```

**多阶段构建的核心价值**：构建环境和运行环境分离。第一阶段用巨大的 Node.js + npm 构建出 `dist/`，第二阶段只带 `dist/` 进一个瘦 Nginx 镜像。最终镜像里没有 Node.js、没有 npm 包、没有源码——只有 Nginx + 静态文件。体积从 ~1GB 缩到 ~30MB。

**`daemon off` 为什么需要**：Unix 守护进程默认后台化——fork 子进程，父进程退出。Docker 以 PID 1 为容器生命周期——PID 1 退出则容器终止。`daemon off` 让 Nginx 前台运行，持续占着 PID 1。

### `CMD` 用 JSON 数组格式

`CMD ["gunicorn", "-c", "gunicorn_config.py", "app:create_app()"]`——第一个元素是可执行程序，后面是参数。等价于终端执行 `gunicorn -c gunicorn_config.py "app:create_app()"`。

`CMD` 可以被覆盖：`docker-compose.yml` 里如果写了 `command: xxx`，会覆盖 `CMD`。我们的 compose 没写 `command`，所以启动时默认执行 CMD。

### 和 docker-compose.yml 里 Nginx 的关系

当前 compose 里 Nginx 服务使用 `image: nginx:alpine`（官方镜像）+ 卷挂载 `./frontend/dist`，而不是 `build: ./frontend`。即 `frontend/Dockerfile` 存在但未被引用——宿主机上手动 `npm run build` 后 compose 挂载产出的 `dist/`。frontend/Dockerfile 是后续切换到全容器化方案的预留（构建在容器里完成，不依赖宿主机 Node.js）。

---

## 十一、部署架构——请求的完整物理路径

```
用户浏览器（公网/本机）
    │
    │ HTTP 请求 http://localhost/login 或 http://localhost/api/chat
    ▼
宿主机 80 端口 → Docker 端口映射 → Nginx 容器 80 端口
    │
    ├── location / → 返回 Vue 静态文件（/usr/share/nginx/html ← ./frontend/dist）
    │
    └── location /api/ → 反向代理转发 http://flask:5000
            │
            ▼
        Docker 内部 DNS：flask → 172.18.0.x
            │
            ▼
        Flask 容器：Gunicorn (4 worker) → Flask app → DeepSeek API
            │
            ├── 读/写 aichat.db → /app/instance/ → volumes 映射 → 宿主机 ./data/
            └── 返回 SSE 流 → Nginx (proxy_buffering off) → 浏览器
```

---

## 十二、npm 生态速查

| | Python 生态 | Node.js 生态 |
|------|------|------|
| 包管理器 | **pip** | **npm** |
| 安装依赖 | `pip install flask` | `npm install vue` |
| 依赖清单 | `requirements.txt` | `package.json` + `package-lock.json` |
| 依赖存放 | `site-packages/` | `node_modules/` |
| 运行脚本 | `python app.py` | `npm run dev` |
| 包托管网站 | PyPI | npmjs.com |

`npm = 前端版的 pip`。npmjs.com 是前端版的 PyPI。GitHub 是存代码的，npm 是装依赖的。

### npm ci vs npm install

| | `npm install` | `npm ci` |
|------|------|------|
| 先看谁 | `package.json`（宽松版本范围） | `package-lock.json`（精确版本） |
| 结果 | 版本可能和上次不一样 | 和 lock 文件逐字节一致 |
| 什么时候用 | 开发——加新依赖 | 构建——Docker 镜像、CI/CD |

`npm ci` 保证 Docker 构建的确定性——今天构建的镜像和明天构建的完全一样。

---

## 十三、部署操作流程

```bash
# 1. 构建前端
cd frontend && npm run build

# 2. 一键启动
cd ..
docker compose up -d --build

# 3. 查看状态
docker compose ps

# 4. 验证
curl http://localhost/api/auth/login -H "Content-Type: application/json" -d '{"username":"test","password":"123456"}'
# 浏览器打开 http://localhost

# 5. 更新代码后
git pull && cd frontend && npm run build && cd .. && docker compose up -d --build

# 6. 停止
docker compose down       # 数据卷（./data）保留在宿主机
```

---

## 十四、跨层模式识别——Docker 技术栈中的统一模式

本次部署学习覆盖的知识点看似零散，但底下有统一的模式：

| 模式 | 在应用层的实例 | 在基础设施层的实例 |
|------|-------------|----------------|
| 依赖清单文件 | `requirements.txt` | `package.json` |
| URL 路径路由分发 | Flask `@app.route` | Nginx `location` |
| 反向代理中转请求 | Vite `proxy` | Nginx `proxy_pass` |
| 配置集中管理 | `Config` 类 | `gunicorn_config.py` |
| 层缓存——"没变不重建" | Git blob 哈希链 | Docker 层缓存 |
| fork 创建进程 | Flask `debug=True` 文件监控 | Gunicorn pre-fork 多 worker |
| 中间层统一接口 | WSGI（服务器↔框架） | VFS（进程↔文件系统） |
| 栈式层层转发 | Flask 上下文栈 | 内核文件系统栈（VFS→ext4→块I/O） |
| 名字→地址翻译 | DNS 公网域名 | Docker 内置 DNS 服务名 |
