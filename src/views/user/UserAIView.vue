<template>
  <div class="ai-page">
    <h2 class="page-title gradient-text">智能问答</h2>

    <div class="chat-container glass-card">
      <!-- 消息列表 -->
      <div class="chat-messages" ref="chatBoxRef">
        <!-- 欢迎 & 快捷问题 -->
        <div v-if="messages.length === 0" class="welcome-area">
          <div class="welcome-icon">
            <svg viewBox="0 0 24 24" width="56" height="56" fill="none" stroke="currentColor" stroke-width="1.5" style="color: var(--color-primary-light)">
              <path d="M12 2a7 7 0 0 1 7 7c0 2.38-1.19 4.47-3 5.74V17a2 2 0 0 1-2 2H10a2 2 0 0 1-2-2v-2.26C6.19 13.47 5 11.38 5 9a7 7 0 0 1 7-7z" />
              <line x1="9" y1="21" x2="15" y2="21" />
            </svg>
          </div>
          <h3 class="welcome-title">NeuroHand 智能助手</h3>
          <p class="welcome-desc">我可以帮您查看设备状态、分析训练数据、提供康复建议</p>
          <div class="quick-questions">
            <button v-for="q in quickQuestions" :key="q" class="quick-btn glass-card" @click="quickAsk(q)">
              {{ q }}
            </button>
          </div>
        </div>

        <!-- 消息气泡 -->
        <div v-for="msg in messages" :key="msg.id" class="msg-row" :class="msg.role">
          <div class="msg-avatar">
            <el-avatar :size="36" v-if="msg.role === 'ai'" class="ai-avatar">AI</el-avatar>
            <el-avatar :size="36" v-else class="user-avatar">{{ userInitial }}</el-avatar>
          </div>
          <div class="msg-bubble" :class="msg.role">
            <p>{{ msg.content }}</p>
          </div>
        </div>

        <!-- 打字指示器 -->
        <div v-if="isTyping" class="msg-row ai">
          <div class="msg-avatar">
            <el-avatar :size="36" class="ai-avatar">AI</el-avatar>
          </div>
          <div class="msg-bubble ai typing-bubble">
            <span class="typing-dot"></span>
            <span class="typing-dot"></span>
            <span class="typing-dot"></span>
          </div>
        </div>
      </div>

      <!-- 输入区域 -->
      <div class="chat-input-bar">
        <el-input
          v-model="inputValue"
          placeholder="输入您的问题..."
          @keydown.enter.exact.prevent="sendMessage"
          size="large"
          clearable
        />
        <el-button type="primary" size="large" :disabled="!inputValue.trim()" @click="sendMessage" class="send-btn">
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="22" y1="2" x2="11" y2="13" /><polygon points="22 2 15 22 11 13 2 9 22 2" />
          </svg>
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, computed } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { sendChatMessage } from '@/api/ai'

const authStore = useAuthStore()
const userInitial = computed(() => authStore.user?.name?.[0] || 'U')

interface Message {
  id: number
  role: 'user' | 'ai'
  content: string
}

let msgId = 0
const messages = ref<Message[]>([])
const inputValue = ref('')
const isTyping = ref(false)
const chatBoxRef = ref<HTMLElement>()

const quickQuestions = [
  '我的假手昨天报错了几次？',
  '最近肌电数据是否正常？',
  '如何进行康复训练？',
  '设备电量还剩多少？',
]

function scrollToBottom() {
  nextTick(() => {
    if (chatBoxRef.value) {
      chatBoxRef.value.scrollTop = chatBoxRef.value.scrollHeight
    }
  })
}

function quickAsk(q: string) {
  inputValue.value = q
  sendMessage()
}

