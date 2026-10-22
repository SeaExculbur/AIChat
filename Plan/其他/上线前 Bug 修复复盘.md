# 上线前 Bug 修复复盘

> 项目：AIChat v1.0
> 日期：2026-10-22
> 内容：五个上线前阻断项的修复过程——会话越权、删账号孤儿行、迁移读错库、更新时间不刷新、SSE 换行；以及前端注册流程收尾。附各自的验证方法，和一个反复出现的模式："改了一半"

---

## 一、修复清单

| # | 问题 | 类型 | 根因一句话 | 验证方式 | 结果 |
|---|---|---|---|---|---|
| 1 | `/api/chat` 不校验会话归属 | 安全（越权） | 客户端传来的 `conversation_id` 被当成了可信事实 | 用不存在的会话 id 发消息 | ✅ 404 + JSON |
| 6 | `delete_account` 留孤儿行 | 数据完整性 | 只删了消息，没删会话；SQLite 外键默认关闭所以测不出 | 先造会话再删账号，查三张表 | ✅ 三表全空 |
| 5a | Alembic 迁移不读 `DATABASE_URL` | 部署链 | online 分支读的是 ini 里写死的 SQLite 路径 | 给一个错误的 `DATABASE_URL` 看会不会失败 | ✅ connection refused |
| 3 | `Conversation.updated_at` 永不刷新 | 功能 | `onupdate` 只在 UPDATE 时触发，而发消息从不碰那一行 | 发消息后比对 `created_at` / `updated_at` | ⬜ 代码已改，待实测 |
| 4 | SSE 帧里含 `\n` 会丢内容 | 功能（前后端） | 一个 `data:` 字段只能承载一行 | 让 AI 输出代码块，看换行是否完整 | ⬜ 代码已改，待实测 |
| 前端 | 注册后存了 `token=undefined` | 功能收尾 | localStorage 只能存字符串，`undefined` 变成 `"undefined"` | 浏览器注册一次，看是否停在注册页 | ✅ 构建 + 接口 + 代理链路已验证，页面交互待手工确认 |

---

## 二、#1 会话越权——客户端给的 id 是"声明"，不是"事实"

### 问题

```python
conversation_id = data.get("conversation_id")   # 客户端说多少就是多少

if conversation_id is None:
    ...新建会话...
# 否则：直接往下用，没有任何检查
```

攻击者 B 只要填一个属于 A 的会话 id，就能把消息**写进 A 的会话**：

```
POST /api/chat
Authorization: Bearer <B自己的token>          ← 身份是真的
{"message": "垃圾内容", "conversation_id": 7}   ← 会话 id 是 A 的
```

而后端完全没有验证"这个会话是不是你的"。

### 为什么这个 bug 容易犯

那段逻辑读起来**非常自然**：

```python
if conversation_id is None:
    新建
# 有 id 就直接用
```

它在"只有你一个人用"的前提下**完全正确**——你的前端传的 id 永远是你自己的。**这个假设在本地开发时永远成立，所以测试时永远发现不了它。**

### 修法

把"声明"和"身份"绑进**同一次查询**：

```python
    else:
        conv = Conversation.query.filter_by(id=conversation_id, user_id=current_user_id).first()
        if conv is None:
            return jsonify({"error": "会话不存在"}), 404
```

**两个要点**：

1. **一次查询同时约束 id 和 user_id**——查得到才是你的，查不到就是 404
2. **"会话不存在"和"会话不属于你"返回同一个 404**——不要写成"这个会话不是你的"，那等于告诉攻击者"这个 id 存在，只是不归你"，是信息泄露

### 修的时候踩的坑：冒号在引号里

第一版写成了：

```python
return jsonify({"error:" "会话不存在"}), 404
```

**冒号在引号里面**。Python 会把相邻的字符串字面量自动拼接：

```python
{"error:" "会话不存在"}
      ↓
{"error:会话不存在"}        ← 这是一个【集合】，不是字典
      ↓
jsonify(集合) → TypeError → 500
```

**这个错误语法上完全合法**，编辑器不会报错，只有运行到那一行才炸。

### 最值得记住的一点：这个分支平时根本走不到

