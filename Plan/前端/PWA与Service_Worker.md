# PWA 与 Service Worker

> 项目：AIChat v1.0  
> 日期：2026-07-17  
> 覆盖：PWA 三件套（manifest + SW + 注册）、离线缓存策略、SW 生命周期、进程隔离原理  

---

## 一、PWA 是什么——把网站变成可安装的 App

PWA 不改变你的后端和前端代码——它在浏览器层加了三样东西：

| 零件 | 位置 | 干什么 |
|------|------|--------|
| `manifest.json` | `public/manifest.json` | 安装说明书——"我叫什么名、用什么图标、打开时隐藏地址栏" |
| `sw.js` | `public/sw.js` | Service Worker——浏览器的后台独立线程，拦截请求、管理缓存、离线兜底 |
| SW 注册代码 | `index.html` 底部 | 把 SW 文件提交给浏览器，让它开始工作 |

三者关系：`manifest` 告诉浏览器"这个网站能被装成 App"，SW 提供离线能力。没有 SW 只装 manifest——装完后离线仍然白屏；没有 manifest 只有 SW——不能安装到桌面，但离线可用。

**PWA ≠ 新技术**——它是已有浏览器能力的包装：HTTPS + Service Worker + Web App Manifest。你不需要学新语言，SW 写的是普通的 JS，manifest 是普通的 JSON。

---

## 二、manifest.json——安装说明书

```json
{
  "name": "AIChat",
  "short_name": "AIChat",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#f7f8fa",
  "theme_color": "#1677ff",
  "icons": [...]
}
```

| 字段 | 干什么 | 没它怎样 |
|------|--------|---------|
| `name` / `short_name` | App 名称——桌面图标下方显示 | 显示域名或空 |
| `display: "standalone"` | 打开时没有浏览器地址栏、标签页，像原生 App | 有地址栏——不像 App |
| `start_url` | 从桌面上点图标启动时加载哪个页面 | 无法启动 |
| `background_color` | 启动画面前景的底色——页面加载前先显示 | 白屏闪烁 |
| `theme_color` | 状态栏/工具栏颜色 | 浏览器默认色 |
| `icons` | 桌面图标 | 显示浏览器默认图标 |

### `<link rel="manifest">`——让浏览器发现这份说明书

```html
<link rel="manifest" href="/manifest.json">
```

`rel`（relationship）告诉浏览器这个链接的身份——不是图标（`icon`），不是样式表（`stylesheet`），而是安装说明书（`manifest`）。

浏览器流程：解析 `<head>` → 看到 `rel="manifest"` → 下载 JSON → 校验（有 name 吗？有 icon 吗？）→ 加入"可安装应用"候选池 → 用户访问次数够了 → 弹出"添加到桌面？"→ 安装。

---

## 三、Service Worker——浏览器的后台独立线程

### 是什么

SW 是浏览器在页面之外独立运行的一段 JS 代码——不受页面关闭影响。它的唯一存在理由是**拦截请求并决定用什么响应回页面**。

### 和普通 JS 的区别

| | 普通 JS（页面里） | Service Worker |
|--|-----------------|----------------|
| 全局对象 | `window` | `self` |
| 能操作 DOM 吗 | ✅ `document.querySelector` | ❌ `self.document` 不存在——SW 没有渲染引擎 |
| 能访问 localStorage 吗 | ✅ | ❌ `self.localStorage` 不存在——SW 用 Cache API 和 IndexedDB |
| 能发网络请求吗 | ✅ `fetch` | ✅ `self.fetch` |
| 生命周期 | 页面关闭→销毁 | 独立于页面——浏览器管理 |
| 存储 | — | `caches`——专管 HTTP 请求和响应的键值对仓库 |

`self` 是 SW 线程的全局根对象——和页面的 `window` 同一个概念，不同环境。浏览器给两个环境分配了不同的全局对象实例，各自挂不同的 API——不是同一套"禁用"了某些属性，是实例本身由不同的 C++ 类创建，物理上不包含另一个环境的属性。

### C++ 层面的原因

浏览器是多进程架构——渲染进程（页面）不能直接碰磁盘。Cache API 的操作必须通过 IPC 发消息给存储进程。这就是为什么 `caches.open()` 返回 Promise——跨进程通信天然是异步的。和你后端的 SQLite `db.session.commit()` 不同——SQLite 是嵌在 Python 进程内的 C 库，同一线程直接 `fwrite`，同步即可。

**根本规则：跨执行边界的事情必须有 Promise——另一个线程、另一个进程、网络远端的服务器，都是异步边界。**

---

## 四、SW 生命周期——三个事件

### install——预缓存关键文件

SW 首次安装时触发一次。通常用来把关键文件（首页、manifest）从网络预拉入缓存。

```js
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(['/', '/index.html', '/manifest.json', '/favicon.svg'])
    })
  )
})
```