async function sendMessage() {
  const content = inputValue.value.trim()
  if (!content) return

  messages.value.push({ id: ++msgId, role: 'user', content })
  inputValue.value = ''
  isTyping.value = true
  scrollToBottom()

  const res = await sendChatMessage(content)
  isTyping.value = false
  messages.value.push({
    id: ++msgId,
    role: 'ai',
    content: res.reply || res.message || JSON.stringify(res),
  })
  scrollToBottom()
}
</script>

<style scoped>
.ai-page { display: flex; flex-direction: column; height: calc(100vh - var(--header-height) - 48px); }
.page-title { font-size: 28px; font-weight: 700; margin-bottom: 16px; flex-shrink: 0; }

.chat-container {
  flex: 1; display: flex; flex-direction: column; overflow: hidden;
  padding: 0 !important; border-radius: 16px !important;
}

/* 消息区 */
.chat-messages { flex: 1; overflow-y: auto; padding: 24px; }

/* 欢迎区 */
.welcome-area { display: flex; flex-direction: column; align-items: center; padding: 48px 0; }
.welcome-icon { margin-bottom: 16px; }
.welcome-title { font-size: 22px; font-weight: 700; margin-bottom: 8px; }
.welcome-desc { color: var(--color-text-muted); font-size: 14px; margin-bottom: 32px; }
.quick-questions { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; width: 100%; max-width: 500px; }
.quick-btn {
  padding: 14px 16px !important; text-align: left; font-size: 13px; cursor: pointer;
  border: 1px solid rgba(99,102,241,0.15) !important; transition: all 0.2s;
  color: var(--color-text); line-height: 1.5;
}
.quick-btn:hover { border-color: var(--color-primary) !important; transform: translateY(-2px); }

/* 消息行 */
.msg-row { display: flex; gap: 12px; margin-bottom: 16px; }
.msg-row.user { flex-direction: row-reverse; }
.msg-avatar { flex-shrink: 0; }
.ai-avatar { background: linear-gradient(135deg, #6366f1, #8b5cf6); color: #fff; font-weight: 700; font-size: 13px; }
.user-avatar { background: linear-gradient(135deg, #06b6d4, #22d3ee); color: #fff; font-weight: 600; }

.msg-bubble {
  max-width: 70%; padding: 12px 16px; border-radius: 16px; font-size: 14px; line-height: 1.7;
}
.msg-bubble.ai {
  background: rgba(30, 41, 59, 0.8); color: #e2e8f0;
  border-bottom-left-radius: 4px;
}
.msg-bubble.user {
  background: linear-gradient(135deg, var(--color-primary), var(--color-accent));
  color: #fff; border-bottom-right-radius: 4px;
}
.msg-bubble p { margin: 0; }

/* 打字指示器 */
.typing-bubble { display: flex; align-items: center; gap: 4px; padding: 14px 20px; }
.typing-dot {
  width: 8px; height: 8px; border-radius: 50%; background: #64748b;
  animation: typing-bounce 1.2s infinite;
}
.typing-dot:nth-child(2) { animation-delay: 0.2s; }
.typing-dot:nth-child(3) { animation-delay: 0.4s; }
@keyframes typing-bounce {
  0%, 60%, 100% { transform: translateY(0); opacity: 0.4; }
  30% { transform: translateY(-6px); opacity: 1; }
}

/* 输入栏 */
.chat-input-bar {
  display: flex; gap: 12px; padding: 16px 24px;
  border-top: 1px solid rgba(99,102,241,0.1);
  background: rgba(15,23,42,0.6); backdrop-filter: blur(8px);
}
.chat-input-bar :deep(.el-input__wrapper) {
  background: rgba(30, 41, 59, 0.6) !important;
  border: 1px solid rgba(99,102,241,0.2);
  border-radius: 12px; box-shadow: none !important;
}
.send-btn {
  width: 48px; height: 48px; border-radius: 12px; padding: 0;
  display: flex; align-items: center; justify-content: center;
  background: linear-gradient(135deg, var(--color-primary), var(--color-accent)); border: none;
}
.send-btn:hover { transform: scale(1.05); }
</style>
