# Flask 业务接口 — 知识复盘

> 项目：AIChat v1.0  
> 阶段：auth.py 业务接口（注册 + 登录 + 删除账号）  
> 状态：auth.py 已完成并 curl 测试通过  

---

## 一、auth.py 做了什么

```
POST   /api/auth/register       → 注册新用户 → 返回 token
POST   /api/auth/login          → 验证密码 → 返回 token
DELETE /api/auth/delete-account → 验证身份 → 删账号 + 聊天记录
```

三个接口共享同一个骨架：路由装饰器 → 读请求 → 查数据库 → 操作数据 → commit → 返回 JSON。

---

## 二、蓝图（Blueprint）

### 解决什么问题

没蓝图时，所有路由写在一个 `app.py` 里——认证、聊天、管理 40 个接口几千行混在一起。改登录功能不小心动到聊天代码，两个人同时改不同功能直接 merge 冲突。

有蓝图后，`auth.py` 只管认证，`chat.py` 只管聊天。`app.py` 只做组装。

### 怎么工作

```python
# auth.py — 创建蓝图对象（一张空路由表）
auth_bp = Blueprint("auth", __name__)

# 往路由表里贴纸条：URL → 函数
@auth_bp.route("/api/auth/register", methods=["POST"])
def register():
    ...

# app.py — 把蓝图的纸条全部抄到 app 的路由表上
from auth import auth_bp
app.register_blueprint(auth_bp)
```

| `Blueprint("auth", __name__)` 参数 | 含义 |
|------|------|
| `"auth"` | 蓝图的名字——Flask 内部用这个名字区分不同蓝图 |
| `__name__` | 当前模块名——告诉蓝图它是哪个 `.py` 文件里的 |

蓝图 = 可拆卸的独立零件，`app.py` = 把零件组装起来的骨架。

---

## 三、注册与登录：逐行拆解

### 导入部分

```python
from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, ChatHistory
```

| 导入 | 干什么 | 没它会怎样 |
|------|--------|-----------|
| `request` | 读取前端发来的 HTTP 请求体 | 拿不到用户输入的 JSON |
| `jsonify` | 把 Python dict 转成 JSON | 前端收到的是二进制，无法解析 |
| `create_access_token` | 签发 JWT token | 用户注册/登录后没通行证 |
| `generate_password_hash` | 明文密码 → 不可逆哈希 | 数据库存明文密码，泄露就完蛋 |
| `check_password_hash` | 比较用户输入和数据库哈希是否一致 | 没法安全验证密码 |
| `jwt_required` | 路由装饰器——没 token 直接 401 | 没登录的人也能调聊天接口 |
| `get_jwt_identity` | 从 token 里读出 user_id | 不知道当前请求是谁发的 |

### 注册接口

```python
@auth_bp.route("/api/auth/register", methods=["POST"])
def register():
    data = request.get_json()                    # ① 解析 JSON
    username = data.get("username")              # ② 取用户名字段
    password = data.get("password")              # ② 取密码字段

    if not username or not password:             # ③ 空值检查
        return jsonify({"error": "用户名和密码不能为空"}), 400

    if User.query.filter_by(username=username).first():  # ④ 查重
        return jsonify({"error": "用户名已存在"}), 409

    user = User(                                  # ⑤ 创建用户对象
        username=username,
        password_hash=generate_password_hash(password)
    )
    db.session.add(user)                          # ⑥ 标记"待插入"
    db.session.commit()                           # ⑦ 写入数据库

    token = create_access_token(identity=str(user.id))  # ⑧ 签发 token
    return jsonify({"message": "注册成功", "access_token": token}), 201
```

#### ① `request.get_json()`

Flask 自动把 HTTP 请求体里的 JSON 字符串解析成 Python dict。前端发来：

```json
{"username": "zhangsan", "password": "123456"}
```

变成：

```python
{"username": "zhangsan", "password": "123456"}
```

#### ② `.get("key")` vs `["key"]`

| | `data.get("username")` | `data["username"]` |
|------|------|------|
| key 不存在时 | 返回 `None` | 抛 `KeyError` 崩溃 |

用 `.get()` 的原因：前端可能发 JSON 缺字段的不完整请求，不要直接崩掉。

#### ③ 空值检查

