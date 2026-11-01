# 移动端适配与 PWA 安装复盘

> 项目：AIChat v1.0  
> 日期：2026-11-01  
> 覆盖：抽屉式会话栏、视口与安全区、全局 box-sizing、Windows 端口保留、PWA 安装排查、图标生成  
> 状态：已落地并部署

---

## 零、这次的改动清单

| 文件 | 改了什么 |
|---|---|
| `frontend/src/views/Chat.vue` | 抽屉式侧栏：状态、模板、媒体查询 |
| `frontend/src/App.vue` | 全局 `box-sizing: border-box` |
| `frontend/src/views/Login.vue` / `Register.vue` | 卡片宽度、`100dvh` |
| `frontend/index.html` | viewport 加 `viewport-fit=cover` |
| `frontend/public/manifest.json` | 删掉 SVG 图标条目 |
| `frontend/public/sw.js` | 加 `skipWaiting()` / `clients.claim()` |
| `frontend/public/icon-192.png` / `icon-512.png` | 从纯蓝色块换成真实图形 |
| `backend/app.py` | 开发端口 5000 → 5500 |
| `frontend/vite.config.js` | 代理目标同步到 5500 |

---

## 一、移动端为什么坏——先定位，再动手

### 1.1 现象与根因

手机上左侧会话栏占了屏幕的一半以上，聊天区被压成一条缝。原因不是"没有响应式设计"这种笼统说法，而是一条具体的 CSS：

```css
.sidebar {
  width: 260px;
  flex-shrink: 0;   /* 不允许被压缩 */
}
```

`flex-shrink: 0` 意味着**在任何屏幕宽度下这 260px 都不会让**。按写下的数字算，375px 的手机上聊天区只剩 115px。

而且因为项目没有全局 `box-sizing`，`width: 260px` 是**内容宽度**，加上左右各 12px 的 padding，实际占位是 284px——比写下这个数字的人以为的还宽 24px。真实剩下的空间是 375 − 284 = 91px。

**没有媒体查询**是表象；**固定的、不可压缩的宽度**才是根本。

### 1.2 断点选在哪

768px 是移动端/桌面的常用分界线（iPad 竖屏就是 768）。判断依据不是"教材这么写"，而是：260px 侧栏在 768px 屏幕下还剩 508px 给聊天区，是舒服的；再窄就明显挤了。

媒体查询写成 `@media (max-width: 767px)`，和 768 不重叠。

---

## 二、抽屉式侧栏——为什么用 `fixed` + `transform`

### 2.1 两条路，差在"谁承担动画代价"

**路子一：动画宽度**

```css
.sidebar { width: 0; transition: width .25s; }
.sidebar.open { width: 260px; }
```

每一帧都在改宽度 → 浏览器要重新计算布局（reflow）→ 聊天区跟着被挤压 → 气泡重排、文字跳动。手机上直接掉帧。

**路子二：把侧栏抽离文档流，再让它平移出去**

```css
.sidebar {
  position: fixed;              /* 脱离 flex 布局 */
  transform: translateX(-100%); /* 推到屏幕左侧外面 */
  transition: transform .25s ease;
}
.sidebar.open { transform: translateX(0); }
```

`position: fixed` 让侧栏不再占据布局空间，聊天区永远是满宽；`transform` 只改变合成层的位置，不触发 reflow。

一句话：**路子一让整个页面布局跟着动，路子二只让一个图层平移。**

### 2.2 为什么不用 `left: -260px` 而是 `translateX`

同样是"移出屏幕"，`left` 属于布局属性，改它会触发 reflow；`transform` 属于合成属性，浏览器可以直接交给 GPU 挪图层。动画场景下后者是标准做法。

### 2.3 模板结构

```vue
<!-- 侧栏：绑一个 open 类，不要用 v-if -->
<aside class="sidebar" :class="{ open: sidebarOpen }">

<!-- 遮罩：必须在 sidebar 和 chat-body 之间 -->
<div v-if="sidebarOpen" class="backdrop" @click="sidebarOpen = false"></div>
```

