# SSE 流式接收与打字机效果

> 项目：AIChat v1.0  
> 日期：2026-07-10  
> 覆盖：fetch 用法、ReadableStream、SSE 解析、Vue v-if/v-for 优先级、TextDecoder、打字机效果实现  

---

## 一、fetch——浏览器原生的 HTTP 客户端

### 和 axios 的对比

| | fetch | axios |
|--|-------|-------|
| 来源 | 浏览器内置 C++ API | npm 包（底层也调 fetch） |
| 返回值 | `Promise<Response>` | `Promise<AxiosResponse>` |
| 非 2xx 时 | 不抛异常——手动检查 `response.ok` | 自动抛异常进 catch |
| 流式支持 | ✅ `response.body.getReader()` | ❌ 支持差——SSE 场景不用 axios |
| JSON 自动解析 | ❌ 需手动 `.json()` | ✅ 自动解析到 `.data` |

### 基本用法

```js
const response = await fetch('/api/chat', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`
  },
  body: JSON.stringify({ message: text })
})

if (!response.ok) throw new Error(`HTTP ${response.status}`)
```

`await` 不是在等"fetch 把报文发出去"——是等**整个 HTTP 往返走完**（TCP 连接 → 发送 → 后端处理 → 响应回到浏览器）。

---

## 二、Response 对象——HTTP 响应在 JS 里的投影

`await fetch(...)` 兑现后得到一个 `Response` 对象：

| 属性/方法 | 类型 | 干什么 |
|----------|------|--------|
| `response.ok` | `boolean` | 状态码 2xx → true，否则 false |
| `response.status` | `number` | HTTP 状态码——200、401、500 |
| `response.body` | `ReadableStream` | 响应体的流式读取器工厂 |
| `response.json()` | `Promise` | 一次性把响应体解析成 JS 对象（登录/注册用） |
| `response.headers` | `Headers` | 后端返回的 HTTP 响应头 |

聊天接口用 `.body.getReader()`——流式读取。登录/注册用 `axios.post(...).data`（等价于 `response.json()`）——一次性解析 JSON。

---

## 三、ReadableStream——逐块读取 TCP 字节流

### 为什么不能一次读完

SSE 流式响应跨度几十秒，后端`yield f"data: {word}\n\n"`不断产生新数据。必须边收边显示——收到一个字立刻追加到气泡，不等到最后。

### 三个关键对象

```js
const reader = response.body.getReader()    // ① 逐块读取器
const decoder = new TextDecoder()            // ② 字节 → 字符串解码器
let buffer = ''                              // ③ 不完整行的缓冲区
```

#### ① getReader——逐块读取器

`reader.read()` 每次返回 `{ done: boolean, value: Uint8Array }`：
- `done` — 流结束为 true
- `value` — 这次读到的原始字节块

`{ done, value }` 是 **JS 解构赋值**——从返回的对象里直接掏出同名属性，等价于 Python 里读 dict 后手动取 key 的值。花括号本身不是对象——是解构语法。

#### ② TextDecoder——字节解码器

UTF-8 中一个中文占 3 字节。`decoder.decode(value, { stream: true })`：
- 解码字节成 JS 字符串
- `{ stream: true }` — 告诉解码器"还有后续数据，多字节字符可能还没到齐，先把这一批能解码的拼出来"——防止一个 UTF-8 字符被切在两个块导致乱码

#### ③ buffer——半成品暂存区

TCP 分块是随机的——一次 `read()` 可能拿到一行的前半个字。`buffer` 把半行留在本地直到拼完整行再处理。

```js
buffer += decoder.decode(value, { stream: true })
const lines = buffer.split('\n')     // 按换行符切
buffer = lines.pop()                 // 最后一段是半行，留下次拼
for (const line of lines) { ... }    // 完整的行进循环
```

---

## 四、SSE 解析——切 "data:" 前缀

后端每 yield 一次就是一个 SSE 事件，格式固定：

```
data: 你\n\ndata: 好\n\ndata: ！\n\ndata: [DONE]\n\n
```

### 解析步骤

```js
const line = lines[i].trim()                    // 去首尾空白
if (!line.startsWith('data: ')) continue        // 不是 SSE 数据行 → 跳过
const word = line.slice(6)                      // 切掉 "data: " 得到真实文本