```python
if not username or not password:
    return jsonify({"error": "用户名和密码不能为空"}), 400
```

`not ""` = `True`——用户填了空字符串也触发。提前拦截而不是让数据库 `nullable=False` 约束报错，用户看到的是中文提示而非 500 崩溃页。

#### ④ 查重

```python
User.query.filter_by(username=username).first()
```

| 片段 | 含义 |
|------|------|
| `User.query` | 翻开花名册（users 表） |
| `.filter_by(username="zhangsan")` | 找到所有名字是 zhangsan 的记录 |
| `.first()` | 取第一条匹配。没匹配返回 `None` |

返回 `None` = 可以注册（没人占这个名字）。返回 User 对象 = 已存在 → 返回 409。

#### ⑤ `generate_password_hash(password)`

```python
"123456" → generate_password_hash() → "pbkdf2:sha256:600000$abc...一长串乱码"
```

数据库只存乱码，永远不存原文密码。即使数据库泄露，攻击者推不出原始密码。

#### ⑥⑦ `db.session.add()` + `db.session.commit()`

| 步骤 | 类比 |
|------|------|
| `db.session.add(user)` | 扔进购物车（标记"待插入"） |
| `db.session.commit()` | 结账（一次性生成 INSERT SQL 写入 SQLite） |

分两步的原因：一次可能操作多张表，全部标记完再一次性 commit。中间出错可以回滚（rollback），不产生半成品数据。

#### ⑧ `create_access_token(identity=str(user.id))`

用 `JWT_SECRET_KEY` 签发一个 JWT token，把 `user.id` 写入 Payload 的 `sub` 字段。`str()` 是因为参数接受字符串比较稳定。注册完返回 token = 不用重新登录。

### 登录接口

```python
@auth_bp.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({"error": "用户名和密码不能为空"}), 400

    user = User.query.filter_by(username=username).first()

    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({"error": "用户名或密码错误"}), 401

    token = create_access_token(identity=str(user.id))
    return jsonify({"message": "登录成功", "access_token": token}), 200
```

#### `check_password_hash(user.password_hash, password)`

把用户输入的明文密码用同样的算法哈希一次，跟数据库里存的哈希值对比。相同 → `True`。

#### 为什么用户名密码错误不分开提示

```python
if not user or not check_password_hash(...):
    return jsonify({"error": "用户名或密码错误"}), 401
```

| 返回"用户名不存在" | 返回"密码错误" | 返回"用户名或密码错误" |
|---|---|---|
| 攻击者测试 100 个用户名 → 知道哪些已注册 | 攻击者知道某用户存在 | **攻击者永远不知道是名字不对还是密码不对** |

统一返回 401，不泄露任何信息，这是防枚举攻击的标准做法。

---

## 四、删除账号

```python
@auth_bp.route("/api/auth/delete-account", methods=["DELETE"])
@jwt_required()
def delete_account():
    current_user_id = int(get_jwt_identity())
    user = User.query.get(current_user_id)

    ChatHistory.query.filter_by(user_id=current_user_id).delete()

    db.session.delete(user)
    db.session.commit()

    return jsonify({"message": "账号已删除"}), 200
```

### `@jwt_required()` 怎么工作

这是一个**装饰器**——在 `delete_account()` 执行之前拦截请求：

```
请求到达 → 取出 Authorization 头的 token
         → 用 JWT_SECRET_KEY 验签名
         → 签名不对或过期 → 返回 401（delete_account 不执行）
         → 验证通过 → 把解码后的数据存进当前线程上下文 → 执行 delete_account()
```

加了 `@jwt_required()` 的接口必须带 token 才能访问。注册和登录不加——token 还没签发。

### `get_jwt_identity()`

从 token 的 Payload 里读出 `identity` 的值（注册时写入的 `str(user.id)`）。返回字符串，`int()` 转整数。

**为什么用它而不是从请求体里读 username**：如果从请求体读 username，A 用户可以在请求头带上自己的 token，请求体里写 `"username": "B"`——删掉 B 的账号。从 token 拿 id = **只能删自己**。

### `User.query.get(id)`

按**主键**查询——`get(1)` = `SELECT WHERE id=1`。比 `filter_by` 更快（主键自带索引）。

### 为什么要先删聊天记录

