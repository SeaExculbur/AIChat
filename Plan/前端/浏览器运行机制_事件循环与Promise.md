# 浏览器运行机制：事件循环、Promise、线程与进程

> 项目：AIChat v1.0  
> 日期：2026-07-03  
> 覆盖：事件循环、宏任务/微任务、Promise 状态变更机制、浏览器架构、进程与线程  

---

## 一、浏览器架构——JS 引擎不是一个人在工作

浏览器是一个 C++ 程序，里面嵌了一个 JS 引擎（Chrome 用的是 V8）：

```
浏览器（C++ 应用程序）
│
├─ V8 引擎          → 执行 JS 源代码。const/if/for/函数调用都在这里
├─ Blink 渲染引擎    → 解析 HTML/CSS，画到屏幕上
├─ C++ 网络栈       → TCP 连接、HTTP 解析、调用操作系统 socket API
├─ Web API 层       → 胶水层——把 C++ 的网络/定时器能力暴露成 JS 函数
│   ├─ fetch()          → JS 调它 = 间接调 C++ 网络栈
│   ├─ setTimeout()     → JS 调它 = 在 C++ 里启动一个定时器
│   └─ DOM API          → JS 调它 = 操作渲染引擎里的节点树
└─ 操作系统内核      → 真正发包的是内核的 TCP/IP 协议栈
```

**有什么用**：理解了这层架构，你就知道为什么 `axios.post()` 不卡页面——网络 I/O 在 C++ 网络栈里异步跑，不占 JS 主线程。JS 只是"通知 C++ 发请求"然后继续。

**axios → fetch → C++ → TCP 的完整调用链**：

```
axios JS 代码（V8 执行）
  → fetch() JS 方法（Web API 入口）
  → 浏览器 C++ 网络栈（TCP 三次握手、send/recv、HTTP 解析）
  → 操作系统内核 socket API（真正发包）
  → 网卡 → 网络 → 后端
```

---

## 二、事件循环——JS 是单线程的，为什么不卡死

JS 只有一个主线程，同一时刻只能干一件事。但要同时响应鼠标点击、网络响应、定时器——靠的是**事件循环**：

```
调用栈             任务队列
────────           ──────────
                   ┌──────────┐
主线程正在执行       │ 鼠标点击   │
  console.log()     │ 定时器到期 │
  handleLogin()     │ HTTP 响应  │
                    └──────────┘

规则：调用栈清空 → 从队列取一个任务 → 执行 → 栈空 → 取下一个 → 循环
```

**有什么用**：理解了调用栈和队列的关系，你就知道为什么 `await` 之后的代码不是立刻执行的——它被塞进了队列，要等当前调用栈清空。

---

## 三、宏任务和微任务——两个队列，优先级不同

任务队列不是只有一个——是两个：

| | 宏任务（Task） | 微任务（Microtask） |
|--|-------------|-----------------|
| 来源 | `setTimeout`、用户点击、HTTP 响应 | `Promise.then/catch`、`await` 之后 |
| 优先级 | 低——一次取一个 | 高——每一个宏任务跑完后清空全部微任务 |

**事件循环的精确规则**：

```
① 清空调用栈
② 清空整个微任务队列（全部取出执行）
③ 从宏任务队列取一个（只取一个）执行
④ 回到 ①
```

**有什么用**：解释这个输出顺序：

```js
console.log('1')
setTimeout(() => console.log('2'), 0)
Promise.resolve().then(() => console.log('3'))
console.log('4')
// 输出：1 → 4 → 3 → 2
```

`then` 进微任务、`setTimeout` 进宏任务。微任务在宏任务之前清空——所以 `3` 在 `2` 之前。

Promise.resolve().then(() => console.log('3'))

它的意义是**构造一个已完成状态的 Promise，并注册一个回调**，让这个回调在本次事件循环的**微任务阶段**被异步调用，而不是在声明时同步调用。

**`await` 与微任务的关系**：

```js
const handleLogin = async () => {
  const response = await axios.post(...)
  console.log(response)           // ← 这行进微任务队列
}
handleLogin()
console.log('我先')               // ← 这行先执行
```

