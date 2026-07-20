# Flask 后端搭建 — 知识复盘

> 项目：AIChat v1.0  
> 阶段：后端骨架搭建（models + config + app 入口）  
> 状态：进行中  

---

## 一、后端是什么

### 前后端通信模型

```
浏览器（前端）                    服务器（后端）
┌─────────────────┐              ┌─────────────────┐
│ 用户点"发送消息"  │  ──HTTP──►  │ 收到消息          │
│                 │              │ ↓               │
│                 │              │ 查数据库（历史记录）│
│                 │              │ ↓               │
│ 打字机逐字显示    │ ◄──SSE───   │ 调 DeepSeek API   │
│                 │              │ ↓               │
│                 │              │ 存数据库（新消息）  │
│                 │              │ ↓               │
│                 │              │ 返回结果          │
└─────────────────┘              └─────────────────┘
```

**核心原则**：前端只管"长什么样"，后端只管"数据怎么来、存哪里、怎么算"。

### HTTP 和 JSON 的关系

- **HTTP** = 信封（传输协议），包含状态码、请求方法、Header
- **JSON** = 信封里的货物（数据格式），前后端都能读懂的通用语

### 状态码是双向的

```
浏览器 ──200/401/500──► Flask 后端 ──200/429/401──► DeepSeek API
        ◄── JSON ──                ◄── JSON ──
      浏览器读状态码              后端也要读 DeepSeek 的状态码
```

Flask 后端既是服务端（对浏览器），也是客户端（对 DeepSeek）。

### 常用状态码速查

| 状态码 | 含义 | 你的项目里什么时候用 |
|--------|------|-------------------|
| 200 | 成功 | 登录成功、聊天返回 |
| 201 | 创建成功 | 注册成功 |
| 400 | 请求格式错误 | 前端发来的 JSON 缺字段 |
| 401 | 未认证 | 没 token 或 token 过期 |
| 403 | 无权限 | 不是你的资源你想看 |
| 409 | 冲突 | 用户名已被注册 |
| 429 | 请求太频繁 | DeepSeek 限流 |
| 500 | 服务器内部错误 | 代码崩了 |

---

## 二、后端要实现的四个功能

```
POST   /api/auth/register    → 注册
POST   /api/auth/login       → 登录
POST   /api/chat             → 聊天（SSE 流式）
GET    /api/history          → 获取历史记录列表
```

---

## 三、核心概念详解

### 1. JWT Token

**问题**：HTTP 是无状态的——每次请求独立，服务器不记得你是谁。

**解决**：登录时后端返回一个加密的 token。后续请求带着 token，后端解密验证身份，不需要每次传密码。

**JWT 三段结构**：

```
eyJhbGciOi...  .  eyJzdWIiOi...  .  SflKxwRJS...
     ↑               ↑               ↑
  Header          Payload         Signature
  加密算法         用户数据          防篡改签名
```

- Payload 只是 Base64 编码，不是加密——任何人都能解码看到内容，所以**不要放密码**
- 安全性靠 Signature：用 `JWT_SECRET_KEY` 签名，篡改 Payload 后签名对不上，服务器立刻拒绝

**完整鉴权流程**：

```
注册 → 密码哈希 → 存入数据库
登录 → 验证密码 → 返回 JWT token
聊天 → 前端带 token 发请求 → @jwt_required() 验证 → 通过后执行函数
```

### 2. 密码哈希

**绝对不存明文密码**。存的是哈希值（不可逆的数字指纹）。

```python
# 注册时
password_hash = hash("123456")   # → 一长串乱码
# 存进数据库的是乱码

# 登录时
hash(用户输入的密码) == 数据库里的密码哈希？
相等 → 密码正确
```

**哈希特点**：
- 同样输入永远得到同样输出（可验证）
- 无法从输出倒推输入（不可逆）
- 输入差一个字符，输出天差地别

### 3. ORM（对象关系映射）