```python
ChatHistory.query.filter_by(user_id=current_user_id).delete()  # ① 先删关联数据
db.session.delete(user)                                         # ② 再删用户
db.session.commit()                                             # ③ 一起提交
```

`ChatHistory.user_id` 有外键约束指向 `users.id`。如果先删用户，外键约束会报错——聊天记录还引用着已删除的用户。必须倒序：先解外键依赖，再删主记录。

---

## 五、ChatHistory 模型

```python
class ChatHistory(db.Model):
    __tablename__ = "chat_history"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
```

| 列 | 类型 | 为什么 |
|------|------|--------|
| `user_id` | Integer + ForeignKey | 哪条消息属于哪个用户——外键保证数据一致性 |
| `role` | String(20) | 区分 `"user"` 和 `"assistant"` |
| `content` | **Text**（无上限） | AI 回复可能很长——不能用 `String(80)` |
| `created_at` | DateTime | 消息发送时间。不要 `updated_at`——消息不会修改 |

### 外键（`db.ForeignKey`）

**解决什么问题**：保证 `user_id` 的值必须是 `users` 表里存在的 id。

```
没有外键： user_id=99999 随便插（用户 99999 不存在，数据废了）
有外键：   user_id=99999 → 数据库拒绝
```

在 `auth.py` 删除函数的语境里，这条规则保证了所有 ChatHistory 永远引用一个有效用户——不会出现孤儿记录指向不存在的人。

---

## 六、JWT Token 机制总结

### 为什么需要 token

HTTP 是无状态的——每次请求独立，服务器不记得你是谁。token 让服务器在这个证据上验证你是谁，不需要每次传密码。

### Token 签发（注册/登录）

```
Payload: {"sub": "5", "exp": 未来时间}
  ↓ 用 JWT_SECRET_KEY 混合哈希
签名 → 三段拼接 → 返回给前端
```

### Token 验证（每次请求带 token）

```
@jwt_required() 拦截
  → 从 Authorization 头取出 token
  → 重新用 JWT_SECRET_KEY 算签名
  → 一致 → 放行（delete_account 执行）
  → 不一致 → 401（函数不执行）
```

### Token 下线的真相

**JWT 没有服务端登出**——token 签出去了，服务器不存它，无法主动作废。登出是前端的事：`localStorage.removeItem("token")`，跳回登录页。改了 `JWT_SECRET_KEY` 会让所有旧 token 全部失效——但无差别踢掉了所有人。

### 和 Session 的对比

| | Session | JWT |
|------|------|------|
| 数据存哪 | 服务器内存/Redis | 客户端浏览器 |
| 扩展多台服务器 | 必须搭 Redis 共享 session | 不需要——每台独立验证 |
| 踢人下线 | 即时——删一条 session | 无法单用户下线，除非加黑名单 |
| 选 JWT 的原因 | — | 部署多台服务器不用额外买 Redis |

---

## 七、curl 测试

### curl 是什么

命令行里的浏览器——构造 HTTP 请求、发给服务器、打印返回的原始数据。前端没写时验证后端接口的唯一工具。

### curl 参数速查

| 参数 | 全称 | 干什么 |
|------|------|--------|
| `-X POST` | eXecute method | 指定 HTTP 方法 |
| `-H "Content-Type: application/json"` | Header | 告诉 Flask"请求体里是 JSON" |
| `-d '{"key":"value"}'` | data | 请求体（真正要传的数据） |

### 对应的 Python 写法

```python
requests.post(url, headers={"Content-Type": "application/json"}, json={"key": "value"})
```

curl 和 requests 库是同一条 HTTP 请求在终端和 Python 里的不同表达。你会 requests 就自然会 curl——只是换了一种调用方式。

### 终端中文显示的问题

```
"message": "注册成功"  = "注册成功"（Unicode 编码，不影响功能）
```

### Windows 下的单引号坑

Git Bash 里 `-d '{"key":"value"}'` 可能被错误解析。改用双引号 + 转义：

```bash
curl -X POST http://localhost:5000/api/auth/login -H "Content-Type: application/json" -d "{\"username\":\"test\",\"password\":\"123456\"}"
```

**PowerShell 里的 curl 是假的**——它是 `Invoke-WebRequest` 的别名，语法完全不同。用 Git Bash。

---

## 八、HTTP 方法与状态码

