# Vue 3 核心知识汇总

> 项目：AIChat v1.0  
> 来源：从前端所有复盘文档中提取 Vue 3 专属知识点  
> 覆盖：响应式系统、模板语法、组件、路由、虚拟 DOM、生命周期  

---

## 一、响应式系统——Vue 的核心引擎

### ref——响应式包装盒

```js
import { ref } from 'vue'
const username = ref('')
const messages = ref([])
const isWaiting = ref(false)
```

`ref()` 把普通值包进一个响应式盒子。括号里是初始值——`''`（空字符串）、`[]`（空数组）、`false`（布尔）。

**为什么需要 ref**：JS 没有 Python 的 `@property` 描述符——普通变量赋值 `x = '新值'` 无法插入拦截钩子。`ref` 用 getter/setter 替代裸变量——读 `.value` 时 Vue 记下"谁在读"，写 `.value` 时 Vue 通知所有引用处刷新。

**使用规则**：变量变了、页面需要自动刷新的地方才用 `ref`。只用于计算或调用方法的变量（如 `router`）不需要。

### `.value`——读写入口

```js
// <script setup> 里：必须写 .value
username.value = '新值'
console.log(messages.value.length)

// <template> 里：Vue 自动解包，不用写 .value
<input v-model="username">
<span>{{ username }}</span>
```

### 两种 ref 用途

| | 数据 ref | 模板 ref |
|--|--------|---------|
| 写法 | `ref('值')` | `ref(null)` + 模板里 `ref="名字"` |
| `.value` 是什么 | 响应式数据 | 真实 DOM 节点 |
| 变化时 | 触发页面更新 | 不触发更新 |
| 例子 | `const inputText = ref('')` | `const messageBox = ref(null)` |

模板 ref 的 `null` 是占位符——组件 setup 阶段 DOM 还不存在，渲染完成后 Vue 把真实 DOM 节点塞进 `.value`。

---

## 二、模板语法——Vue 的指令系统

### `v-model`——双向绑定

```html
<input v-model="username">
```

一行替代两行手工代码：`input.value = username.value`（数据→视图）+ `addEventListener('input', ...)`（视图→数据）。输入框和变量永远同状态。

### `v-if`——条件渲染

```html
<div v-if="errorMessage" class="error-msg">{{ errorMessage }}</div>
```

条件为 false → DOM 节点被**销毁**（不是隐藏）。为 true → 节点被创建挂到树上。适合条件很少变化、不会频繁切换的场景。

**v-if vs v-show**：`v-if` 销毁/创建节点（开销大），`v-show` 改为 `display: none`（节点还在）。频繁切换用 v-show，一次切换用 v-if。

### `v-for`——列表渲染

```html
<div v-for="(msg, index) in messages" :key="index">
  <p>{{ msg.content }}</p>
</div>
```

等价 Python：`for index, msg in enumerate(messages):`——遍历数组，每条生成一个 DOM 节点。

**`:key`——每行的唯一标识**：diff 算法靠 key 区分"谁是谁"，和 Git blob hash 同一个思想。key 相同的节点跳过不重画，只操作新增或删除的节点。

**v-if 与 v-for 的优先级**：Vue 3 规定 `v-if` 优先于 `v-for`，导致 `v-if` 里用到循环变量时变量还未定义 → 崩溃。不允许写在同一个元素上。

**解决方案——`<template>` 透明中介**：

```html
<template v-for="(msg, index) in messages" :key="index">    ← v-for 在外层
  <div v-if="msg.content !== ''" :class="...">                ← v-if 在内层
    <p>{{ msg.content }}</p>
  </div>
</template>
```

`<template>` 自己不出现在 DOM 里——只托管 `v-for`，让两层指令错开。

### `{{ }}`——插值

```html
<span>{{ username }}</span>
<p>{{ msg.content }}</p>
```

把 JS 变量的值塞进 HTML。等价 `element.textContent = xxx`。花括号是模板引擎的通用标记——Vue、Flask Jinja2 都用它。

### `@`——事件绑定（`v-on:` 的简写）

```html
<button @click="handleLogin">登录</button>
<form @submit.prevent="handleLogin">
<input @keydown.enter="sendMessage">
```

把浏览器事件绑定到 JS 函数。`.prevent` 阻止默认行为（表单刷新），`.enter` 只响应回车键。

### `:`——属性绑定（`v-bind:` 的简写）

```html
<div :class="msg.role === 'user' ? 'user-bubble' : 'ai-bubble'">
<button :disabled="!inputText.trim() || isWaiting">
<div :key="index">
```

把 JS 表达式的值传给 HTML 属性。不加 `:` 的话引号里当纯字符串处理。

---

## 三、组件系统

### `.vue` 文件三段结构

```html
<script setup>   ← JS 逻辑——变量、函数、import。顶层内容自动对模板可用
</script>

<template>      ← HTML 结构 + Vue 指令。本身不出现在 DOM 里
</template>

<style scoped>  ← CSS 样式。scoped 只对当前组件生效
</style>
```

### `<script setup>`——Vue 3 的新写法

不需要手动 `return { username, handleLogin }`——顶层变量和函数自动对模板可用。`useRouter()` 等组合式函数必须在顶层调用，不能放在函数体内部。

### `<style scoped>`——组件级隔离

