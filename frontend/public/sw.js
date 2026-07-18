// ====== Service Worker —— PWA 的离线引擎 ======
// 浏览器后台独立线程，不受页面关闭影响
// 拦截所有网络请求，决定"走网络"还是"从缓存拿"

const CACHE_NAME = 'aichat-v1'

// ====== ① 安装事件：预缓存关键文件 ======
// SW 首次安装时触发——只跑一次
self.addEventListener('install', (event) => {
  console.log('[SW] 正在安装...')
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      // 把首页和 manifest 预先存进缓存
      return cache.addAll([
        '/',
        '/index.html',
        '/manifest.json',
        '/favicon.svg'
      ])
    })
  )
})

// ====== ② 激活事件：清理旧缓存 ======
// 新 SW 接管时触发——删掉旧版本的缓存
self.addEventListener('activate', (event) => {
  console.log('[SW] 激活')
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys
          .filter((key) => key !== CACHE_NAME)  // 旧版本缓存名不一样
          .map((key) => caches.delete(key))      // 删掉
      )
    })
  )
})

// ====== ③ 拦截请求：网络优先 + 缓存兜底 ======
// 页面发的每个请求都经过这里
self.addEventListener('fetch', (event) => {
  // 非 GET 请求、SSE 流、API 请求 —— 必须走网络，不缓存
  if (
    event.request.method !== 'GET' ||
    event.request.url.includes('/api/')
  ) {
    return   // 不拦截，浏览器按默认走网络
  }

  event.respondWith(
    fetch(event.request)
      .then((response) => {
        // 网络请求成功 → 把响应复制一份存缓存（静默，不阻塞返回）
        const cloned = response.clone()
        caches.open(CACHE_NAME).then((cache) => {
          cache.put(event.request, cloned)
        })
        return response  // 立即返回给页面
      })
      .catch(() => {
        // 网络挂了 → 尝试从缓存拿
        return caches.match(event.request).then((cached) => {
          if (cached) {
            console.log('[SW] 离线返回:', event.request.url)
            return cached
          }
          // 页面导航且没缓存 → 显示离线页面
          if (event.request.mode === 'navigate') {
            return new Response(
              '<html><body style="display:flex;align-items:center;justify-content:center;height:100vh;font-family:sans-serif"><h2>你离线了</h2></body></html>',
              { headers: { 'Content-Type': 'text/html' } }
            )
          }
          // JS/CSS 文件也没缓存 → 返回 503
          return new Response('Offline', { status: 503 })
        })
      })
  )
})