### GET 和 POST 的根本区别

| | GET | POST |
|------|------|------|
| 应该改变服务器状态吗 | 不应该——只读 | 应该——创建/修改 |
| 浏览器地址栏能发吗 | 能（默认行为） | 不能 |
| 浏览器刷新会重发吗 | 安全——随便刷 | 浏览器会警告"重新提交表单" |

注册和登录用 POST 的原因：这些操作修改数据库。如果写成 GET，搜索引擎爬虫扫描链接时会发空注册、浏览器预加载会触发登录——不是你想象中不会有人 GET 你的地址就平安无事。

### 接口用到的状态码

| 状态码 | 含义 | 你的接口里什么时候返回 |
|--------|------|---------------------|
| 200 | 成功 | 登录成功 |
| 201 | 创建成功 | 注册成功 |
| 400 | 请求格式有误 | 用户名或密码为空 |
| 401 | 未认证 | 密码不对 / 没 token |
| 409 | 冲突 | 用户名已存在 |

---

## 九、Python 类与实例（复习）

| | `User`（大写，类） | `user`（小写，实例） |
|------|------|------|
| 是什么 | 数据库表的模板 | 表里的一行记录 |
| 类比 | 空白表格 | 填写了一行的表格 |
| 如何创建 | `class User(db.Model): ...` | `user = User(username="zhangsan")` |

`User` 类定义了"用户有什么属性"（id, username, password_hash...）。`user` 对象是"一个具体的用户"——先诞生在 Python 内存里，`commit()` 后成为数据库里的真实一行。

`db.Model` 是父类——写了保存、查询、删除等所有数据库操作。你继承它就是拿现成功能，只定义自己的列。

---

## 十、数据库操作速查

| 操作 | 代码 |
|------|------|
| 查一条（按主键） | `User.query.get(id)` |
| 查一条（按其他列） | `User.query.filter_by(username="...").first()` |
| 新增一条 | `db.session.add(obj)` → `db.session.commit()` |
| 删除一条 | `db.session.delete(obj)` → `db.session.commit()` |
| 批量删除 | `Model.query.filter_by(...).delete()` |

---

## 十一、`@jwt_required()` 装饰器底层

用你熟悉的 Python 装饰器知识理解：

```python
# 你写的
@jwt_required()
def delete_account():
    ...

# 等价于
def delete_account():
    ...
delete_account = jwt_required()(delete_account)
```

`jwt_required()` 返回一个闭包函数，包装了你的 `delete_account`。包装层做的事：

```
① 从 Authorization 头取出 token
② 用 JWT_SECRET_KEY 验签名
③ 不通过 → return 401（delete_account 不执行）
④ 通过 → 把解码后的数据存进线程局部变量 → 执行 delete_account()
```

`get_jwt_identity()` 从同一个线程局部变量读出 user_id。两个函数不通过参数传递——通过 Flask 内部的"当前线程临时存储"交换数据，跟 `app_context()` 的栈机制是同一个线程局部变量思想。

---

## 十二、.gitignore 规则小结

| 写法 | 效果 |
|------|------|
| `*.log` | 所有 `.log` 文件，任意深度 |
| `node_modules/` | 所有叫 `node_modules` 的文件夹 |
| `/important.log` | 只忽略根目录的 |
| `!文件` | 例外——之前忽略的，保留这个 |
| `Plan/test/` | 忽略整个 `test/` 目录 |
| `Plan/test/**` | 同 `Plan/test/`——递归匹配 |
| `Plan/test/*` | `test/` 下的直接条目（文件和文件夹都匹配） |
| `**/test/` | 任意位置的 `test/` 目录 |

**关键规则**：不以 `/` 开头的规则 = 全局生效（任意深度）。以 `/` 开头 = 只限根目录。

`.gitignore` 规则必须**顶格写**——行首不能有缩进，否则 Git 不认。

---

## 十三、Flask 本质与后端架构

### Flask 本质是什么

**一个 URL → 函数 的映射字典。** Flask 内部维护一张路由表：

```python
{
    "/api/auth/register": register,
    "/api/auth/login": login,
    "/api/auth/delete-account": delete_account,
}
```

请求来了，Flask 做的事就是**查字典**——从 URL 找到对应函数然后调用。其余所有功能（`request.get_json()`、`jsonify()`、`@jwt_required()`）全是为了让这个字典工作得更顺手而存在的助手。

