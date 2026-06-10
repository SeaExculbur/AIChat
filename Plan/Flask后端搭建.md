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

浏览器的安全机制——**同源策略**。`localhost:5173`（前端）和 `localhost:5000`（后端）虽然在同一台机器上，但**端口不同**，浏览器判定为跨域，默认禁止前端 JS 请求后端。

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

## 八、代码验证方法

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

## 九、当前项目文件状态

```
backend/
├── models.py          ✅ User 模型定义完成
├── config.py          ✅ 配置类完成
├── app.py             待写（工厂模式入口）
├── auth.py            待写（注册/登录路由）
├── requirements.txt   ✅ 依赖清单
└── .env               ✅ 环境变量
```

---

## 十、遇到的问题

| 问题 | 原因 | 解决 |
|------|------|------|
| `flask_sqlalchemy` 报 import 警告 | 只装了 `sqlalchemy`，没装 `flask-sqlalchemy` | `pip install flask-sqlalchemy` |