**没有 ORM 的世界**：手写 SQL 字符串，换数据库要重写，有 SQL 注入风险。

**有 ORM 的世界**：Python 类 = 数据库表，Python 对象 = 数据库行，列 = 类属性。

```
你写的 Python                    ORM 翻译成 SQL              SQLite 执行
─────────────────────────────────────────────────────────────────────
user = User(username="zhangsan")  →  （内存里的对象）
db.session.add(user)               →  （标记为"待插入"）
db.session.commit()                →  INSERT INTO user ...    →  写入 aichat.db
```

### 4. 主键（Primary Key）

**每一行数据的唯一身份证号**。有了它，才能精确定位到数据库中任意一行。

| 效果 | 含义 |
|------|------|
| 唯一性 | 同一张表里主键值不能重复 |
| 不能为空 | 自动 `nullable=False` |
| 自动索引 | B-Tree 索引，`User.query.get(5)` 是常数时间 |
| 自增 | SQLite 自动取 `上一行 id + 1` |

---

## 四、数据库技术栈

| 层级 | 技术 | 干什么 |
|------|------|--------|
| ORM 框架 | SQLAlchemy 2.0 | Python 类 ↔ 数据库表的翻译官 |
| Flask 封装 | Flask-SQLAlchemy 3.1 | 提供 `db.Model`、`db.session` 等 Flask 风格 API |
| 驱动 | SQLite 内置 | 真正的数据库引擎 |
| 数据库文件 | `backend/aichat.db` | 单文件数据库 |

**注意**：`flask-sqlalchemy` 和 `sqlalchemy` 是两个不同的包，前者依赖后者。

---

## 五、User 模型逐行解析

```python
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())
```

### `db = SQLAlchemy()`
创建 SQLAlchemy 核心实例。项目中所有数据库操作（建表、增删改查）都通过它。

### `class User(db.Model)`
继承 `db.Model` 告诉 SQLAlchemy"这是一张表"。继承后自动获得查询能力（`User.query.filter_by(...)`）、保存能力（`db.session.add(user)`）等。

### `__tablename__ = "users"`
特殊类属性（不是魔术方法），指定表名。不写默认用类名小写 `user`，容易和 SQL 关键字冲突。

### 各列参数拆解

| 参数 | 作用 | 什么时候用 |
|------|------|-----------|
| `primary_key=True` | 主键，自动索引 + 唯一 + 不为空 | 每张表必有一列 |
| `unique=True` | 值不能重复，数据库层面保证 | 用户名、邮箱、手机号 |
| `nullable=False` | 不允许为空 | 必填字段 |
| `server_default=...` | 数据库端默认值（INSERT 时触发） | 时间戳 |
| `onupdate=...` | 数据库端更新值（UPDATE 时触发） | `updated_at` |

#### `server_default` vs `default`

| 类型 | 谁给值 | 举例 |
|------|--------|------|
| `default`（客户端） | Python 代码执行时给值 | `default=datetime.utcnow` |
| `server_default`（服务端） | 数据库引擎在插入时给值 | `server_default=db.func.now()` |

`server_default` 的好处：无论从哪个入口写入数据（代码、命令行、数据库工具），都会自动填时间。

#### `created_at` vs `updated_at`

| 列 | 触发时机 | 变化 |
|------|---------|------|
| `created_at` | 只在 INSERT 时 | 一辈子不变 |
| `updated_at` | INSERT 时 + 每次 UPDATE 时 | 每次修改自动刷新 |

---

## 六、Config 配置详解

```python
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-jwt-secret")
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///aichat.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
```

### 为什么要集中配置

散落各处 → 改一个值翻三个文件；密钥硬编码 → push 到 GitHub 后泄露。  
集中到一个类 → 一处改全局生效；敏感值从外部注入。

### 环境变量 vs .env 文件

```
电脑环境变量（系统自带）     .env 文件（项目级别）
─────────────────────    ─────────────────────
USERNAME、PATH、TEMP       DEEPSEEK_API_KEY（项目自定义）
全局永久                   跟着项目走
                          load_dotenv() 临时加载到环境变量池
```