**为什么侧栏不能用 `v-if`**：`v-if` 是"从 DOM 里删掉"，元素都不存在了，`transition` 自然没有起点和终点，动画会变成"突然出现/突然消失"。要动画，元素必须一直在 DOM 里，只是位置在变。

**为什么遮罩可以用 `v-if`**：遮罩不需要滑入滑出，出现/消失就够了。

**为什么遮罩必须是兄弟节点**：它的定位是 `position: fixed; inset: 0`（铺满视口），`z-index: 99` 压在侧栏（100）下面、聊天区上面。如果塞进 `.chat-body` 里，一旦将来给 `.chat-body` 加 `transform` 或 `overflow`，`fixed` 的参照系会跟着变，遮罩就只覆盖聊天区了。

### 2.4 关键 CSS

```css
@media (max-width: 767px) {
  .menu-btn { display: block; }

  .sidebar {
    position: fixed;
    top: 0;
    left: 0;
    width: min(80vw, 300px);
    height: 100dvh;
    transform: translateX(-100%);
    transition: transform 0.25s ease;
    z-index: 100;
  }

  .sidebar.open { transform: translateX(0); }

  .backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.4);
    z-index: 99;
  }
}
```

三个值的理由：

- `min(80vw, 300px)`——320px 屏幕上算 256px，留出边界让人看见"背后还有东西，点一下能关"；大屏手机封顶 300px 不至于拉满
- `height: 100dvh` 而不是 `top:0; bottom:0`——两者同时写会冲突，二选一
- `z-index: 100 / 99`——遮罩必须在侧栏下面、聊天区上面

### 2.5 桌面端不能残留遮罩

用户在手机上打开抽屉 → 把窗口拉宽到桌面尺寸，`sidebarOpen` 还是 `true`，遮罩仍在 DOM 里。桌面端媒体查询不生效，`.backdrop` 变成一个普通块元素，可能挡住页面还点不掉。

兜底：

```css
.backdrop { display: none; }          /* 基础样式里先藏掉 */
@media (max-width: 767px) { .backdrop { display: block; ... } }
```

---

## 三、关闭时机——乐观更新 vs 确认后更新

`selectConversation` 里有两个可放的关闭位置：

```js
const selectConversation = async (id) => {
  if (isWaiting.value) return
  if (id === currentConvId.value) return

  currentConvId.value = id            // ← 这里已经改了

  const res = await axios.get(...)    // ← 等待网络
  sidebarOpen.value = false           // ← 方案 B：成功后再关
  messages.value = res.data.messages.reverse()
}
```

**方案 A（放在 `await` 之前）**：点下去抽屉立刻滑走，但请求还没回来。用户看到的是**上一个会话的消息**，过一会儿才换。如果请求失败，抽屉已经关了，`currentConvId` 却已经指向新会话——这时候发消息会发到那个用户根本没看见的会话里。而且 `catch` 里只有 `console.error`，界面上没有任何提示。

**方案 B（放在成功分支里）**：抽屉保持打开，被点的条目已经高亮（`currentConvId` 在第 72 行就改了），等数据回来、消息替换的同一刻抽屉滑走。失败时抽屉没关，"点了没反应"本身就是最直观的信号。

术语：A 是**乐观更新**（假设一定成功，先改界面），B 是**确认后更新**。微信切会话是 A——它读本地数据，几乎没有延迟；走网络且没有错误提示 UI 的场景，B 更稳。

---

## 四、全局 `box-sizing`——一个影响所有尺寸的默认值

### 4.1 `content-box` 和 `border-box` 的差别

```css
/* 默认（content-box） */
.box { width: 260px; padding: 0 12px; }   /* 实际占位 = 260 + 24 = 284px */

/* border-box */
.box { box-sizing: border-box; width: 260px; padding: 0 12px; }  /* 实际占位 = 260px */
```