正常测试时，用自己的会话发消息，`conv` 永远查得到，`if conv is None` 永远为 False——**那段代码从写下的那一刻起就没被执行过。**

> **未执行的代码可能藏着 bug。而只有走到那个分支，才会暴露。**

**而"越权测试"恰好就是走到那个分支的唯一方式**——**验证方法和测试方法，是同一个东西。**

---

## 三、#6 删账号留下孤儿行——按依赖的拓扑序删

### 问题

```python
ChatHistory.query.filter_by(user_id=current_user_id).delete()

db.session.delete(user)
db.session.commit()
```

只删了聊天记录，**没删会话**。

### 为什么 SQLite 上测不出来

```
SQLite：外键约束【默认关闭】
    → 删 user 时不检查引用
    → 静默留下 conversations 里的孤儿行，不报错

PostgreSQL：外键约束【强制】
    → 删 user 时发现还有 conversations 引用它
    → IntegrityError → 500
```

**这是"本地一片祥和、上线第一天上演"的典型。**

### 修法：顺序是硬性的

```
chat_history.conversation_id  ──┐
                                ├──→ conversations.id
conversations.user_id  ─────────┼──→ users.id
chat_history.user_id   ─────────┘
```

**被引用的最后删，引用别人的最先删**：

```python
ChatHistory.query.filter_by(user_id=current_user_id).delete()
Conversation.query.filter_by(user_id=current_user_id).delete()
db.session.delete(user)
db.session.commit()
```

顺序反了（先删 Conversation）→ `chat_history.conversation_id` 还引用着它 → 同样被拒。

### 验证：必须先造数据

```bash
# ① 删除前：确认这个用户确实有一条会话
conversations: [(5, 'verify conv')]

# ② 删账号
DELETE /api/auth/delete-account → 200

# ③ 删除后：三张表都应该空
users: []   conversations: []   chat_history: []
```

**"先造数据"这一步不能省**：

```
如果被删的记录本来就不存在
    → 删完查表也是空的
    → 但【证明不了】删除逻辑对不对
```

> **"空结果"和"正确结果"看起来一样，但含义完全不同。**

### 一个更彻底的方案（当时没做）

外键定义时加 `ondelete="CASCADE"`，删 user 时数据库自动清理引用它的行。

| | 手动删（当前） | CASCADE |
|---|---|---|
| 优点 | 显式、可控、不会误删一大片 | 省事、**不会漏** |
| 缺点 | **容易漏**（就是这个 bug） | 一次删除悄悄带走一大片 |
| 成本 | 3 行 | 要写迁移改外键约束 |

`conversations` 和 `chat_history` 完全从属于 user——**这种"从属关系"是 CASCADE 的典型适用场景**。将来表结构大改时可以一起考虑。

---

## 四、#5a 迁移读到错误的库——最阴的一个

### 问题：同一个文件里，两个分支行为不一样

```python
# run_migrations_offline()  第 51 行
url = os.getenv("DATABASE_URL") or config.get_main_option("sqlalchemy.url")
      ↑ 读了环境变量 ✔

# run_migrations_online()   第 70 行
connectable = engine_from_config(
    config.get_section(config.config_ini_section, {}),   ← 只读 ini 里写死的路径
    prefix="sqlalchemy.",
    poolclass=pool.NullPool,
)
```

**写的人显然想到了 `DATABASE_URL`，但只改在 offline 分支**——而实际执行迁移走的是 online 分支。

### offlne 和 online 是二选一，不是"两边"

```
alembic upgrade head          → online，真的连库、真的执行
alembic upgrade head --sql    → offline，【不连库】，只把 SQL 打印出来
```

offline 模式的用途是"生成 SQL 文本给 DBA 审阅"或"在没有数据库驱动的环境里产出脚本"，所以它本来就不连库，读 URL 只是为了知道按哪种方言生成 SQL。

**真正"不一样"的是这两个进程**：

```
Flask 应用    →  读 DATABASE_URL（config.py）      →  PostgreSQL
Alembic 迁移  →  读 alembic.ini 的 sqlalchemy.url  →  SQLite
                     ↑ 它们必须指向同一个库
```

