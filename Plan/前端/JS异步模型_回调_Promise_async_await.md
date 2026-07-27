# JS 异步模型：回调 → Promise → async/await

> 项目：AIChat v1.0  
> 目的：从零理解"为什么 axios.post() 不立刻返回结果"  
> 基础要求：会 Python 的 `def` / `return`，会 C 的 `main` → 顺序执行  

---

## 一、为什么浏览器不能"等着"

你后端 Python 写：

```python
import requests
response = requests.post('http://localhost:5000/api/auth/login', json=data)
print(response.status_code)   # 等 response 回来了才执行这行
```

Python 可以"停在这等"——因为后端等 0.3 秒不影响任何人。

浏览器不可以——因为浏览器只有一个主线程。如果 JS 在等网络响应时卡住，整个页面就冻住了：**按钮点不了、文字选不了、滚动不了、页面像死了一样。** 用户在等 DeepSeek 回复的 10 秒内，页面完全不能操作。

所以浏览器的规则是：**网络请求、定时器、文件读取——一律不等，立刻返回。**

---

## 二、回调（Callback）："干完了调这个函数"

最早的解决方案。一个函数包起来，等网络请求结束了再执行：

```js
function fetchData(onSuccess) {
  setTimeout(() => {
    onSuccess('数据到了')     // 2 秒后调这个函数
  }, 2000)
}

fetchData((result) => {
  console.log(result)         // 2 秒后才打印
})
console.log('我先打印')       // 这行立刻执行，不等人
// 控制台输出顺序：
//   我先打印
//   数据到了（2 秒后）
```

`fetchData` 不返回数据——它返回 `undefined`（立刻）。数据通过回调函数的参数传回来。

**问题**：三个请求串行时写出来的是"回调地狱"——层层嵌套，代码向右一直缩进：

```js
login(res => {
  getUserInfo(res.token, info => {
    getChatHistory(info.userId, history => {
      // 越写越深......
    })
  })
})
```

---

## 三、Promise："我给你一个承诺，以后兑现"

一个 Promise 是一个**现在拿不到、将来会拿到的值的占位符。**

```js
const promise = axios.post('/api/auth/login', { username, password })
// promise 现在是 Promise 对象，不是登录结果
// axios 立刻返回一个"承诺"：成了就调 .then，败了就调 .catch

promise
  .then(response => {
    console.log('登录成功', response.data)   // 成了走这里
  })
  .catch(error => {
    console.log('登录失败', error)           // 败了走这里
  })

console.log('这行先打印')    // 和回调一样，不等人
```

把上面的"回调地狱"用 Promise 链改写：

```js
login({ username, password })
  .then(res => getUserInfo(res.token))       // 登录完拿用户信息
  .then(info => getChatHistory(info.userId)) // 拿完信息拿聊天记录
  .then(history => console.log(history))     // 打印出来
  .catch(err => console.log('某一步挂了', err))
```

不再是向右缩进——是向下一步一步链下去。

### 补充一个进阶坑

`Promise.resolve().then(...)` 还有一个隐藏特性：`.then()` 本身会**返回一个新的 Promise**，这个新 Promise 的状态取决于你箭头函数的返回值。但在你的例子中，因为箭头函数里没有 `return`，默认返回 `undefined`，所以它最终会返回一个状态为 `fulfilled`、值为 `undefined` 的新 Promise。

### 三个状态

一个 Promise 从创建到结束走三种状态之一：

```
Promise 诞生
  → pending（等待中——还没结果）
  → fulfilled（成了——resolve 被调用）
  或 rejected（败了——reject 被调用）
```

一个 Promise 只能从未完成变到已完成或已失败一次——不能来回横跳。

### Python 等价

```python
# Python asyncio 的 Future ≈ JS Promise
import asyncio

async def main():
    result = await asyncio.sleep(2, '数据到了')  # await = .then 的语法糖
    print(result)
```

Python 的 `asyncio.Future` 和 JS 的 `Promise` 是同一个东西——一个将来才会有的值的占位符。

---

## 四、async/await："用同步写法写异步代码"

`await` 让 JS 暂停当前函数，等 Promise 兑现，然后继续。注意：**只暂停当前函数，不暂停页面其他事情。**

```js
const handleLogin = async () => {           // async 标记这个函数里有 await
  try {
    const response = await axios.post('/api/auth/login', {
      username: username.value,
      password: password.value
    })
    // await 暂停在这里——不执行下一行，直到 axios 返回结果
    console.log('登录成功:', response.data)   // response 是真正的结果，不是 Promise
  } catch (error) {
    console.log('登录失败:', error)
  }
}
```

等价 Python：

```python
async def handle_login():
    try:
        response = await http_client.post('/api/auth/login', json=data)
        print('登录成功:', response.json())
    except Exception as e:
        print('登录失败:', e)
```

### async/await 三条规则

1. `await` 只能放在 `async` 标记的函数里
2. `await` 后面跟的是一个 Promise（`axios.post` 返回的就是 Promise）
3. `await` 暂停的是**当前函数**，不是整个浏览器页面

---

## 五、你的 Login.vue 里的实际代码

当前：

```js
const handleLogin = () => {
  console.log('用户名:', username.value)
  console.log('密码:', password.value)
}
```

加上 `async/await` 后：

```js
import axios from 'axios'

const handleLogin = async () => {                    // ① 加 async
  try {
    const response = await axios.post('/api/auth/login', {  // ② 加 await
      username: username.value,
      password: password.value
    })
    console.log('登录成功:', response.data)           // ③ response 是真正的结果
    // 下一步：存 token、跳转到 /chat
  } catch (error) {
    console.log('登录失败:', error.response?.data)    // ④ 后端返回的错误信息在这里
  }
}
```

执行时间线：

```
用户点登录
  → handleLogin 开始执行
  → await axios.post(...) → JS 引擎暂停 handleLogin，把控制权还给浏览器
  → 浏览器继续响应鼠标/键盘（页面不冻）
  → 0.3 秒后，Flask 返回响应
  → JS 引擎恢复 handleLogin，从 await 那一行继续往下
  → console.log('登录成功')
```

---

## 六、一张图总结三个概念的关系

```
                    ┌─────────────────┐
                    │   浏览器主线程    │
                    │  永远不能等！     │
                    └────────┬────────┘
                             │
            ┌────────────────┼────────────────┐
            ▼                ▼                ▼
      回调 Callback     Promise         async/await
      "干完调我"      "给你承诺"       "用同步写法写异步"

      层层嵌套           .then()链        await 暂停
      (2010年前)      (2015年)        (2017年, 现在主流)
```

你项目里只用 `async/await`——`axios.post()` 返回 Promise，你用 `await` 等它。

---

## 七、Python/JS 异步速查

| 概念 | Python（asyncio） | JS |
|------|-------------------|-----|
| 异步函数标记 | `async def` | `async function` / `async () =>` |
| 等待结果 | `await` | `await`（一模一样） |
| 未来值占位符 | `asyncio.Future` | `Promise` |
| 错误处理 | `try/except` | `try/catch` |
| 等一个 Future | `await future` | `await promise` |

你的后端 `chat.py` 没用 `asyncio`——用的是同步的生成器 `yield`。但如果你用过 Python 异步，JS 的 `async/await` 就是一模一样的写法。