**优先级**：系统环境变量 > .env 文件 > 代码默认值

**具体例子**：

```
场景 1 — 本地开发（没设系统环境变量）：
  os.getenv("DEEPSEEK_API_KEY") → 系统没有 → 读 .env → 返回 "sk-local-dev-key"

场景 2 — 生产服务器（Railway 面板设了环境变量 DEEPSEEK_API_KEY=sk-production）：
  os.getenv("DEEPSEEK_API_KEY") → 系统有 → 返回 "sk-production"
  .env 文件里写的 "sk-local-dev-key" 被忽略

场景 3 — .env 里也没写：
  os.getenv("DEEPSEEK_API_KEY") → 系统没有 → .env 也没有 → 返回默认值 ""
```

这是有意设计的——你在生产服务器设置的环境变量（真实密钥）优先级最高，`.env` 里的开发密钥不会把它覆盖掉。如果非要让 `.env` 覆盖系统变量，需要显式写 `load_dotenv(override=True)`，但几乎没人这么干。

### `.env` + `.env.example` 标准做法

- `.env`：真实密钥，在 `.gitignore` 里，不提交
- `.env.example`：模板文件（只有键名，没有值），提交到 Git，别人 clone 后复制一份填入自己的密钥

### 各配置项

| 变量 | 谁用 | 用途 | 重要性 |
|------|------|------|--------|
| `SECRET_KEY` | Flask 内部 | 加密 session cookie | Flask 启动需要存在 |
| `JWT_SECRET_KEY` | Flask-JWT-Extended | 签名和验证 JWT token | **泄露 = 可伪造任意用户身份** |
| `DEEPSEEK_API_KEY` | OpenAI SDK | 调用 DeepSeek API 的凭证 | 没有它 API 不响应 |
| `SQLALCHEMY_DATABASE_URI` | SQLAlchemy | 数据库连接地址，`sqlite:///` = 相对路径 | 换数据库只改这一行 |
| `SQLALCHEMY_TRACK_MODIFICATIONS` | Flask-SQLAlchemy | 关掉废弃的信号系统 | 不写 = 启动时黄字警告 |

### `load_dotenv()` 做了什么

把 `.env` 文件里的 `KEY=VALUE` 临时加载到操作系统环境变量池。Python 进程结束后消失，但 `.env` 文件还在，下次启动再加载。默认不覆盖已有的系统环境变量（`override=True` 才会覆盖）。

---

## 七、Flask 应用工厂模式

```python
from flask import Flask
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from config import Config
from models import db


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    CORS(app)
    JWTManager(app)

    with app.app_context():
        db.create_all()

    return app
```

### 为什么用 `create_app()` 包装而不是直接 `app = Flask(__name__)`

| 方式 | 问题 |
|------|------|
| 直接创建 `app = Flask(__name__)` | 测试时多个模块 import 同一个 app 变量 → 循环引用；测试无法创建独立实例 |
| 工厂函数 `create_app()` | 每次调用返回全新实例；测试隔离；企业项目 99% 都用这个写法 |

### `db.init_app(app)` vs `db = SQLAlchemy(app)`

工厂模式下 app 在函数内部才创建，外部拿不到，所以需要延迟绑定——先创建 `db = SQLAlchemy()`（不绑定），函数里再 `db.init_app(app)` 绑上去。

### `db.create_all()` 的行为

`CREATE TABLE IF NOT EXISTS ...`——有表就跳过，没表才建。可以反复跑，不会重复建表、不会丢数据。

**为什么不能更新表结构**：

`db.create_all()` 的职责只有一条：**"表不存在就建"**。它检查的是整张表的存在性，不是逐列比对。

```python
# 第一次跑：建了一张 4 列的表（id, username, password_hash, created_at）
db.create_all()

# 你在模型里加了第 5 列（updated_at），再跑一次
db.create_all()
# → 数据库一看：users 表已存在，跳过
# → 老表还是 4 列，updated_at 这列永远不会被加进去
```