### Werkzeug 是什么

Werkzeug 是一个**独立的 Python HTTP 解析器 + 开发服务器**，不是 Flask 的一部分。Flask 的作者同时写了它，Flask 内部依赖它：

| 层次 | 干什么 |
|------|--------|
| Werkzeug | 解析原始 HTTP 报文 → Request 对象；把 Response 对象序列化成 HTTP 字节流发回浏览器 |
| Flask | 路由派发——查字典找函数、调用函数、返回 Response |

**Flask 不处理 TCP 连接、不解析原始 HTTP 报文——这些全交给 Werkzeug。**

### 一个 HTTP 请求的完整生命周期

```
浏览器发来 HTTP 报文
  → Werkzeug 解析 → Request 对象
  → Flask 创建 request context（"当前处理哪个请求"的标记）
  → app context 自动 push（"当前活跃的 app 是谁"）
  → 匹配路由表 → 调用对应函数（register / login / delete_account）
  → 函数内部：读 request JSON → 查数据库 → 操作数据 → commit → 返回 dict + 状态码
  → Flask 把 dict 封装成 Response 对象
  → request context 销毁
  → Werkzeug 把 Response 序列化成 HTTP 字节流
  → TCP 发送给浏览器
```

### app.py 的本质

**组装，不是实现。** app.py 不写任何业务逻辑——它只做一件事：把散落各处的零件组装成一个能运行的整体：

```python
Config              → 后端所有的设置
db.init_app(app)    → 数据库归你管
CORS(app)           → 跨域的事你来
JWTManager(app)     → Token 的事你来
register_blueprint  → 路由挂好了
app.run()           → 跑
```

注册怎么写、登录怎么验——app.py 一个字不管。**骨架不替代器官——它把它们固定在正确的位置上。**

### 后端没有"主要负责人"

整个后端是一群各自独立的小角色——路由派发的、算密码的、管数据的、签发凭证的——全在一个进程里。Flask 当不上领导——它只是会议桌上传话的人。

### 所有 Web 框架本质一样

| 框架 | 语言 | 路由写法 | 本质 |
|------|------|---------|------|
| Flask | Python | `@app.route("/")` | 字典 |
| FastAPI | Python | `@app.get("/")` | 字典 + 自动类型校验 + 自动生成 API 文档 |
| Spring Boot | Java | `@GetMapping("/")` | 字典 + 依赖注入容器 |

写法不同，核心机制一样——每个请求进来，查一张 URL→函数的映射表，调对应函数。换语言时只需问三个问题：怎么往字典加一条记录？怎么从请求取值？怎么返回 JSON？剩下全是语法糖。

### 为什么 Flask 用装饰器注册路由

**装饰器不是语法糖——是 Python 解释器执行时序的强制执行。**

把 URL 直接写在函数下面可以粗略实现"视觉聚合"，但这依赖程序员手动保证"路由注册必须在 `register_blueprint` 之前"的时间约束。在循环 import 的场景下，`from app import create_app` 会触发 app.py 的导入链，app.py 又回头 `from auth import auth_bp`——此时 auth.py 的函数体还没执行，附在函数下面的 `add_url_rule` 还没被读到。app.py 拿到的 `auth_bp` 是一个路由表为空的蓝图，`register_blueprint` 注册了空壳——之后函数体继续执行，路由才被补上，但蓝图已单向合并完毕，补上的路由永久丢失，URL 静默 404。

装饰器不依赖人的纪律——它在函数定义完成那一刻被 Python 解释器强制执行。这一刻永远早于任何 import 链触发的 `register_blueprint`。写在下面依赖的是人，纪律会被时间打破；装饰器依赖的是 Python 解释器本身——不可破。

---

## 十四、上下文本质

### 上下文是什么

**一个线程局部变量的标记位。** 不存复杂数据，不执行逻辑，不传参数。只回答一个问题："此时此刻，在处理谁？"

| 上下文类型 | 回答什么问题 | 什么时候创建 |
|-----------|------------|-----------|
| 应用上下文 | 当前哪个 Flask app 是活跃的 | `with app.app_context()` 手动创建，或请求到达时自动创建 |
| 请求上下文 | 当前哪个 HTTP 请求正在处理 | 每次请求到达时自动创建，响应后自动销毁 |