项目原先只在 Login/Register 的 `input` 上写了 `box-sizing: border-box`，没有全局重置。于是：

- `.sidebar` 实际 284px
- `.card` 实际 400 + 64 = **464px**——375px 屏幕上必然横向溢出

### 4.2 放在哪里才算全局

```vue
<!-- App.vue -->
<style>
*,
*::before,
*::after {
  box-sizing: border-box;
}
</style>
```

**不带 `scoped`**。如果写在 `Chat.vue` 的 `<style scoped>` 里，`*` 会被编译成 `*[data-v-xxx]`，只对 Chat.vue 模板里的元素生效，Login/Register 的 `.card` 拿不到。

代价：全局改会影响所有现有元素——`.sidebar` 从 284 变 260，`.card` 从 464 变 400。改完要把三个页面都过一遍。

---

## 五、视口细节——那些"看着对了但手机上不对"的地方

| 问题 | 原因 | 写法 |
|---|---|---|
| 底部被裁 | 移动 Safari 的 `100vh` 包含地址栏 | `height: 100vh; height: 100dvh;`（后者覆盖，旧浏览器忽略第二行） |
| 刘海屏/底部横条遮挡 | 没有声明 `viewport-fit=cover`，`env(safe-area-inset-*)` 永远返回 0 | `<meta name="viewport" content="... viewport-fit=cover">` + `padding-bottom: max(16px, env(safe-area-inset-bottom))` |
| iOS 输入框聚焦时整页放大 | 输入框 `font-size` 小于 16px 会触发自动缩放 | 移动端 `font-size: 16px` |
| 登录卡片横向溢出 | 固定 `width: 400px` | `width: min(400px, calc(100vw - 32px))` |

`100dvh` 的 `d` 是 dynamic——浏览器地址栏伸缩时它会实时跟着变。旧浏览器不认识，会忽略那一行，前面保留的 `100vh` 就是兜底。

---

## 六、后端 5000 端口起不来——Windows 保留端口段

### 6.1 现象

```
* Serving Flask app 'app'
* Debug mode: on
以一种访问权限不允许的方式做了一个访问套接字的尝试。
```

这是 Windows 的 **WSAEACCES（10013）**。Flask 启动时第一件事是 `socket.bind(("127.0.0.1", 5000))`，这一步被系统拒绝。

### 6.2 诊断顺序

```powershell
# 1. 有没有进程占着 5000
netstat -ano | findstr :5000

# 2. 5000 是不是落在系统保留段里
netsh interface ipv4 show excludedportrange protocol=tcp
```

本例的结果：`netstat` 空，但排除表里有 `4911–5010` 一段，**5000 和 5001 都在里面**。这是 Hyper-V / WinNAT（Docker Desktop 会用到）预占的动态端口段。

所以"没人占用却绑不上"——不是别人占了，是系统不允许。

### 6.3 两种解法

**临时抢回来**（不改代码）：

```powershell
net stop winnat      # 需要管理员权限
# 另开窗口启动后端
net start winnat     # 用完立刻启回来，否则 Docker 网络会断
```

**持久换端口**（推荐）：选一个不在保留段里的端口。本例可用区间是 `5011–5356`、`5358–12506`，最后选了 **5500**。

要同步改两处：

```python
# backend/app.py
app.run(debug=True, port=5500)
```

```js
// frontend/vite.config.js
'/api': 'http://localhost:5500'
```

**不要改** `gunicorn_config.py` 的 `bind = "0.0.0.0:5000"` 和 `nginx.conf` 的 `proxy_pass http://flask:5000`——那是**容器内部**端口，跑在 Linux 容器的网络命名空间里，和 Windows 宿主机保留哪段端口无关。

### 6.4 为什么 Docker 不受影响

`app.py` 的 `app.run()` 写在 `if __name__ == "__main__":` 里，只有直接 `python app.py` 才执行。容器里的启动命令是：

