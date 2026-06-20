# Flask 聊天接口 — 知识复盘

> 项目：AIChat v1.0  
> 阶段：chat.py 业务接口（流式聊天 + 历史分页）  
> 状态：chat.py 完成并 curl 测试通过  

---

## 一、chat.py 做了什么

```
POST /api/chat  → 接收用户消息 → 拼接历史上下文 → 调用 DeepSeek → 流式返回 → 存入数据库
GET  /api/history  → 查当前用户聊天记录 → 分页返回
```

和 `auth.py` 的区别：聊天接口不是一次返回 JSON——而是**持续几十秒、逐字返回数据流**。技术核心是 Python 生成器（`yield`）和 SSE 协议。

---

## 二、导入部分

```python
from flask import Blueprint, request, jsonify, Response
from openai import OpenAI
```

| 导入 | 用途 | 区别于 auth.py |
|------|------|-------------|
| `Response` | 包装流式生成器——告诉 Flask"这个接口的响应是断断续续的" | auth.py 只用 `jsonify` 一次性返回 |
| `OpenAI` | OpenAI SDK 客户端类——连接 DeepSeek API | chat.py 独有 |

---

## 三、聊天接口主体（前半段）

```python
@chat_bp.route("/api/chat", methods=["POST"])
@jwt_required()
def chat():
    current_user_id = int(get_jwt_identity())
    data = request.get_json()
    user_message = data.get("message", "")

    if not user_message.strip():
        return jsonify({"error": "消息不能为空"}), 400
```

和 `auth.py` 完全一样的开头——读 token、验身份、取 JSON。

```python
    history = ChatHistory.query.filter_by(user_id=current_user_id) \
        .order_by(ChatHistory.created_at.desc()).limit(20).all()
    history.reverse()

    messages = [{"role": msg.role, "content": msg.content} for msg in history]
    messages.append({"role": "user", "content": user_message})
```

**为什么要取最新 20 条再反转**：DeepSeek 需要消息从旧到新排列（自然对话顺序）。但取"最近 20 条"最快的方法是先按时间降序取末 20 行，再 Python 列表反转。如果把 `asc()` 和 `limit(20)` 配对——取到的是最旧 20 条，上下文少了一个月的最新对话。

`[{"role": ..., "content": ...} for msg in history]` — 列表推导式：把 ORM 对象转成 DeepSeek API 需要的 dict 格式。

### `$user_message.strip()`

```python
data.get("message", "")
```

给了默认值 `""`：防止前端漏传 `message` 字段时 `None.strip()` 崩溃。`"".strip()` = `""` → `not ""` = `True` → 返回 400 提示。

---

## 四、生成器函数 `generate()`

### Python 生成器（yield）

```python
def get_numbers():
    yield 1       # 送 1，暂停，等着
    yield 2       # 下次被叫时从这里继续，送 2
    yield 3       # 再下次从这里继续，送 3
```

| | return | yield |
|------|--------|-------|
| 送完数据后 | 函数死亡 | 函数暂停，下次叫继续执行 |
| 能送几次 | 1 次 | 无限次 |
| 你的聊天接口 | 不能用——只能返回一次 | 每个字 yield 一次，总共几百次 |

### 调用 DeepSeek API

```python
client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com/v1"
)
```

`base_url` 改成了 DeepSeek 的地址——SDK 默认连接 `api.openai.com`，改一行就重定向到 DeepSeek。

```python
response = client.chat.completions.create(
    model="deepseek-chat",
    messages=messages,
    stream=True          # ← 核心：不等完整回复，每生成一个字立刻返回
)
```

`stream=False` → DeepSeek 全生成完才一次性返回。`stream=True` → 你收到一个可迭代的流对象，每一秒多一个元素。

### 遍历流 + SSE 格式

```python
for chunk in response:
    word = chunk.choices[0].delta.content    # 取出这一个字
    if word is not None:
        ai_words.append(word)                 # 拼到列表里
        yield f"data: {word}\n\n"            # 立刻发给前端
```