### 后果比想象的严重

不是"漏了一个 `is_active` 列"——**是 Postgres 上整个 schema 都没建**：

```
docker compose exec flask alembic upgrade head
    ↓ 打到容器内 SQLite，建表加列一切"成功"
    ↓
Postgres 里：一张表都没有
    ↓
应用启动 → relation "users" does not exist → 500
    ↓
而且下次再跑，它读那本错的账，说"已是最新版本"
```

**"跑到了错误的账本上"比"没跑"难查得多**——因为命令骗你说成功了（exit code 0）。

### 修法

```python
def run_migrations_online() -> None:
    url = os.getenv("DATABASE_URL") or config.get_main_option("sqlalchemy.url")
    connectable = create_engine(url, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        ...
```

**import 也要跟着换**：`engine_from_config` → `create_engine`（旧的删掉，别留死 import）。

### 我改的时候，也"改了一半"

第一版改成了：

```python
    connectable = create_engine(
        url,                                              # ← url 从未定义
        config.get_section(config.config_ini_section, {}), # ← create_engine 不收这个
        prefix="sqlalchemy.",                              # ← 也不收
        poolclass=pool.NullPool,
    )
```

**只换了函数名，没注意到三件事**：`url` 没定义、两个旧参数不属于新 API。

**两个 API 的参数结构完全不同**：

```python
engine_from_config(config_dict, prefix="sqlalchemy.")   # 吃配置字典，自己去里面找 url
create_engine(url)                                      # 直接吃 URL 字符串
```

### 验证：故意给一个错误的配置

```powershell
$env:DATABASE_URL = "postgresql://x:x@127.0.0.1:1/x"
venv/Scripts/alembic.exe current
Remove-Item Env:DATABASE_URL
```

| 输出 | 结论 |
|---|---|
| `connection refused` | ✅ 修好了——它真的在读环境变量 |
| 正常打印版本号 | ❌ 没修好——还在用 ini 里的 SQLite |

> **正常情况下，修好和没修好看起来一模一样**（本地开发时两者指向同一个 SQLite 文件）。**只有给它一个"错误的地址"，才能看出它到底在读谁。**

**⚠️ Windows PowerShell 设完环境变量必须清掉**：`load_dotenv()` 默认**不覆盖**已存在的环境变量，残留的 `DATABASE_URL` 会污染后面所有 Python 进程。

---

## 五、#3 updated_at 不刷新——"机制没被触发"和"功能不存在"是两件事

### 直觉判断：没调取时间的函数？

`models.py` 里明明配了：

```python
updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())
```

`onupdate` 会在**这一行被 UPDATE 时**自动把值设成数据库的 `now()`。

**所以"取时间"这件事它已经包了，不需要手动调函数。**

### 真正的原因：那一行从来没被 UPDATE 过

```
发一条消息实际发生的事：
    INSERT INTO chat_history (...)      ← 写消息
    （结束）

    UPDATE conversations ...            ← 这一步从未发生
```

**`onupdate` 挂在 `conversations` 上，可你根本没去动那一行**——它没有机会执行。

> 类比：走廊装了"开门自动亮灯"。灯一直没亮——**不是传感器坏了，是你没开过那扇门。**

### 修法

```python
db.session.add(user_msg_record)
conv.updated_at = db.func.now()      # ← 让这一行进入"已修改"状态
db.session.commit()
```

### 为什么用 `db.func.now()` 而不是 `datetime.now()`

```python
conv.updated_at = datetime.now()      # Python 进程取时间
conv.updated_at = db.func.now()       # 数据库取时间  ← 更好
```

- **时区一致性**：`server_default` 用的是数据库的时钟，用 Python 时间会混入两套时区
- **多机时钟偏差**：将来 Flask 跑在多个容器里，各自的时钟可能差几秒——**时间应该是"写进数据库那一刻"，不是"应用进程觉得那一刻"**

### 背后的设计取舍：冗余字段的责任边界

"最后更新时间"有两种存法：

| | 冗余字段（当前） | 派生（从 chat_history 算） |
|---|---|---|
| 写的时候 | 多一次 UPDATE | 只写消息 |
| 读的时候 | 直接查，快 | 要 JOIN / 子查询，慢 |
| 一致性 | **可能忘记维护** | 天生一致 |