if (word === '[DONE]') break                    // 流结束信号
if (word === '[ERROR]') throw new Error('SSE error')  // 异常信号

messages.value[aiIndex].content += word         // 追加到 AI 气泡
```

`.slice(6)` — 切掉前 6 个字符（`"data: "` 的长度），余下部分是后端 yield 的字。

---

## 五、打字机效果——逐字追加到气泡

### 时间线

```
① push 用户消息 → 蓝色气泡上屏
② push AI 占位 → 空壳 { role: 'assistant', content: '' } → v-if 过滤，不画
③ isWaiting = true → 三点闪烁

④ while(true) 循环逐块读 SSE：
   → 收到 "你" → content = "你" → v-if 不再过滤，气泡出现
   → 收到 "好" → content = "你好" → 气泡文字自动变长
   → 每次追加后 await scrollToBottom() → 自动滚到底
   → [DONE] → break

⑤ finally: isWaiting = false → 三点消失
```

### 关键设计：空占位 + 过滤

AI 占位有双重用途：给 SSE 流一个已存在的气泡 index（`aiIndex`）用来动态追加文字；`v-if="msg.content !== ''"` 保证只有真正有内容时才画出来。占位同时作为追加目标和视觉过滤器的区分条件在同一个 `content` 字段上完成。

---

## 六、v-if 与 v-for 优先级——Vue 2 vs Vue 3

| | Vue 2 | Vue 3 |
|--|-------|-------|
| 优先级 | `v-for` 优先 | `v-if` 优先 |
| `v-if="msg.content !== ''"` | `msg` 存在，能跑 | `msg` 未定义 → 崩溃 |

### Vue 3 规则

`v-if` 不能直接和 `v-for` 写在同一个元素上——`v-if` 先执行，循环变量还没出生。

### 解决方案：`<template>` 透明中介

```html
<template v-for="(msg, index) in messages" :key="index">    ← v-for 在 template 上
  <div v-if="msg.content !== ''" :class="...">                ← v-if 在里面的 div 上
    <p>{{ msg.content }}</p>
  </div>
</template>
```

`<template>` 自己不出现在 DOM 里——只托管 `v-for`，让 `v-for` 和 `v-if` 错开层级，各自独立执行。先循环产虚拟节点 → 在内层 div 上 v-if 判断 → 通过就画，不通过就跳过。

---

## 七、状态守卫与并发控制

### isWaiting 门卫

```js
if (isWaiting.value) return   // 正在等 AI 回复 → 禁止发新消息
```

防止用户在 AI 回复期间连续发送多条消息。底层原理：`await fetch` 期间 JS 主线程被释放（异步思想），用户仍可以点击 "发送" 按钮——第二次 `sendMessage` 从 `isWaiting` 门卫处被拦截。

### catch + finally 清理链

```js
try { ... SSE 流式读取 ... }
catch (error) {
  // AI 回复为空 → 删掉占位气泡
  if (messages.value[aiIndex] && !messages.value[aiIndex].content) {
    messages.value.pop()
  }
}
finally {
  isWaiting.value = false   // 无论成败，释放门卫
}
```

---

## 八、其他速记

| 知识点 | 一句话 | 用途 |
|--------|--------|------|
| `JSON.stringify(obj)` | JS 对象 → JSON 字符串（等于 Python `json.dumps`） | HTTP 请求体只能传字符串 |
| `response.ok` | 浏览器 C++ 层解析 HTTP 响应后填的布尔值 | 200-299 → true，否则 false |
| `?.` 可选链 | `messages[messages.length-1]?.content`——消息列表空时不崩溃 | 防御空数组访问 |
| `&&` 短路与 | 前半 false 后半不执行 | 避免读 undefined 的属性 |
| `nextTick` | 等 Vue 清空 DOM 更新队列 | 新气泡画完后再读 scrollHeight，确保滚底准确 |
| `scrollHeight vs scrollTop` | `scrollTop = scrollHeight` 把滚动条拖到底 | 让最新消息始终可见 |
| `const { done, value } = await reader.read()` | JS 解构——从返回对象里直接掏出同名属性 | 代替 `result.done` / `result.value` 两步访问 |
| `setTimeout` vs `setInterval` | 延时调用一次（毫秒） / 重复调用 | 定时器与循环常见异步场景，不是 SSE 相关 |