`f"data: {word}\n\n"` 就是 SSE 协议的格式：

```
data: 你

data: 好

data: ！

data: [DONE]
```

浏览器端的 `EventSource` 读到 `data:` 开头的行就触发事件——前端每收到一行就在聊天框里加一个字。没有 `data:` 前缀，`EventSource` 不认识。

### 异常处理

```python
try:
    word = chunk.choices[0].delta.content
    ...
except:
    yield "data: [ERROR]\n\n"
```

`try` 在 `for` 循环**内部**——每个 chunk 独立处理。一个 chunk 解析失败不影响前后 chunk。DeepSeek 网络超时、API 限流都走 `except`，不会让整个聊天接口崩掉。

### 流结束后存数据库

```python
yield "data: [DONE]\n\n"

reply_text = "".join(ai_words)    # ["你","好","！"] → "你好！"
ai_message = ChatHistory(user_id=current_user_id, role="assistant", content=reply_text)
db.session.add(ai_message)
db.session.commit()
```

存数据库放在 `for` 循环**外面**——所有 chunk 收完之后一次性存。放在循环里会反复存（200 个 chunk = 200 条半成品记录）。

### 返回流式响应

```python
return Response(generate(), mimetype="text/event-stream")
```

`Response` 包装生成器——Flask 遍历 `generate()`，每 `yield` 一段就通过 HTTP 发送一段。`mimetype="text/event-stream"` 告诉浏览器"这是 SSE 流，别当普通 JSON 解析"。

**`generate()` 必须加括号**——不加括号传的是函数引用，不是生成器对象。会报 `TypeError: 'function' object is not iterable`。

---

## 五、SSE vs 普通 HTTP 响应

| | 普通 JSON 接口（注册/登录） | SSE 流式接口（聊天） |
|------|------|------|
| 返回几次 | 1 次 | N 次（逐字） |
| Flask 工具 | `jsonify()` | `Response(生成器, mimetype="text/event-stream")` |
| HTTP 传输方式 | `Content-Length`（定长） | `Transfer-Encoding: chunked`（分块） |
| 前端接收 | `axios.post()` → 拿到完整 JSON | `EventSource` → 每次 `data:` 触发一次事件 |
| 后端实现 | `return 字典` | `yield f"data:..."` |

---

## 六、历史记录 + 分页

```python
@chat_bp.route("/api/history", methods=["GET"])
@jwt_required()
def history():
    current_user_id = int(get_jwt_identity())
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

    pagination = ChatHistory.query.filter_by(user_id=current_user_id) \
        .order_by(ChatHistory.created_at.desc()) \
        .paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        "messages": [{"role": m.role, "content": m.content, "time": m.created_at.isoformat()}
                     for m in pagination.items],
        "page": pagination.page,
        "pages": pagination.pages,
        "total": pagination.total
    }), 200
```

### `request.args` — 读取 URL 参数

```
GET /api/history?page=2&per_page=10
                  ↑          ↑
              request.args  request.args
```

| 调用 | URL 有参数时 | URL 没参数时 |
|------|-----------|-----------|
| `request.args.get("page", 1, type=int)` | 返回 `2`（整数） | 返回 `1`（默认值） |
| `request.args.get("per_page", 20, type=int)` | 返回 `10`（整数） | 返回 `20`（默认值） |

`type=int`：Flask 自动把字符串 `"2"` 转成整数 `2`。

`request.args` 和 `request.get_json()` 是同一个 `request` 对象的不同属性。URL 参数从网址问号后面取，JSON 从请求体取。

### `.paginate()` — SQLAlchemy 分页

```python
.paginate(page=2, per_page=10, error_out=False)
```

内部发两条 SQL：

```sql
SELECT COUNT(*) FROM chat_history WHERE user_id = 5;        -- 算总数
SELECT * FROM chat_history WHERE user_id = 5
    ORDER BY created_at DESC LIMIT 10 OFFSET 10;             -- 取第 2 页（跳过前 10 条）
```

数据库不认识"第几页"——只认识 **OFFSET（跳过多少行）+ LIMIT（取多少行）**：