这不是 SQLite 的问题，是 `db.create_all()` 的定位——它只负责"第一次建表"，不管表建好之后的任何结构变更。这就像 `mkdir` 命令——目录存在就报错跳过，不会进去帮你在目录里新增一个子文件夹。

**怎么办**：

| 方式 | 适用场景 |
|------|---------|
| 删 `aichat.db` 文件重建 | 开发阶段，数据不重要 |
| Flask-Migrate（Alembic） | 生产环境，不能丢数据 |

Flask-Migrate 的本质是**数据库版本的 Git**——`db migrate`（生成迁移脚本）→ `db upgrade`（应用迁移）→ `db downgrade`（回滚）。每个迁移文件就像一次 commit，数据库结构变更被精确跟踪。

### CORS 是什么

浏览器的安全机制——**同源策略**。两个页面的协议、域名、端口三者完全相同才是同源。`localhost:5173`（前端）和 `localhost:5000`（后端）端口不同，浏览器判定为不同源，默认禁止前端 JS 请求后端。

#### 同源策略解决什么问题

假设用户在一个标签页里登录了银行网站 A，同时在另一个标签页里打开了一个恶意网站 B。B 网站的 JS 代码可以向 A 网站的后端发 HTTP 请求——浏览器里没有机制阻止它——而 A 服务器会正常处理这个请求并返回响应。如果浏览器不加拦截，B 网站的 JS 就能读到 A 服务器返回的用户余额数据。

同源策略做的事：**浏览器在 JS 读响应之前检查——"发起这个请求的页面的域名，和接收这个响应的服务器的域名，是同源吗？**"。不是同源 → 浏览器把响应扔掉，JS 拿不到数据。

#### 两类跨域请求——浏览器在不同的时刻拦截

**简单请求**（`GET`、`POST` + 标准 `Content-Type`，不带自定义头）：

```
浏览器：直接发 POST，请求体和服务器之间照常通信
服务器：正常处理 → 正常返回 200 + 数据 + Access-Control-Allow-Origin 头
浏览器：收到响应 → 检查 Access-Control-Allow-Origin 头
  → 白名单里有我的域名 → JS 可以读响应 ✅
  → 白名单里没有 → 浏览器把响应扔掉，JS 拿不到数据 ❌
```

请求照发，服务器照处理——浏览器在**最后一步**拦住 JS，不让他读响应。

**复杂请求**（带 `Authorization`、`Content-Type: application/json`、PUT/DELETE 等）：

```
浏览器：先不发正式请求——先发一个 OPTIONS 预检请求（Preflight）
        "服务器，我能用 Authorization 头吗？JSON Content-Type 可以吗？"
服务器：返回 Access-Control-Allow-Headers / Methods / Origin 等权限头
浏览器：检查权限范围
  → 权限够 → 发正式请求（和后端正常通信）✅
  → 权限不够 → 连正式请求都不发 ❌
```

复杂请求在**发请求之前**就被拦——服务器根本没收到正式请求，不知道有这回事。

#### 你的项目里

登录、注册、聊天全部是复杂请求（`Content-Type: application/json` + `Authorization` 头），全部触发预检。开发阶段 Vite 代理让浏览器不认为是跨域——JS 从 `localhost:5173` 访问 `localhost:5173`，同源策略根本不会触发，`CORS(app)` 开发阶段没用上。生产环境下前端部署到 Vercel、后端部署到 Railway，浏览器访问的是两个不同域名——这时 `CORS(app, origins=["前端域名"])` 加上响应头告诉浏览器"这个跨域访问是我允许的"。

没有 `CORS(app)` → 前端 `axios.post('http://localhost:5000/api/chat')` → 浏览器拦截，请求根本发不出去，控制台报 `Access-Control-Allow-Origin` 错误。