`await` 后面的代码等价于 `.then` 回调——被塞进微任务队列，等调用栈清空才执行。

---

## 四、Promise 状态变更——谁在调 resolve

Promise 状态不是魔法——是有人调了 `resolve` 或 `reject`：

```js
new Promise((resolve, reject) => {
  // resolve('成功') → Promise → fulfilled
  // reject('失败')  → Promise → rejected
})
```

**axios 的 Promise 状态是谁改的**：

```
浏览器 C++ 网络栈收到 HTTP 响应
  → 解析 HTTP 报文
  → fetch API 内部：状态码 2xx → 调 resolve(response)
                    状态码 !2xx → 调 reject(error)
  → fetch 的 Promise 状态变更
  → axios 监听到 → 把 axios 自己的 Promise resolve 掉
  → 你的 await 拿到值
```

Promise 在 `fulfilled` 时存的是 `resolve(值)` 里的值，在 `rejected` 时存的是 `reject(错误)` 里的错误对象。你的 `response.data.access_token` 和 `error.response?.data` 都是从这两个状态存储位置取出来的。

---

## 五、进程与线程

| | 进程（Process） | 线程（Thread） |
|--|---------------|-------------|
| 内存 | 独立——互不看见 | 共享——都能读写 |
| 崩溃影响 | 一个崩了别的没事 | 一个崩了整个进程死 |
| 通信 | 管道、Socket | 直接读写共享变量（需加锁） |
| 你的项目里 | Flask（Python 进程）、Vite（Node.js 进程）、浏览器（C++ 进程） | 浏览器主线程、Web Worker 线程 |

**浏览器为什么选单线程 + 事件循环而不是多线程**：两个线程同时改同一个 DOM 节点——一个删它一个改它——浏览器不知道该听谁的。单线程天然避免锁问题。

**异步 ≠ 并行**：异步控制**时序**（什么时候做），并行控制**并发**（几条路同时做）。JS 的异步是靠 C++ 层和操作系统在背后并行跑 I/O，JST 主线程永远是单线程。`setTimeout` 把任务推迟不让它卡着栈，但栈里的任务跑满 3 秒照样卡——事件循环被堵死。

---

## 六、路由思想——从芯片到应用层的同构模式

物理路由器查 IP 前缀转发数据包，Flask 查 URL 路径转发请求给函数——同一个信息结构：

```
层级            查什么键          转发到哪里
─────────────────────────────────────────────
网络层          IP 地址         下一跳路由器 / 目标机器
传输层          端口号           目标进程（操作系统端口映射表）
应用层          URL 路径         目标函数（Flask 路由表）
Vue Router      地址栏路径        目标组件（Login.vue / Chat.vue）
```

**端口的作用**：IP 地址找到机器，端口号找到机器里的进程。你 `s.bind(('localhost', 8080))` 就是在操作系统里登记"8080 这个房号我占了"。

一个 TCP 连接由四元组唯一确定：`(源IP, 源端口, 目标IP, 目标端口)`。客户端端口是操作系统临时分配的（用完回收），服务端端口是固定监听的。

---

## 七、不重要的知识点速记

| 知识点 | 一句话 | 用途 |
|--------|--------|------|
| `async` 关键字 | 标记函数可以用 `await`，返回值自动包装成 Promise | 语法开关，没有运行时代码 |
| `await` 关键字 | 等 Promise 兑现，取 `resolve` 传出来的值 | 暂停当前函数，不暂停浏览器 |
| `?.` 可选链 | `obj?.prop` = 如果 `obj` 是 `null/undefined` 就返回 `undefined` | 防止访问空对象崩溃 |
| `_` 占位符 | `(_, reject) => {}` 表示第一个参数不需要 | JS 社区约定，不是语法 |
| 箭头函数 `() => {}` | 等于 Python `lambda:` / C 函数指针 | 短函数写法和"传函数当参数" |
| `ref('')` | 返回一个带 getter/setter 的包装盒，值在 `.value` 里 | JS 没有 `@property` 描述符，Vue 用盒子模拟 |
| `Promise.resolve().then(fn)` | 把 `fn` 塞进微任务队列 | 控制异步执行时序 |