样式只对当前 `.vue` 文件生效，不影响 `Login.vue` 里的同名 class。

---

## 四、Vue Router——前端路由

### 路由表定义

```js
const routes = [
  { path: '/login', name: 'Login', component: () => import('../views/Login.vue') },
  { path: '/', redirect: '/login' }
]
const router = createRouter({ history: createWebHistory(), routes })
```

`() => import(...)` 是懒加载——用户不访问这个路由就不下载该组件。

### 路由方法

| 方法 | 干什么 | 历史记录 |
|------|--------|---------|
| `router.push('/chat')` | 跳转 | 加一条 → 能后退 |
| `router.replace('/chat')` | 跳转 | 替换当前 → 不能后退——登录后应使用此方法 |
| `router.back()` | 后退 | — |

### `<router-link>` vs `<a>`

```html
<router-link to="/register">去注册</router-link>    ← 路由跳转，不刷新页面
<a href="/register">去注册</a>                       ← 整页刷新，Vue 状态全丢
```

### `<router-view />`——路由出口

```html
<router-view />
```

占位符——当前路由匹配的组件被塞到这个位置。SPA 的核心：整个网站只有一个 HTML 文件，切换页面不刷新，只换 `<router-view />` 里的内容。

### useRouter vs useRoute

`useRouter()` 返回路由**器**实例——调 `push`、`replace`。  
`useRoute()` 返回当前路由信息——`path`、`params`，只读。

---

## 五、虚拟 DOM——Vue 的 diff 引擎

### 是什么

Vue 在 JS 内存里维护一棵轻量 DOM 树——每个节点只存 tag、class、key、children，不存真实 DOM 的几百个浏览器内部属性。

### 工作流程

```
① 数据变了 → Vue 重新跑 render → 生成新的虚拟 DOM 树（纯 JS，极快）
② diff 新旧两棵虚拟 DOM 树 → 找到差异点（靠 :key 定位）
③ 把差异一次性应用到真实 DOM → 最小的真实 DOM 操作
```

### 与 Git 的类比

Git 比对两版 commit 的 tree——blob hash 相同的跳过。Vue 比对两版虚拟 DOM——key 相同的跳过。同一个 diff 算法思想——拍快照、比对、只动变了的地方。

---

## 六、nextTick——等 Vue 画完 DOM

### 问题

`messages.value.push(新消息)` 后 Vue 不立刻画 DOM——它把更新排进内部队列，等 JS 代码跑完再批量执行。

### 解决

```js
import { nextTick } from 'vue'

await nextTick()                         // 等 Vue 清空 DOM 更新队列
messageBox.value.scrollTop = messageBox.value.scrollHeight   // 此时读到真实高度
```

`nextTick()` 返回一个 Promise——Vue 清空 DOM 更新队列后 resolve。`await` 暂停当前函数等这一刻。

---

## 七、组件生命周期

```
① setup() 阶段（JS 初始化）
   → ref(null)、定义函数
   → DOM 不存在

② mount 阶段（Vue 画 DOM）
   → 模板编译，创建真实 DOM 节点
   → 模板 ref 被填入值

③ update 阶段（数据变化）
   → 虚拟 DOM diff → 更新真实 DOM
   → nextTick 在每次更新后可用
```

---

## 八、模板语法速查

| 语法 | 干什么 | 例子 |
|------|--------|------|
| `v-model="x"` | 双向绑定——输入框 ↔ 变量 | `<input v-model="username">` |
| `v-if="x"` | 条件渲染——创建/销毁 DOM | `<div v-if="errorMessage">` |
| `v-show="x"` | 条件显示——display:none | `<div v-show="open">` |
| `v-for="m in arr"` | 列表渲染——遍历数组 | `<div v-for="m in messages" :key="i">` |
| `@click="fn"` | 点击事件 | `<button @click="handleLogin">` |
| `@submit.prevent` | 表单提交 + 阻止刷新 | `<form @submit.prevent="...">` |
| `:class="expr"` | 动态 CSS class | `:class="role === 'user' ? 'u' : 'a'"` |
| `:disabled="expr"` | 动态禁用 | `<button :disabled="loading">` |
| `:key="id"` | v-for 的唯一标识 | `:key="index"` |
| `{{ expr }}` | 插值——显示变量值 | `<p>{{ msg.content }}</p>` |
| `ref="name"` | 模板 ref——抓 DOM 节点 | `<div ref="messageBox">` |

---

## 九、与后端的精确类比

| Vue 概念 | 后端等价 |
|----------|---------|
| `ref` | `@property` 描述符——读/写时插入钩子 |
| `v-for` + `:key` | `for ... in enumerate(...)` |
| `v-model` | `@property` getter + setter——双向同步 |
| `{{ }}` | Jinja2 模板插值——Python 里同样用 `{{ }}` |
| `@click` | `@app.route`——声明事件和函数的绑定关系 |
| `<router-link>` vs `<a>` | SPA 内部跳转 vs 整页刷新 |
| `router.push` | Flask `redirect('/chat')`——但不刷新页面 |
| 虚拟 DOM | Git tree 对象——拍快照、比对、只动变化 |
| `:key` | Git blob hash——唯一标识，diff 的基础 |
| `nextTick` | 没有直接等价——等 DOM 更新完再读 |