会话列表是**高频读、低频写**，所以选冗余字段是对的 ✔ **代价是：这条冗余的责任，落在每一个写入口上——漏一个就退化。**

---

## 六、#4 SSE 换行——一份协议，两端必须同时改

### 机制

后端每帧：

```
data: <一个 token>\n\n
```

如果 token 里含换行（代码块、列表），实际发出去的是：

```
data: 第一行
第二行

```

前端按 `\n` 切分：

```
"data: 第一行"   → 以 "data: " 开头 → 当正文 ✔
"第二行"         → 不以 "data: " 开头 → 跳过 ✘
```

**后半截丢失。** AI 输出代码块时"糊成一坨"就是这个原因。

### 修法：让每一帧都是 JSON

**后端**：

```python
yield f"data: {json.dumps(word)}\n\n"
```

`json.dumps("a\nb")` 输出 `"a\\nb"`——换行被转义成两个字符，不再是真正的换行。

**前端**：

```js
const raw = line.slice(6)
if (raw === '[DONE]') break
if (raw === '[ERROR]') throw new Error('SSE error')

const payload = JSON.parse(raw)        // 首帧是对象，正文帧是字符串

if (isFirstChunk) {
  isFirstChunk = false
  if (payload && typeof payload === 'object' && payload.conversation_id) {
    handleNewConversation(payload.conversation_id, payload.title)
    continue
  }
}

messages.value[aiIndex].content += payload
```

### 为什么 JSON 比手工转义好

还有一种做法是 `word.replace("\n", "\\n")`——但 JSON 更好：

```
首帧的 meta：已经是 JSON ✔
改完之后：   所有帧都是 JSON ✔  → 帧协议统一
```

而且 `json.dumps` 处理的不只是换行——**引号、反斜杠、控制字符、emoji 编码，它全都管**。手工替换只管得了换行一种。

### 提交粒度：这两处必须在同一个 commit

```
后端发 JSON、前端当纯文本拼  → 气泡里出现 "你好"（带引号）
后端发纯文本、前端 JSON.parse → 解析失败
```

**单独提交任何一个，那一刻的代码都是坏的。** "可工作的状态"是 commit 的基本要求。

---

## 七、前端注册流程——三个层层叠加的小错

### ① 存了 `undefined`

```js
localStorage.setItem('token', response.data.access_token)   // access_token 现在是 undefined
router.replace('/chat')
```

**localStorage 只能存字符串**，所以 `undefined` 被存成了 `"undefined"`——**五个字母**。

路由守卫只判断真假：

```js
if (to.path === '/chat' && !token) { next('/login') }
```

`"undefined"` 是真值 → **放行** → 请求带 `Bearer undefined` → 401 → 跳回登录。

**用户感受**："注册成功后闪了一下聊天页，又被踢回来了。"

> **"存了一个坏值"比"没有值"更糟——因为它能通过真值检查。**

### ② `.value` 漏了两次

```js
errorMessage = ''        // ✘ 把 ref 对象换成了字符串
successMessage = ''      // ✘
```

`ref('')` 返回的不是字符串，而是一个**包装对象** `{ value: '' }`——Vue 需要在读写时拦截才能触发界面更新，而 JS 的原始值没法被拦截，所以必须包一层。

**为什么会炸**：`const` 声明的标识符不能重新赋值 → `TypeError: Assignment to constant variable`。

**更糟的是它被 try/catch 吞了**：

```
try {
    successMessage.value = '注册成功'    ✔ 提示设上了
    errorMessage = ''                   ✘ TypeError
} catch (error) {
    errorMessage.value = '注册失败，请重试'   ← 显示了失败
    successMessage = ''                       ✘ 又抛，这次没人接
}
```

**结果：账号注册成功了，界面说失败了。** 用户再注册一次 → 409「用户名已存在」→ 更困惑。

（用 `const` 是好事——它让错误**立刻**以 TypeError 暴露。写成 `let` 只会把 ref 悄悄换成字符串，更难查。）

