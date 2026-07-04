# Vue Router 与登录闭环

> 项目：AIChat v1.0  
> 日期：2026-07-04  
> 覆盖：路由跳转、token 存储、错误提示、表单验证、Chrome 自动填充  

---

## 一、Vue Router 路由方法

### `router.push('/chat')`
压栈跳转——历史记录中新增一条。用户点浏览器后退能回到原页面。

### `router.replace('/chat')`
原地替换——不增长历史记录。登录成功或注册成功后使用，避免用户退回到已登录的窗口。

### `useRouter()` vs `useRoute()`
- `useRouter()` 返回路由**器**实例，调用 `push`、`replace`、`go` 等方法控制跳转
- `useRoute()` 返回当前路由信息（`path`、`params`、`query`），只读

`useRouter()` 必须在 `<script setup>` 顶层调用，不能放在函数体内部。

---

## 二、localStorage —— 客户端的持久化存储

```js
localStorage.setItem('token', response.data.access_token)   // 存
localStorage.getItem('token')                                 // 取
localStorage.removeItem('token')                              // 删
```

和 WebSocket 不同——`localStorage` 是浏览器提供的键值对存储，数据存在用户磁盘上。关闭浏览器、重启电脑之后 ，数据还在。JWT token 放这里是对的——token 本身有过期时间，不需要额外清理逻辑。

---

## 三、错误提示模式

### 响应式变量

```js
const errorMessage = ref('')     // 空 = 不显示
```

### 两种触发路径

```js
const handleLogin = async () => {
  errorMessage.value = ''                          // ① 每次开始时清空旧的

  try {
    ... axios.post(...) ...
  } catch (error) {
    errorMessage.value = error.response?.data?.error || '登录失败，请重试'
    // ② 网络错误或 401 → 显示后端返回的错误信息
  }
}
```

注册页多一个前端校验：

```js
if (password.value != cfm_password.value) {
  errorMessage.value = '两次密码不一致'    // ③ 前端校验失败
  return
}
```

### 模板渲染

```html
<p v-if="errorMessage" class="error-msg">{{ errorMessage }}</p>
```

`v-if="errorMessage"`：空字符串 → falsy → 节点从 DOM 树消失。非空 → truthy → 节点存在，`{{ }}` 填入文字。

`v-if` vs `v-show`：`v-if` 创建/销毁 DOM 节点；`v-show` 改为 `display: none`（节点仍存在，只是不可见）。

---

## 四、`?.` 可选链与 `||` 兜底

```js
errorMessage.value = error.response?.data?.error || '登录失败，请重试'
```

`?.`：链式访问——任何一步是 `undefined` 就停止返回 `undefined`，不抛异常。

`||`：左边有值取左边，左边没值取右边。JS 的 falsy 值：`''`、`0`、`null`、`undefined`、`NaN`、`false`。

---

## 五、前端校验 vs 后端校验

| | 前端校验 | 后端校验 |
|--|--------|--------|
| 例子 | 两次密码不一致 | 用户名已存在（需查数据库） |
| 速度 | 毫秒级 | 100-500ms |
| 安全性 | 用户可绕过（浏览器F12改了代码） | 绕不过——数据库是唯一权威 |

前端拦截的是"不需要网络就能判断"的无效请求。后端拦截的是"需要数据库才能判断"的业务规则。

---

## 六、Chrome 自动填充

`autocomplete="off"` 在 Chrome 上无效——Chrome 74 开始忽略此属性。

注册页用 `autocomplete="new-password"` 阻止填充已保存的旧密码——浏览器认为注册或改密不需要自动填入旧密码。

---

## 七、`ref` 使用规则

需要响应式——变量值变了，页面上用 `{{ }}` / `v-model` / `v-if` 引用的地方必须自动更新——才用 `ref`。只用于计算或调用方法的变量（如 `router`）不需要。

`ref` 的值通过 `.value` 读写——JS 没有 Python 的 `@property` 描述符，Vue 用盒子模拟。模板里不用写 `.value`——Vue 编译器自动解包。

---

## 八、不重要的速记

| 知识点 | 一句话 |
|--------|--------|
| `{{ }}` | Vue 模板的插值标记——里面写 JS 变量，等号是 `element.textContent = xxx` 的语法糖 |
| `.prevent` | 阻止浏览器默认行为（表单提交刷新页面） |
| `<form>` | 提供 `@submit` 事件——点按钮或按回车都触发 |
| `type="submit"` | 使按钮触发表单 `@submit` 事件 |
| `type="button"` | 按钮只触发 `@click`，不触发表单提交 |
| `<router-link>` | 路由跳转——不刷新页面 |
| `<a href>` | 浏览器新加载页面——刷新整个页面 |
| `const` | 声明不可重新赋值的变量 |
| `let` | 声明可变的变量 |
| `import` | 和 Python `from ... import` 一致——必须写在文件最顶部 |
| `export default` | 导出模块的默认值——其他文件通过 `import` 异步接收 |