Flask-CORS 做的事：在后端每个 HTTP 响应的头部自动加上 `Access-Control-Allow-Origin`，告诉浏览器"这个跨域请求我允许了"。不加这个包的用户一般都经历过前端怎么也调不通后端、最后发现是浏览器拦截了所有请求的绝望半小时。

### 蓝图（Blueprint）是什么

Flask 内置的模块化机制——把不同功能的接口拆分到不同文件：

```python
# auth.py —— 认证相关接口
from flask import Blueprint
auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/api/auth/register", methods=["POST"])
def register():
    ...

# chat.py —— 聊天相关接口
chat_bp = Blueprint("chat", __name__)

@chat_bp.route("/api/chat", methods=["POST"])
def chat():
    ...

# app.py 里统一注册
app.register_blueprint(auth_bp)
app.register_blueprint(chat_bp)
```

**没有蓝图**：所有路由堆在 `app.py` 一个文件里，几百行代码混在一起，改一个接口翻半天。  
**有蓝图**：认证、聊天各自独立文件，功能边界清晰，多人并行开发不冲突。

蓝图和 `create_app()` 工厂模式是搭档——工厂创建 app 实例，蓝图组织路由。两者合在一起就是 Flask 企业项目的标准骨架。

---

## 八、app.py 逐行解析

```python
from flask import Flask
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from config import Config
from models import db


def create_app():
    app = Flask(__name__)              # ①
    app.config.from_object(Config)     # ②

    db.init_app(app)                   # ③
    CORS(app)                          # ④
    JWTManager(app)                    # ⑤

    with app.app_context():            # ⑥
        db.create_all()                # ⑦

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)
```

### ① `app = Flask(__name__)`

Flask 是一个普通 Python 类。`app = Flask(__name__)` 就是实例化一个对象——和你写 `user = User(username="zhangsan")` 一模一样。

`__name__` 是当前 `.py` 文件的名字（Python 内置模块属性）。直接运行时是 `"__main__"`，被 import 时是 `"app"`。写成 `"my_chat_app"` 也行，但约定俗成写 `__name__`——文件改名时不用改这行，import 和直接运行都能正确工作。

### ② `app.config.from_object(Config)`

批量注入配置。等价于手写了：

```python
app.config["SECRET_KEY"] = Config.SECRET_KEY
app.config["JWT_SECRET_KEY"] = Config.JWT_SECRET_KEY
# ... 逐个来一遍
```

少写重复代码，且不会漏。

### ③ `db.init_app(app)`

**不是"app 管理数据库"，方向反了**——是告诉 db："你以后要管的 app 是这一个。"

`db` 之前只是一个空壳 `SQLAlchemy()`，不知道数据库文件在哪。`init_app(app)` 把 app 的引用存入 db 内部注册表。之后 db 做任何操作时都知道去 `app.config` 里取配置。

**为什么不需要 `with app.app_context()`**：`init_app` 只是存一个引用，不读配置、不连数据库、不执行 SQL，不需要知道"当前活跃的 app"。

### ④ `CORS(app)` — 跨域许可

浏览器的安全规则——**同源策略**：`localhost:5173`（前端）不能向 `localhost:5000`（后端）发请求，因为端口不同。`CORS(app)` 在每次 HTTP 响应的头部加上 `Access-Control-Allow-Origin`，告诉浏览器"这个跨域请求我允许了"。不加这行，前端永远调不通后端。

### ⑤ `JWTManager(app)` — JWT 鉴权初始化

从 `app.config` 读取 `JWT_SECRET_KEY`，注册 `@jwt_required()` 装饰器。之后 `auth.py` 里写的 `@jwt_required()` 能生效，就是因为这里初始化了。

### ⑥⑦ `with app.app_context()` + `db.create_all()`

`db.create_all()` 内部需要知道"当前活跃的 app 是谁"来读取数据库路径配置。但 `create_app()` 还没 `return app`，Flask 还没启动，没人自动设定活跃标记。`with app.app_context()` 手动设标记：进入时把 app 设为当前活跃，退出时取消标记。

