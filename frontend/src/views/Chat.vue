<script setup>
import { ref, nextTick, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'

const router = useRouter()

// 消息列表——每条 { role: 'user'|'assistant', content: '...' }
const messages = ref([])

// 输入框内容
const inputText = ref('')

// 是否正在等待 AI 回复
const isWaiting = ref(false)

// 消息列表的 DOM 引用——用于自动滚到底部
const messageBox = ref(null)

// 会话列表——每条 { id, title, updated_at }
const conversations = ref([])

// 当前选中的会话 ID，null = 新会话（还没发过消息）
const currentConvId = ref(null)

// 当前会话已加载到第几页（滚动加载用）
const currentPage = ref(1)

// 还有更多历史页吗（滚动到顶再加载）
const hasMore = ref(false)

// 滚到消息列表最底部
const scrollToBottom = async () => {
  await nextTick()
  if (messageBox.value) {
    messageBox.value.scrollTop = messageBox.value.scrollHeight
  }
}

// 时间格式化——统一把时间字符串转成 "2026-08-14 10:30" 
const formatTime = (timeStr) => {
  if (!timeStr) return ''
  return new Date(timeStr).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

const handleNewConversation = (id, title) => {
  if (currentConvId.value === null) {
    // 新的会话状态，加到左侧列表顶部
    conversations.value.unshift({
      id: id,
      title: title || '新对话',
      updated_at: new Date().toISOString()
    })
  }
  currentConvId.value = id
}

// 点击会话条目
const selectConversation = async (id) => {
  if (isWaiting.value) return                 // ① 正在等 AI 回复——不许切
  if (id === currentConvId.value) return      // ② 点的就是当前会话——不重复加载

  currentConvId.value = id                    // ③ 切换当前会话
  currentPage.value = 1                       // ④ 分页重置到第一页

  const token = localStorage.getItem('token')

  try {
    const res = await axios.get(`/api/conversations/${id}?page=1&per_page=20`, {
      headers: { Authorization: `Bearer ${token}` }
    })
    messages.value = res.data.messages.reverse()   // ⑤ 降序 → 反转成正序
    hasMore.value = res.data.page < res.data.pages  // ⑥ 还有更早的消息吗
    await scrollToBottom()
  } catch (err) {
    console.error('加载会话失败:', err)
  }
}

// "+ 新对话"——清空回到新会话状态
const startNewChat = () => {
  if (isWaiting.value) return
  currentConvId.value = null
  messages.value = []
  inputText.value = ''
  currentPage.value = 1
  hasMore.value = false
}

// 发送消息
const sendMessage = async () => {
  const text = inputText.value.trim()
  if (!text || isWaiting.value) return

  // ① 用户消息上屏
  messages.value.push({ role: 'user', content: text })
  inputText.value = ''
  await scrollToBottom()

  // ② AI 占位——先放一个空气泡，后面逐字填充
  const aiIndex = messages.value.length
  messages.value.push({ role: 'assistant', content: '' })
  isWaiting.value = true

  const token = localStorage.getItem('token')

  try {
    const response = await fetch('/api/chat', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({ message: text,
        conversation_id: currentConvId.value
       })
    })

    if (!response.ok) throw new Error(`HTTP ${response.status}`)

    // ③ 逐块读取 SSE 流
    const reader = response.body.getReader()
    const decoder = new TextDecoder()        // 把字节数组转成字符串
    let buffer = ''                          // 存不完整的 SSE 行
    let isFirstChunk = true

    while (true) {
      const { done, value } = await reader.read()   // 读下一块字节
      if (done) break

      buffer += decoder.decode(value, { stream: true })   // 拼到缓冲区

      // ④ 解析 SSE——每行 "data: 字\n\n"
      const lines = buffer.split('\n')
      buffer = lines.pop()           // 最后一段可能是半行，留着下次拼

      for (let i = 0; i < lines.length; i++) {
        const line = lines[i].trim()
        if (!line.startsWith('data: ')) continue

        const raw = line.slice(6)

      if (raw === '[DONE]') break
      if (raw === '[DB_ERROR]') throw new Error('DB error')
      if (raw === '[ERROR]') throw new Error('SSE error')

      const payload = JSON.parse(raw)      // 首帧是对象，正文帧是字符串

      if (isFirstChunk) {
        isFirstChunk = false
        if (payload && typeof payload === 'object' && payload.conversation_id) {
          handleNewConversation(payload.conversation_id, payload.title)
          continue
        }
      }

      messages.value[aiIndex].content += payload

        await scrollToBottom()
      }
    }

  } catch (error) {
    console.error('流式请求失败:', error)

    if (error.message === 'HTTP 401') {
    messages.value[aiIndex].content = '登录已过期，请重新登录...'
    setTimeout(() => router.replace('/login'), 2000) 
  } else {
      // 网络断开、DeepSeek 限流、服务器500 错误提示
      messages.value[aiIndex].content = 'AI 回复失败，请重试'
    }
  
    // 如果 AI 回复为空，把占位气泡删掉
    if (messages.value[aiIndex] && !messages.value[aiIndex].content) {
      messages.value.pop()
    }

  } finally {
    isWaiting.value = false
    await scrollToBottom()
  }
}

onMounted(async () => {
  const token = localStorage.getItem('token')
  if (!token) return

  try {
    const res = await axios.get('/api/conversations', {
      headers: { Authorization: `Bearer ${token}` }
    })
    conversations.value = res.data
  } catch (err) {
    console.error('加载会话列表失败:', err)
  }
})

const logout = () => {
  localStorage.removeItem('token')
  router.replace('/login')
}

</script>

<template>
  <div class="chat-page">

    <!-- ======== 左侧：会话列表 ======== -->
  <aside class="sidebar">
    <button class="new-chat-btn" @click="startNewChat">+ 新对话</button>
<div class="conv-list">
  <div
    v-for="conv in conversations"
    :key="conv.id"
    class="conv-item"
    :class="{ active: conv.id === currentConvId }"
    @click="selectConversation(conv.id)"
  >
    <span class="conv-title">{{ conv.title }}</span>
    <span class="conv-time">{{ formatTime(conv.updated_at) }}</span>
  </div>
</div>

  </aside>

  <!-- ========== 右侧：聊天区 ======== -->
   <div class="chat-body">
      <!-- ======== 顶部导航栏 ======== -->
      <header class="topbar">
        <span class="logo">AIChat</span>
        <button class="logout-btn" @click="logout">退出</button>
      </header>

      <!-- ======== 消息列表 ======== -->
      <div class="message-box" ref="messageBox">
        <!-- 空状态提示 -->
        <div v-if="messages.length === 0" class="empty-hint">
          <h2>有什么可以帮你的？</h2>
          <p>输入消息开始与 DeepSeek 对话</p>
        </div>

        <!-- 消息气泡 -->
        <template v-for="(msg, index) in messages" :key="index">
        <div
          v-if="msg.content !== ''"
          :class="msg.role === 'user' ? 'user-bubble' : 'ai-bubble'">
          <p>{{ msg.content }}</p>
        </div>
      </template>

        <!-- 等待指示器 -->
        <div v-if="isWaiting && messages[messages.length - 1]?.content === ''" class="ai-bubble">
            <span class="dot">●</span>
            <span class="dot">●</span>
            <span class="dot">●</span>
        </div>
      </div>

      <!-- ======== 底部输入区 ======== -->
      <div class="input-bar">
        <input
          v-model="inputText"
          type="text"
          placeholder="输入消息..."
          @keydown.enter="sendMessage"
        />
        <button
          class="send-btn"
          :disabled="!inputText.trim() || isWaiting"
          @click="sendMessage"
        >
          发送
        </button>
      </div>

    </div>

  </div>
</template>

<style scoped>
/* ======== 整体布局 ======== */
.chat-page {
  display: flex;
  flex-direction: row;       /* 从上到下：导航 → 消息区 → 输入区 */
  height: 100vh;                 /* 占满全屏 */
  background-color: #f7f8fa;     /* 浅灰背景 */
}

/* ======== 左侧会话栏 ======== */
.sidebar {
  width: 260px;
  background-color: #fff;
  border-right: 1px solid #e8e8e8;
  display: flex;
  flex-direction: column;
  padding: 16px 12px;
  flex-shrink: 0;            /* 不随窗口缩小被压扁 */
}

.new-chat-btn {
  width: 100%;
  padding: 10px 0;
  background-color: #1677ff;
  color: #fff;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  cursor: pointer;
  margin-bottom: 12px;
}

.conv-list {
  flex: 1;                   /* 占满侧栏剩余空间 */
  overflow-y: auto;          /* 会话多了可滚动 */
}

/* 会话条目 */
.conv-item {
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  margin-bottom: 4px;
}

.conv-item:hover {
  background-color: #f0f2f5;   /* 悬停——浅灰 */
}

.conv-item.active {
  background-color: #e6f0ff;   /* 当前选中——浅蓝 */
}

.conv-title {
  display: block;
  font-size: 14px;
  color: #333;
  overflow: hidden;
  text-overflow: ellipsis;     /* 标题太长——省略号 */
  white-space: nowrap;
}

.conv-time {
  display: block;
  font-size: 12px;
  color: #999;
  margin-top: 4px;
}

/* ======== 右侧聊天区 ======== */
.chat-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;              /* 防止消息气泡把 chat-body 撑爆 */
}