`caches.open('aichat-v1')`——打开或创建一个名为 `aichat-v1` 的缓存仓库。`cache.addAll([...])` 内部为每个 URL 自动 fetch + 存入缓存。`event.waitUntil(promise)` 延长事件生命期——等全部缓存完才说安装完成。不用它 → 安装提前完成 → 缓存不完整 → 离线时缺失文件。

### activate——清理旧版本缓存

新 SW 接管控制权时触发。清理前任留下的过期数据。

```js
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys
          .filter((key) => key !== CACHE_NAME)
          .map((key) => caches.delete(key))
      )
    })
  )
})
```

`caches.keys()` 拿到所有缓存仓库的名字。`filter(key => key !== CACHE_NAME)` 筛出不属于当前版本的旧仓库。`map(key => caches.delete(key))` 逐个删除。`Promise.all([...])` 等全部删完才兑现。

### fetch——拦截请求

页面发的每个请求都触发此事件。决定"走网络"还是"从缓存拿"。

```js
self.addEventListener('fetch', (event) => {
  if (不该拦截) return              // 浏览器正常走网络

  event.respondWith(               // 用我给的 Response 回页面
    fetch(event.request)           // 网络优先
      .then((response) => {
        // 成功了 → 复制一份存缓存（静默，不阻塞返回）
        const cloned = response.clone()
        caches.open(CACHE_NAME).then((cache) => cache.put(event.request, cloned))
        return response
      })
      .catch(() => caches.match(event.request))  // 网络挂了 → 缓存兜底
  )
})
```

`event.respondWith(promise)` 是 SW 的核心——告诉浏览器"别发网络请求，用我传的这个 Response 回页面"。页面不知道收到的是服务器的响应还是 SW 虚拟的——它只看到一个 HTTP 响应。

`response.clone()` 复制响应体——response 对象的 body 只能读一次（一次返回页面、一次存缓存，需要两个独立副本）。

---

## 五、缓存版本管理——为什么需要 CACHE_NAME

改版后 SW 代码有更新的 JS 文件。如果缓存里还是旧版的 HTML/JS/CSS，离线时用户看到的是旧界面。

```
CACHE_NAME = 'aichat-v1'
  → 改版 → CACHE_NAME = 'aichat-v2'
  → 新 SW 创建 'aichat-v2' 缓存——预存新版文件
  → activate 清掉 'aichat-v1'——旧文件消失
  → 下次离线用户看到的是最新页面
```

不改版本名 → 新旧文件共存于同一仓库 → activate 不触发 → 旧缓存条目仍在——但不会产生存储冲突（同一个 URL key 会被新的 fetch 响应覆盖），只是旧文件会堆积占用空间。改版本名更直接——新建一个干净仓库，一口气删掉所有旧数据。

---

## 六、不重要的速记

| 知识点 | 一句话 | 用途 |
|--------|--------|------|
| `<link>` 的 `type` 属性 | 提前告诉浏览器文件格式——和 HTTP 响应里的 `Content-Type` 同信息但不同时机 | 预检优化；响应头缺失时兜底 |
| `rel` 属性 | 告诉浏览器"这个文件的身份是什么" | `icon` = 标签页图标，`manifest` = 安装说明，`stylesheet` = CSS |
| `self`（SW 全局对象） | SW 线程的全局根对象——没有 `document`、没有 `localStorage`，只有 `fetch` 和 `caches` | SW 不渲染页面，没必要挂 DOM API |
| `window`（页面全局对象） | 页面的全局根对象——所有内置 API 挂在上面 | `console.log` 等价于 `window.console.log`——你省略了 `window.` |
| `addEventListener` | 原生 JS 的事件绑定——SW 里没有 Vue，必须手动写 | Vue 的 `@click` 编译后落在此 API 上 |
| `event.waitUntil(promise)` | 延长事件生命期——等 Promise 兑现 | install 里保证缓存存完再算完成 |
| `event.respondWith(promise)` | 拦截请求，用自定义的 Response 回页面 | fetch 事件的唯一作用——决定回什么 |
| `new Response(html, { headers })` | 浏览器内置的构造器——创建一个 HTTP 响应对象 | SW 离线时造虚拟响应给页面 |
| `.then()` vs `await` | 同一种暂停/恢复模式的两种写法 | SW 回调未标 `async` 时用 `.then()`，`async` 函数内用 `await` |
| `response.clone()` | 复制响应体——body 只能读一次，两个消费者各需一份 | 一份返回页面，一份存缓存 |
| `caches` vs `localStorage` | caches 存完整 HTTP 响应（状态码+头+体），localStorage 存字符串键值对 | 前者给 SW 离线兜底，后者存 token 和用户偏好 |
| `Promise.all([...])` | 等一组 Promise 全部兑现才兑现 | 批量删除缓存仓库 |
| `filter()` / `map()` | JS 数组的筛选和映射方法 | filter 选出需要处理的项，map 把每项转换成操作 |