`with` 保证即使 `db.create_all()` 抛异常，标记也一定会被清除。

### `create_app()` 返回的 app 里装了什么

```
app.config   → 所有配置（SECRET_KEY、JWT_SECRET_KEY、DEEPSEEK_API_KEY...）
db           → 已绑定、已建表的数据库（aichat.db 已生成，User 表已建好）
JWTManager   → JWT 鉴权就绪，@jwt_required() 可用
CORS         → 每个响应自动带跨域许可
```

### `app.run(debug=True)` 启动后终端输出的含义

| 输出 | 含义 |
|------|------|
| `WARNING: This is a development server...` | Werkzeug 是开发用单线程服务器，不能扛生产流量 |
| `Running on http://127.0.0.1:5000` | Flask 已启动，监听本地 5000 端口 |
| `Restarting with stat` | debug 模式启动了文件监控器，代码改动自动重载 |
| `Debugger is active!` | Werkzeug 调试器已激活——代码报错时浏览器显示交互式 Python 命令行 |
| `Debugger PIN: 320-981-406` | 调试器访问密码，基于本机信息自动生成 |

### `debug=True` 的安全隐患

生产环境必须关 debug。debug 模式下，代码报错时浏览器上出现一个**交互式 Python 调试器**——任何人都能在浏览器里直接执行你的 Python 代码。本地开发（localhost）只有你自己能访问，没问题；部署到公网后等于把服务器终端暴露给全世界。

---

## 九、上下文管理器深入

### 什么是上下文管理器

任何 `with x as y:` 语句中，`x` 必须是一个实现了 `__enter__` 和 `__exit__` 方法的对象。

```python
with 某对象:        # ① 进入：自动调用 某对象.__enter__()
    做事情           # ② 做事
                     # ③ 退出：自动调用 某对象.__exit__()（中间报错也会执行）
```

### 三个等价写法

```python
# 写法 1：with（最安全）
with app.app_context():
    db.create_all()

# 写法 2：手动 push/pop（容易漏 pop）
ctx = app.app_context()
ctx.push()
db.create_all()
ctx.pop()           # 如果 create_all() 抛异常，这一行执行不到

# 写法 3：手动 + try/finally（啰嗦）
ctx = app.app_context()
ctx.push()
try:
    db.create_all()
finally:
    ctx.pop()        # finally 保证异常时也执行
```

`with` 就是写法 3 的语法糖——python-dotenv 的作者帮你写了 `__enter__`（调用 `push`）和 `__exit__`（调用 `pop`），你只管写 `with`。

### 为什么需要应用上下文（app context）

`create_app()` 跑到 `db.create_all()` 时，app 对象已经有了，但 **db 不知道"当前在用哪个 app"**。Flask 的设计允许同一进程里跑多个 app 实例——用"当前活跃 app"的标记来决定配置从哪取，而不是全局写死一个 app 引用。

**你的项目只有一个 app，但库的作者不能假设所有用户都只有一个 app。** 上下文就是解决"多 app 共处一个进程时，每个操作自动找对配置"的机制。

### app context 的栈是 Python list，不是 C 调用栈

Flask 内部的"上下文栈"实际上就是一个 Python `list`，`push` = `list.append()`，`pop` = `list.pop()`。和 CPU 层面的硬件调用栈没有关系，只是借用了"栈"这个名字。

---

## 十、WSGI 与 Flask 开发服务器

### WSGI 是什么

WSGI（Web Server Gateway Interface）——Python Web 应用和真正的 Web 服务器之间的**通用插头标准**。

```
开发环境（你现在）            生产环境（部署后）
浏览器                        浏览器
  ↓                            ↓
Werkzeug（Flask 内置）         Nginx / Caddy（真正 Web 服务器）
  ↓                            ↓
Flask 应用                    Gunicorn / uWSGI（WSGI 服务器）
                               ↓
                             Flask 应用（多进程副本）
```