```
CMD ["gunicorn", "-c", "gunicorn_config.py", "app:create_app()"]
```

gunicorn 只 import `create_app()`，那段代码永远不会跑。同理 `vite.config.js` 的 `server.proxy` 只服务于开发服务器，`vite build` 时被忽略。

**两套坐标系**：

```
宿主机（Windows）           容器网络（Linux）
localhost:5500      ✗       flask:5000
（开发用）                   （gunicorn 监听，nginx 访问）
```

compose 里 flask 没有 `ports:`，容器的 5000 从来没暴露到宿主机，两者不会碰面。

---

## 七、PWA 安装失败——按症状分层排查

### 7.1 先分清"卡在哪一步"

Chrome 在安卓上安装 PWA 分两步：

```
第一步（本地）：读 manifest → 校验图标 → 检查 SW 是否注册
                  ↓ 通过，弹出"安装"
第二步（联网）：把应用信息发给 Google 的 WebAPK 服务器
                 → 生成真正的 APK → 手机下载回来
```

"根本没有安装按钮" 和 "点了卡在下载中" 是两个完全不同的问题：

| 症状 | 大概率原因 |
|---|---|
| 微信/QQ 内置浏览器里没有安装入口 | PWA 安装被这些容器禁用，不是 bug |
| iOS Safari 没有安装提示 | 设计如此，要手动「分享 → 添加到主屏幕」 |
| 安卓 Chrome 有按钮但卡在"下载中" | WebAPK 服务不可达，或本地校验项有问题 |
| 安卓 Chrome 完全没按钮 | manifest / SW / HTTPS 有一项不满足 |

### 7.2 线上资源验证

用 curl 逐项确认（比在手机上猜快得多）：

```bash
curl -sI https://域名/manifest.json      # Content-Type 应为 application/json
curl -s  https://域名/manifest.json      # 内容是否完整
curl -s -o /dev/null -w "%{http_code}\n" https://域名/icon-192.png
curl -s -o /dev/null -w "%{http_code}\n" https://域名/sw.js
```

本例四项全部正常，说明 manifest 本身没问题，问题在图标内容和 SW 状态。

---

## 八、踩坑：两个 PNG 图标其实是纯色块

### 8.1 现象

把 manifest 里的 SVG 图标删掉之后，装到桌面的应用图标变成**一整块纯蓝色**。

### 8.2 根因

`icon-192.png`（545 字节）和 `icon-512.png`（1880 字节）本身就是两张纯色图——没有任何图形。体积小得异常就是线索：一张有内容的 512×512 PNG 通常几十 KB。

之前没人发现，是因为 manifest 里同时挂着 `favicon.svg`，Chrome 优先用了 SVG，把这个问题盖住了。删掉 SVG 之后，界面退回到色块。

### 8.3 为什么 SVG 那条本来也该删

```json
{ "src": "/favicon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any maskable" }
```

两个问题：

1. **`maskable` 有安全区要求**——系统会把图标裁成圆形/水滴形，图形必须留在中心约 80% 的区域内。SVG 一般没有留这个边距，裁完就缺角
2. **这个 SVG 有 197KB、698 条 `<path>`**——是描摹出来的矢量图，Chrome 安装时要把每个图标下载并光栅化一遍

正确的做法：`purpose` 用 `"any"`，要 maskable 就单独做一个带留白的 PNG。

---

## 九、踩坑：改了 SW 却看不到变化

浏览器对 `sw.js` 本身是有缓存的，改完部署后手机上可能几小时都还是旧版本。而且旧 SW 的激活时机是"所有相关页面关闭之后"。

### 9.1 为什么需要 `skipWaiting` 和 `clients.claim`

```js
self.addEventListener('install', (event) => {
  self.skipWaiting()      // 新 SW 不排队，立即进入激活状态
  event.waitUntil(...)
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    Promise.all([
      self.clients.claim(),   // 立刻接管已打开的页面
      caches.keys().then(...) // 原来的清缓存逻辑
    ])
  )
})
```