/* ======== 顶部导航 ======== */
.topbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 24px;
  background-color: #fff;
  border-bottom: 1px solid #e8e8e8;
}

.logo {
  font-size: 18px;
  font-weight: 600;
  color: #1a1a1a;
}

.logout-btn {
  padding: 6px 16px;
  border: 1px solid #d9d9d9;
  border-radius: 6px;
  background: #fff;
  color: #666;
  cursor: pointer;
  font-size: 14px;
}

.logout-btn:hover {
  color: #ff4d4f;
  border-color: #ff4d4f;
}

/* ======== 消息列表 ======== */
.message-box {
  flex: 1;                       /* 占满剩余空间 */
  overflow-y: auto;              /* 消息多了可滚动 */
  padding: 24px 0;
}

/* 空状态 */
.empty-hint {
  text-align: center;
  margin-top: 120px;
}

.empty-hint h2 {
  font-size: 24px;
  color: #1a1a1a;
  margin-bottom: 8px;
}

.empty-hint p {
  font-size: 14px;
  color: #999;
}


/* ======== 用户气泡——靠右、蓝色 ======== */
.user-bubble {
  width: fit-content;
  max-width: 70%;
  margin-left: auto;                  /* 推到右边 */
  background-color: #1677ff;
  color: #fff;
  border-radius: 12px;
  border-bottom-right-radius: 4px;   /* 右下小尾巴 */
  padding: 12px 16px;
  margin-bottom: 16px;
  font-size: 15px;
  line-height: 1.6;
  word-break: break-word;
}