### Werkzeug vs Gunicorn

| | Werkzeug（`app.run()`） | Gunicorn |
|------|------|------|
| 并发 | 单线程，一次处理一个请求 | 多 worker 进程，并行处理 |
| 用途 | 开发调试 | 生产环境 |
| 稳定性 | 长时间跑可能内存泄漏 | 专门优化过长期稳定性 |

### 为什么生产环境不能直接用 `app.run()`

- 性能：10 个用户同时发消息，第 10 个得等前 9 个处理完
- 安全：debug 模式下浏览器可以直接执行 Python 代码
- 稳定：长时间运行会有内存泄漏

---

## 十一、JWT 签名与安全深入

### 签名到底怎么算

```
Payload: {"user_id": 5}
    ↓ 和 JWT_SECRET_KEY 一起丢进哈希函数
JWT_SECRET_KEY = "ilovepython"
    ↓
SHA-256 → "3f8a9b2c1d4e5f..."
    ↓ 这就是签名（token 第三段）
```

### 验证过程

```
服务器收到 token → 拆出 Payload + 签名
    → 用同一个 JWT_SECRET_KEY 对 Payload 重新算哈希
    → 新签名 == token 里的签名？相等→通过，不相等→被篡改过→拒绝
```

### 攻击者改 Payload 会怎样

攻击者把 `{"user_id": 5}` 改成 `{"user_id": 999}`，但签名还是旧的。服务器重新算哈希发现不匹配→拒绝。攻击者要伪造签名必须知道 JWT_SECRET_KEY——他不知道，所以做不到。

### 改了 JWT_SECRET_KEY 会发生什么

所有旧 token 立即失效——旧签名是用旧密钥算的，新密钥算出来的签名对不上。这不是 bug，是特性：密钥泄露后更换密钥，所有旧 token 全部作废。

### 穷举 JWT 密钥可行吗

不可能。HS256 产生 256 位哈希，可能的密钥数量约 1.16×10⁷⁷——比地球上所有沙子数量还大几十个数量级。每秒试 10 亿次，试完需要的时间远超宇宙年龄。

### 真正的攻击入口（按威胁排序）

| 攻击方式 | 威胁 | 防御 |
|---------|------|------|
| HTTP 明文传输（中间人抓包） | 高 | HTTPS——Vercel + Railway 默认开启 |
| `.env` 误提交 GitHub | 高 | `.gitignore` |
| XSS（跨站脚本注入） | 中 | Vue 3 默认对 `{{ }}` 做 HTML 转义 |
| 浏览器恶意插件读 localStorage | 中 | token 设短过期时间缓解 |
| JWT 密钥太弱（如 `"123"`） | 低 | 使用强随机字符串 |
| 用户电脑被物理接触 | 低 | 不属于后端防护范围 |

### 限流保护的是什么

不是 JWT 密钥的安全——是**接口调用频率**。防止攻击者用偷来的 token 反复调 `/api/chat` 把你的 DeepSeek 费用打爆，或者暴力枚举密码撞库登录。

---

## 十二、Git 与二进制文件

### 为什么 `.db` 文件不能进 Git

**原因 1**：运行产物，不是源码。`aichat.db` 是 `db.create_all()` 生成的——clone 项目的人在自己电脑上跑一次也会生成。

**原因 2**：含用户数据。测试账号、密码哈希不应出现在公开仓库。

**原因 3**：Git 的存储机制对二进制文件极度低效。

### Git 的存储机制

Git 存的是**完整快照**（不是差异）。每次 commit 拍一张所有文件的完整照片，用 SHA-1 哈希值命名文件。文本文件两版之间相同的行→同一哈希→自动去重。二进制文件（`.db`）改一个用户，整个数据库文件的字节几乎全变了→几乎没有哈希块可以复用→每次 commit 都存一份接近完整大小的新副本。

```
文本文件 50 次 commit:  .git/ ≈ 300 KB
.db 文件 50 次 commit:  .git/ ≈ 5.5 MB
```

