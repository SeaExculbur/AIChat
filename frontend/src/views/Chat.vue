<script setup>
import { ref, nextTick } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()

// 消息列表——每条 { role: 'user'|'assistant', content: '...' }
const messages = ref([])

// 输入框内容
const inputText = ref('')

// 是否正在等待 AI 回复
const isWaiting = ref(false)

// 消息列表的 DOM 引用——用于自动滚到底部
const messageBox = ref(null)

// 滚到消息列表最底部
const scrollToBottom = async () => {
  await nextTick()
  if (messageBox.value) {
    messageBox.value.scrollTop = messageBox.value.scrollHeight
  }
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
      body: JSON.stringify({ message: text })
    })

    if (!response.ok) throw new Error(`HTTP ${response.status}`)

    // ③ 逐块读取 SSE 流
    const reader = response.body.getReader()
    const decoder = new TextDecoder()        // 把字节数组转成字符串
    let buffer = ''                          // 存不完整的 SSE 行

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

        const word = line.slice(6)   // 切掉 "data: " 前缀

        if (word === '[DONE]') break    // 流结束
        if (word === '[ERROR]') throw new Error('SSE error')

        // ⑤ 追加到 AI 气泡
        messages.value[aiIndex].content += word
        await scrollToBottom()
      }
    }

  } catch (error) {
    console.error('流式请求失败:', error)
    // 如果 AI 回复为空，把占位气泡删掉
    if (messages.value[aiIndex] && !messages.value[aiIndex].content) {
      messages.value.pop()
    }
  } finally {
    isWaiting.value = false
    await scrollToBottom()
  }
}
</script>

<template>
  <div class="chat-page">

    <!-- ======== 顶部导航栏 ======== -->
    <header class="topbar">
      <span class="logo">AIChat</span>
      <button class="logout-btn" @click="router.replace('/login')">退出</button>
    </header>

    <!-- ======== 消息列表 ======== -->
    <div class="message-box" ref="messageBox">
      <!-- 空状态提示 -->
      <div v-if="messages.length === 0" class="empty-hint">
        <h2>有什么可以帮你的？</h2>
        <p>输入消息开始与 DeepSeek 对话</p>
      </div>

      <!-- 消息气泡 -->
      <div
        v-for="(msg, index) in messages"
        :key="index"
        :class="msg.role === 'user' ? 'user-bubble' : 'ai-bubble'">

          <p>{{ msg.content }}</p>
      </div>

      <!-- 等待指示器 -->
      <div v-if="isWaiting" class="ai-bubble">
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
</template>

<style scoped>
/* ======== 整体布局 ======== */
.chat-page {
  display: flex;
  flex-direction: column;       /* 从上到下：导航 → 消息区 → 输入区 */
  height: 100vh;                 /* 占满全屏 */
  background-color: #f7f8fa;     /* 浅灰背景 */
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
  border-top: 1px solid #e8e8e8;
}

.input-bar input {
  flex: 1;
  padding: 10px 16px;
  border: 1px solid #d9d9d9;
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