### 为什么叫上下文（栈机制）

每个线程有一个独立的栈。push = 当前活跃标记入栈，pop = 标记出栈。单用户时感觉不到栈的存在——只有一个标记，push 一次 pop 一次。多线程时每个线程有自己的栈——各自 push 自己的请求标记，互不污染。你唯一手动用上下文的地方是 `with app.app_context(): db.create_all()`——应用启动前 Flak 还没运行，自动上下文不存在，手动设一次。之后所有请求的上下文管理全部由 Flask 自动完成。

### `@jwt_required()` 是局部钩子

Flask 提供了全局钩子（`before_request` / `after_request`）——所有请求都经过。`@jwt_required()` 复用了相同的拦截原理——在路由函数执行前先验 token，但只在贴上它的路由上生效。注册和登录不需要验证——它们是签发 token 的地方，被保护之前必须有不锁的门。

### 线程局部变量（`threading.local`）

**解决什么问题**：多个 HTTP 请求同时到达时，线程 1 的 `user_id=5` 不能被线程 2 的 `user_id=8` 覆盖。

Python 的 `threading.local` 为每个线程维护独立的存储字典。`@jwt_required()` 验完 token 后把解码结果存入当前线程的局部存储，同一个线程里的 `get_jwt_identity()` 从同一个存储读出 user_id。线程 1 和线程 2 物理上不共享这块内存——操作系统基于当前线程 ID 自动路由到对应的存储区。你的代码里永远是 `get_jwt_identity()` 一行——从不需要传线程 ID。底层机制是线程 ID 作字典键，自动隔离。

### `@jwt_required()` 的值传递路径

```
① @jwt_required() 装饰器
   → 从 Authorization 头取出 token
   → 用 JWT_SECRET_KEY 验签名 → 解码 Payload
   → 把解码结果存入当前线程局部存储

② get_jwt_identity()
   → 从当前线程局部存储读出解码结果
   → 返回 "sub" 字段 → user_id
```

它们之间**不通过函数参数传递——通过线程局部存储交换数据**。

### Python 执行机制与循环 import

**Python 是解释型语言——从上到下，边读边执行**（不同于 C 的先编译后执行）。`def` 创建函数对象但不执行函数体，`if __name__ == "__main__"` 只是普通的 if 语句——读到时执行判断。

**循环 import 链**：

```
auth.py → from models import db, User
  → models.py → from app import create_app
    → app.py → from auth import auth_bp
      → Python 发现 auth.py 已在导入中 → 返回已执行到一半的 auth 模块
      → auth_bp 对象存在（第二行已执行）
      → 但装饰器和路由都还没执行到（指针卡在第三步等 models 返回）
→ app.py 拿到空路由表的 auth_bp → register_blueprint 注册了空壳
→ auth.py 继续执行 → 路由被补上 → 但蓝图已单向合并完毕 → 永久 404
```

**无报错、无堆栈、无日志——只有路由消失了。**

Flask 的作者没有专门为循环 import 做设计，但装饰器在函数定义那一刻执行——这一刻永远早于任何 import 链触发的 `register_blueprint`。写在函数下面依赖的是人的纪律——纪律会被时间打破；装饰器依赖的是 Python 解释器本身的执行机制——不可破。

### 常见的工程解耦策略

不完全解耦循环 import——能做到的通常只是让循环永远不被触发：

- `models.py` 不 import `app.py`——model 的职责是描述数据形状，不需要知道应用入口
- 保持引用方向单向：`app → auth → models`（不回头）
- 出现相互引用时引入第三个模块接收双向依赖，打破直接环

这并不是什么高级架构问题——任何模块在 import 链中出现回头引用时都有这个问题。这是 Python 解释器的循环导入保护在 API 框架与数据库建模之间的交汇处产生的必然冲突。

```
backend/
├── models.py          ✅ User + ChatHistory 模型
├── config.py          ✅ 配置类
├── app.py             ✅ Flask 入口 + 蓝图注册
├── auth.py            ✅ 注册 + 登录 + 删除账号（curl 测试通过）
├── chat.py            待写（聊天接口）
├── requirements.txt   ✅ 依赖清单
└── .env               ✅ 环境变量
```