### 二进制文件的合并冲突

Git 面对两个版本不同的 `.db` 文件无法逐行比较合并——只能把两个文件都扔给你，让你选一个保留、另一个丢弃。但 SQLite 文件不能用文本编辑器手动编辑，只能删掉重建。所以 `.gitignore` 直接拦住，不让它进入版本控制。

### Git 合并的三条规则

| 两个人改同一文件的 | Git 的行为 |
|-----------------|-----------|
| 不同行（各自独立） | 自动拼接为一个新版本 |
| 同一行 | 标记冲突，暂停合并，等你手动选 |
| 同一位置加了不同内容（相邻行） | 也标记冲突——不知道谁先谁后 |

Git 从不在两个合法改动间二选一——它把能合并的部分合并了，合不上的标记出来让你决定。

---

## 十三、报错阅读技巧

### Python 报错堆栈从下往上读

```
Traceback (most recent call last):       ← 别从这里看
  File "/lib/.../site-packages/flask/..." ← 第三方库，跳
  File "/lib/.../site-packages/sqlalchemy/..." ← 第三方库，跳
  File "auth.py", line 42, in login      ← 你的代码，看这
KeyError: 'username'                      ← 根因：字典里没 'username'
```

**最后一行是根本原因，往上找第一个你自己的文件就是错误位置。**

### 训练方法

1. 看最后一行——`XXXError: message`
2. 在堆栈中定位你自己的 `.py` 文件那行
3. 把错误信息复述给自己听
4. 先假设一个原因，再验证——错了换假设，逐步逼近

---

## 十四、代码验证方法

### 三层验证

```bash
# 第一层：逐文件测 import
cd backend
E:/Python/python.exe -c "from models import db, User; print('models OK')"
E:/Python/python.exe -c "from config import Config; print('config OK')"
E:/Python/python.exe -c "from app import create_app; app = create_app(); print('app OK')"

# 第二层：启动 Flask
E:/Python/python.exe app.py
# 看到 Running on http://127.0.0.1:5000 即成功

# 第三层：接口测试（写完后）
curl -X POST http://localhost:5000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username": "test", "password": "123456"}'
```

### 为什么 `import` 成功就能说明没问题

Python 的 `import` 是逐行执行——包没装会报 `ImportError`，语法错了会报 `SyntaxError`，类名拼错会报 `NameError`。`print('OK')` 执行到 = 前面所有行都安全通过。

---

## 十六、当前项目文件状态

```
backend/
├── models.py          ✅ User 模型定义完成
├── config.py          ✅ 配置类完成
├── app.py             ✅ Flask 应用入口，骨架跑通
├── auth.py            待写（注册/登录路由）
├── chat.py            待写（聊天接口）
├── requirements.txt   ✅ 依赖清单
├── .env               ✅ 环境变量
└── instance/          🔒 运行时产物，不进 Git
    └── aichat.db      自动生成，.gitignore 已拦截
```

---

## 十五、遇到的问题

| 问题 | 原因 | 解决 |
|------|------|------|
| `flask_sqlalchemy` 报 import 警告 | 只装了 `sqlalchemy`，没装 `flask-sqlalchemy` | `pip install flask-sqlalchemy` |
| `.gitignore` 规则全部失效（`.vscode/`、`.env`、`__pycache__/` 出现在暂存区） | 创建 `.gitignore` 时每行前面有缩进（tab + 空格），Git 不自动去除前导空白 | 去掉所有行首缩进，顶格写 |
| `db.create_all()` 把数据库文件建到了 `instance/` 目录下 | Flask 的默认行为——运行实例相关的数据放在 `instance/`，和源码目录分离 | 正常现象，在 `.gitignore` 加上 `instance/` 和 `*.db`，注意每个规则顶格写 |
| `auth.py` 出现在 `Changes not staged for commit` | IDE 打开文件时自动格式化或保存 | `git restore backend/auth.py` 恢复 |