- 没有 `skipWaiting`：新 SW 停在 waiting 状态，等所有标签页关闭才激活
- 没有 `clients.claim`：激活了也不接管当前已打开的页面，要刷新一次才生效

`clients.claim()` 必须放进 `waitUntil`，否则 activate 结束后这个 promise 可能被丢弃。

### 9.2 调试时怎么强制清掉旧 SW

```
chrome://serviceworker-internals → 找到站点 → Unregister
```

或者：Chrome 设置 → 网站设置 → 该域名 → 清除并重置。

**这一步经常被跳过，导致误判"改了没用"。**

---

## 十、图标是怎么生成出来的

### 10.1 没有设计稿，只有一张 SVG

本机没有 ImageMagick / Inkscape / cairosvg，但有 Edge。用 headless 模式把 SVG 渲染成 PNG：

```html
<!-- render.html -->
<style>
  html, body { margin: 0; padding: 0; background: transparent; overflow: hidden; }
  .wrap { width: 512px; height: 512px; display: flex; align-items: center; justify-content: center; }
  img { display: block; width: 440px; height: 440px; }
</style>
<div class="wrap"><img src="file:///.../favicon.svg"></div>
```

```bash
msedge --headless=new --disable-gpu --hide-scrollbars \
       --force-device-scale-factor=1 --window-size=512,512 \
       --default-background-color=00000000 \
       --screenshot=icon-512.png file:///.../render.html
```

- `--default-background-color=00000000` → 透明背景（8 位 ARGB 十六进制）
- `--window-size` 和容器尺寸一致，截出来正好 512×512

再用 Pillow 缩出 192：

```python
from PIL import Image
Image.open('icon-512.png').convert('RGBA').resize((192, 192), Image.LANCZOS).save('icon-192.png')
```

`LANCZOS` 重采样比让浏览器直接渲染 192 更锐利。

### 10.2 为什么要留白

先算内容的真实包围盒（在 headless 页面里用 `svg.getBBox()`）：

```
x: 0, y: 61, width: 1232, height: 1193
```

图形贴着左边缘和下边缘——直接当图标会被裁。所以内层图片缩到 440×440 居中放置，四周留 7% 边距。这个边距对 Android 的圆形/圆角遮罩来说还不够多（严格 maskable 要 20%），但作为普通 `"any"` 图标是合适的。

### 10.3 用浏览器算 bbox 的方法

```html
<div id="holder"><!-- 把 SVG 内容内联进来 --></div>
<script>
  const b = document.querySelector('#holder svg').getBBox()
  document.getElementById('out').textContent = `BBOX ${b.x} ${b.y} ${b.width} ${b.height}`
</script>
```

```bash
msedge --headless=new --dump-dom file:///.../bbox.html | grep BBOX
```

`--dump-dom` 会输出 JS 执行后的 DOM，省去了手工测量的功夫。

---

## 十一、零散但值得记的坑

### 11.1 Vite 代理返回 502

502 的意思是：**请求到了 Vite，Vite 往上游转发时连不上**。不是前端代码的错。

排查顺序：

```bash
curl -X POST http://127.0.0.1:5500/api/auth/login ...   # 直连后端
curl -X POST http://localhost:5173/api/auth/login ...   # 经代理
```

直连成功、经代理失败 → 代理目标写错了；两个都失败 → 后端没跑。

### 11.2 `localhost` 同时是 IPv4 和 IPv6

Flask 默认只绑 `127.0.0.1`（IPv4），而 `localhost` 可能先解析到 `::1`。Node 17 以后解析顺序按系统返回的来，某些情况下会导致代理连不上。

排查时把代理目标写成明确的 `http://127.0.0.1:5500`，少一个变量就少一种可能。

### 11.3 Git Bash 里的 `python` 不是项目 venv