### ③ 提示没清干净——清理要放在唯一入口

```js
const handleRegister = async () => {
  errorMessage.value = ''          // ← 只清了错误提示
  if (password !== cfm_password) {
    errorMessage.value = '密码不一致'
    return                          // ← 提前 return，根本没走到 catch
  }
  ...
  } catch (error) {
    successMessage.value = ''       // ← 清理加在了这里
  }
}
```

**提前 return 的路径绕过了清理** → 上次的成功提示还挂着 → **一绿一红同时显示**。

**修法：把清理挪到函数入口**：

```js
errorMessage.value = ''
successMessage.value = ''          // ← 每次提交都从干净状态开始
```

> **清理状态要放在"唯一入口"，而不是"每个出口"。**
>
> 放在每个分支里 = 每新增一个分支就要记得再清一次（这次就漏了 `return` 那条）。
> 放在入口 = 只有一个地方要记得，后面怎么写都安全。

**这和"数据库约束放在数据库层"是同一个思路：把保证放在唯一的、必经的位置，而不是散落在每个调用点。**

---

## 八、这次反复出现的一个模式："改了一半"

同一个失败模式，在三个完全不同的地方出现了：

| 出现位置 | "改了的那一半" | "漏掉的那一半" |
|---|---|---|
| **Alembic env.py**（原作者） | offline 分支读了 `DATABASE_URL` | online 分支没读 |
| **我修 env.py 时** | 把 `engine_from_config` 换成了 `create_engine` | 没加 `url = ...`，没删旧的参数 |
| **Register.vue 的清空逻辑** | catch 里清了成功提示 | 前端校验提前 return 的路径没清 |

**成因是同一个**：做局部替换时，注意力集中在"正在改的那个点"，而**和它配套的其他点**在视野之外。

**防线只有一个**：**改完立刻跑**。让错误暴露，而不是靠"再看一眼应该没问题"。

---

## 九、验证方法学

这次摸索出几条可复用的：

### ① 故意给错误的配置，看它会不会失败

```bash
DATABASE_URL="postgresql://x:x@127.0.0.1:1/x" alembic current
```

**正常情况下，"读了配置"和"用了默认值"看起来一模一样**——只有给一个错误的输入，才能区分。

### ② 验证"删除"之前，先让被删的东西存在

空结果 ≠ 正确结果。先造数据，再删，再查。

### ③ 构建通过 ≠ 运行时正确

`npm run build` 能发现语法和模板错误，但**发现不了** `errorMessage = ''` 这类**语义错误**（它语法完全合法）。
**只有真的点一下才会炸。**

### ④ "网络链路"和"浏览器交互"要分开验

这次的注册功能：
- **链路**（前端 5173 → Vite 代理 → Flask → 201）→ 可以用 curl 验证 ✔
- **交互**（提示显示、页面不跳转）→ 只能在浏览器里点，curl 验证不了 ✔

**分开验的好处**：出问题时能直接定位是"网络/后端"还是"前端渲染"。

### ⑤ 提交前问一句：这个 commit 单独拿出来，代码能工作吗？

`chat.py` 改 SSE、`Chat.vue` 也要改——**必须同一个 commit**。分开提交的话，中间那一刻代码是坏的。

---

## 十、遗留

| # | 问题 | 状态 |
|---|---|---|
| 3 | `updated_at` 刷新 | 代码已改，**待实测**（发消息后比对时间） |
| 4 | SSE 换行 | 代码已改，**待实测**（让 AI 输出代码块） |
| 前端 | 滚动加载历史分页 | 未做（`hasMore` / `currentPage` 有状态，模板无 `@scroll`） |
| 部署 | 域名解析、HTTPS、备案号页脚、公安联网备案 | 备案已通过，等待部署 |

---

## 附：这次改动的文件

```
backend/chat.py                  #1 归属校验  #3 updated_at  #4 JSON 帧
backend/auth.py                  #6 删账号清理会话
backend/alembic/env.py           #5a online 分支读 DATABASE_URL
backend/models.py                #  仅注释
frontend/src/views/Chat.vue      #4 JSON 解析
frontend/src/views/Register.vue  #  注册流程收尾
```
