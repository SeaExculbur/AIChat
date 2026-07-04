# DOM 操作速查

> 项目：AIChat v1.0  
> 目的：Vue 模板语法的底层落脚点——你写的每一行 Vue 最终都落在这些操作上  

---

## 一、DOM 是什么

浏览器把 HTML 文档在内存里建成一棵节点树。树上的每个节点都是一个 JS 对象——能读、能写、能删、能挪。

```
HTML                    内存中的 DOM 树（JS 对象）
─────                   ──────────────────────────
<html>                   document
  <body>                   └─ html
    <div id="app">             └─ body
    </div>                        └─ div#app
</html>
```

`document` 是这棵树的根节点，一切操作从它开始。

---

## 二、找节点

```js
// 按 id 找（最精确，最快）
document.getElementById('app')

// 按 CSS 选择器找第一个（通用）
document.querySelector('.error-msg')       // class
document.querySelector('#app')             // id
document.querySelector('input[type="text"]') // 属性选择器

// 按 CSS 选择器找全部（返回 NodeList，不是真正的数组）
document.querySelectorAll('.row')

// 从当前节点往周围找
element.parentElement          // 父节点
element.children               // 所有直接子节点
element.nextElementSibling     // 下一个兄弟节点
```

---

## 三、读/写内容

```js
element.textContent = '新文字'          // 改纯文字（安全——自动转义）
const text = element.textContent        // 读纯文字

element.innerHTML = '<b>新文字</b>'     // 插入 HTML（有 XSS 风险——别直接拼接用户输入）
```

---

## 四、读/写样式

```js
element.style.color = 'red'             // 改单个样式
element.style.display = 'none'          // 隐藏元素
element.style.display = ''              // 恢复显示

element.classList.add('active')         // 加 class
element.classList.remove('active')      // 去 class
element.classList.toggle('active')      // 切换 class（有就去掉，没有就加上）
element.classList.contains('active')    // 判断有没有这个 class → true/false
```

---

## 五、读/写属性

```js
// 通用属性
element.setAttribute('disabled', '')    // 设任意属性
element.getAttribute('href')            // 读任意属性
element.removeAttribute('disabled')     // 删属性

// 输入框专用
inputElement.value                      // 读输入框的值
inputElement.value = '新值'             // 写输入框的值
inputElement.placeholder                // 读/写提示文字
```

---

## 六、创建、插入、删除

```js
// 创建
const div = document.createElement('div')     // 创建一个新的 div 节点（在内存里，不在页面上）

// 插入
parent.appendChild(div)                       // 挂到父节点的最后一个子节点后面
parent.insertBefore(div, 参考节点)             // 插在某个节点前面

// 删除
element.remove()                              // 从树上摘掉自己
parent.removeChild(子节点)                     // 父节点摘掉子节点

// 清空
element.replaceChildren()                     // 删掉所有子节点
```

---

## 七、事件监听

```js
element.addEventListener('click', () => {
  console.log('被点了')
})

element.addEventListener('input', (event) => {
  console.log('输入框内容变了:', event.target.value)
})
```

---

## 八、Vue 模板到 DOM 操作的映射

| Vue 写法 | 底层 DOM 操作 |
|----------|-------------|
| `{{ message }}` | `element.textContent = message` |
| `v-if="show"` | `element.style.display = show ? '' : 'none'` |
| `v-model="username"` | `input.addEventListener('input', ...)` + `element.value = username` |
| `@click="fn"` | `element.addEventListener('click', fn)` |
| `<div :class="cls">` | `element.classList.add/remove(cls)` |
| `<img :src="url">` | `element.setAttribute('src', url)` |

Vue 的价值：你不需要手动写第一列的 DOM 操作——Vue 自动生成它们。但知道这张映射表，Vue 的每个语法就不再是魔法。