PowerShell 里 `python` 指向 `E:\Python\python.exe`（全局 3.13），Git Bash 里指向 MSYS2 自带的版本。两者都不是 `backend/venv`。

排查依赖问题时，一律用：

```bash
backend/venv/Scripts/python.exe app.py
```

### 11.4 `git add` 是原子操作

只要有一个 pathspec 匹配不上，整条命令失败，**一个文件都不会进暂存区**。所以会看到"路径 A 明明存在，也没被加进去"——因为路径 B 写错了。

排查：

```bash
git add --dry-run <路径>     # 只检查不执行
```

### 11.5 Vue Router 5 的 `next()` 已废弃

```
[Vue Router warn]: The `next()` callback in navigation guards is deprecated.
```

新写法用返回值代替回调：

```js
// 旧
router.beforeEach((to, from, next) => {
  if (to.path === '/chat' && !localStorage.getItem('token')) next('/login')
  else next()
})

// 新
router.beforeEach((to) => {
  if (to.path === '/chat' && !localStorage.getItem('token')) return '/login'
  // 什么都不返回 = 放行
})
```

返回值就是"接下来去哪"，`false` 表示中止导航。

### 11.6 `.waiting` 是死代码

`Chat.vue` 的 `<style>` 里定义了 `.waiting { display: flex; gap: 6px; padding: 14px 20px }`，但模板里等待指示器用的是 `class="ai-bubble"`，这个类从来没被用到。

---

## 十二、未实施：AI 回复的 Markdown 渲染

讨论过方案但没有落地，记录下来避免重复推演。

**改动点只有一处**：AI 气泡的 `{{ msg.content }}` 换成 `v-html`。

**选型**：`markdown-it`。理由：`html: false` 会把原始 HTML 转义掉，内置的 `validateLink` 会拒绝 `javascript:` 协议——比 `marked` 少一层 DOMPurify 依赖。

**关键配置**：

```js
const md = new MarkdownIt({ html: false, linkify: true, breaks: true })
```

`breaks: true` 不能省——现在靠 `white-space: pre-wrap` 保留换行，换成 Markdown 后单换行默认会被合并成空格。

**Vue 的坑**：`v-html` 插入的 DOM 不带 `data-v-xxx`，scoped 样式匹配不上，必须用 `:deep()`：

```css
.ai-bubble :deep(pre) { overflow-x: auto; }
```

**流式的坑**：半截代码围栏会先显示成乱文本（开头的三个反引号到了、结尾的还没到）。可以在渲染前数一下代码围栏符号的个数，奇数就临时补一个收尾。

**安全边界**：用户消息不要用 `v-html`——用户输入的正文没有理由被当 HTML 解析。

---

## 十三、验证清单

改完这些之后应逐项确认：

- [ ] 桌面（>768px）：菜单按钮不出现，侧栏常驻，和改造前一致
- [ ] 390px：侧栏完全不可见，聊天区满宽
- [ ] 点 ☰：侧栏滑出 + 遮罩出现，聊天区不被挤压
- [ ] 点会话 / 点 `+ 新对话` / 点遮罩：抽屉都收回
- [ ] 320 / 375 / 390：无横向滚动条
- [ ] 手机上输入框聚焦不放大页面
- [ ] 底部输入栏不被 iPhone 横条遮挡
- [ ] 部署后 `https://域名/icon-192.png` 显示的是真实图形
- [ ] 手机上清掉旧 SW 后，安装能正常完成（或被确认是 WebAPK 网络问题）

---

## 十四、一句话总结

移动端适配送配的核心不是"加个 media query"，而是**搞清楚每个尺寸由谁决定**：谁在占位（flex 子项 / fixed 元素）、谁在算宽度（content-box / border-box）、谁在承担动画代价（布局属性 / 合成属性）。PWA 安装则要分清"本地校验"和"联网生成"两段——症状不同，排查方向完全不同。