.user-bubble p {
  margin: 0;
  white-space: pre-wrap;
}

/* ======== AI 气泡——靠左、白色 ======== */
.ai-bubble {
  width: fit-content;
  max-width: 70%;
  margin-right: auto;                 /* 推到左边 */
  background-color: #fff;
  border: 1px solid #e8e8e8;
  border-radius: 12px;
  border-bottom-left-radius: 4px;    /* 左下小尾巴 */
  padding: 12px 16px;
  margin-bottom: 16px;
  font-size: 15px;
  line-height: 1.6;
  word-break: break-word;
}

.ai-bubble p {
  margin: 0;
  white-space: pre-wrap;
}

/* ======== 等待动画 ======== */
.waiting {
  display: flex;
  gap: 6px;
  padding: 14px 20px;
}

.dot {
  font-size: 8px;
  color: #999;
  animation: blink 1.4s infinite;
}

.dot:nth-child(2) { animation-delay: 0.2s; }
.dot:nth-child(3) { animation-delay: 0.4s; }

@keyframes blink {
  0%, 60%, 100% { opacity: 0.2; }
  30% { opacity: 1; }
}

/* ======== 底部输入区 ======== */
.input-bar {
  display: flex;
  gap: 12px;
  padding: 16px 24px;
  background-color: #fff;
  border-top: 1px solid #0a0a0a;
}

.input-bar input {
  flex: 1;
  padding: 10px 16px;
  border: 2px solid #ababab;
  border-radius: 8px;
  font-size: 14px;
  outline: none;
}

.input-bar input:focus {
  border-color: #1677ff;
}

.send-btn {
  padding: 10px 24px;
  background-color: #1677ff;
  color: #fff;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  cursor: pointer;
}

.send-btn:hover {
  background-color: #4096ff;
}

.send-btn:disabled {
  background-color: #d9d9d9;
  cursor: not-allowed;
}
</style>