```
页码 → OFFSET 换算：OFFSET = (page - 1) × per_page
第 1 页 → OFFSET 0
第 2 页 → OFFSET 20
第 3 页 → OFFSET 40
```

`error_out=False`：请求的页数超出总页数时返回空列表而不是抛 404。用户手动改 URL 到 `?page=999` 不应该崩掉接口。

### `pagination` 对象的属性

```python
pagination.items   # ← 当前页数据（Python 对象列表，20 条）
pagination.page    # ← 当前是第几页（整数）
pagination.pages   # ← 总共多少页（整数）
pagination.total   # ← 总共多少条记录（整数）
```

### `isoformat()` — datetime 转字符串

```python
m.created_at.isoformat()   # "2026-06-17T15:30:00"
```

Python datetime 对象不能被 `jsonify` 序列化——直接传会抛 `TypeError`。`isoformat()` 把时间转成 ISO 8601 标准字符串，前端 JavaScript 的 `new Date()` 能直接解析。

### 返回的 JSON 结构

```json
{
  "messages": [
    {"role": "user", "content": "你好", "time": "2026-06-17T15:30:00"},
    {"role": "assistant", "content": "你好！", "time": "2026-06-17T15:30:05"}
  ],
  "page": 1,
  "pages": 5,
  "total": 98
}
```

`messages` 填聊天框，`pages` + `total` 算翻页器。

---

## 七、常见 bug 模式

### 1. 变量名重构残留

```python
ai_words = []           # ← 改了名叫 ai_words
ai_message.append(x)    # ← 旧名字残留 → NameError
```

改了一个变量名之后全局搜旧名字，确认没有残留引用。

### 2. 副作用路径未验证

curl 返回 200 + 流式正常 ≠ 数据库正确。每完成一个接口，追查一次数据库里是不是只有你预期的那条记录。验证方法：跑完聊天后立即跑 `GET /api/history`，看 `role` 是不是 `"assistant"`、`content` 是不是完整的。

### 3. 数据库存放在了错误的位置

存数据库放在循环内 → 循环 200 次存 200 条。放在 `finally` 里 → 每个 chunk 的 `finally` 都触发一次——仍旧存 200 条。放在 `for` 循环外面、所有 chunk 收完之后——只存 1 条完整记录。这才是正确的。

---

## 八、聊天接口数据流（完整链路）

```
用户发 "你好"
  ↓
Flask 收到 POST /api/chat
  ↓ jwt_required 验身份
  ↓
查 ChatHistory 表 → 拿最近 20 条历史 → reverse → 拼成 messages 列表
  ↓
存用户消息到 ChatHistory 表（user 角色）
  ↓
client.chat.completions.create(stream=True) → DeepSeek 逐 token 返回
  ↓
for 循环遍历 stream：
  chunk.choices[0].delta.content → 取出一个字
  ↓
  try → yield f"data: 字\n\n" → Flask 发送 chunk → 浏览器 EventSource 收到 → 拼到聊天框
  ↓ except → yield "data: [ERROR]\n\n"
  ↓
所有 chunk 遍历完毕 → yield "data: [DONE]\n\n"
  ↓
"".join(ai_words) → 拼成完整 AI 回复 → 存入 ChatHistory（assistant 角色）
  ↓
连接关闭
```

---

## 九、当前项目文件状态

```
backend/
├── models.py          ✅ User + ChatHistory（user_id 索引已建）
├── config.py          ✅ 配置类
├── app.py             ✅ 入口 + 蓝图注册（auth + chat）
├── auth.py            ✅ 注册 + 登录 + 删除 + 修改密码
├── chat.py            ✅ 流式聊天 + 历史分页
├── requirements.txt   ✅ 依赖清单
└── .env               ✅ 环境变量

已实现接口：
POST   /api/auth/register       ✅
POST   /api/auth/login          ✅
DELETE /api/auth/delete-account ✅
POST   /api/auth/change-password ✅
POST   /api/chat                ✅
GET    /api/history             ✅
```
