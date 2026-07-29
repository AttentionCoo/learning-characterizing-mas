<script setup>
import { ref, onMounted, nextTick, computed } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import { getTutorConversationsAPI, getTutorConversationHistoryAPI, deleteTutorConversationAPI, tutorStreamAPI } from '@/api/tutor'
import AppAvatar from '@/components/AppAvatar.vue'
import ImageUploader from '@/components/ImageUploader.vue'
import ReasoningTrace from '@/components/ReasoningTrace.vue'
import { useUserStore } from '@/stores/user'
import { useReasoningTrace } from '@/composables/useReasoningTrace'
import { normalizeAiMarkdown } from '@/utils/aiMarkdown'

const userStore = useUserStore()

marked.setOptions({ gfm: true, breaks: true })

const MAX_CONVERSATIONS = 50

const conversations = ref([])
const conversationsLoading = ref(false)
const activeConversationId = ref(null)
const chatMessages = ref([])
const draftMessage = ref('')
const isStreaming = ref(false)
const isThinking = ref(false)
const thinkingHint = ref('')
const currentStage = ref('')
const talkId = ref(null)
const chatContainerRef = ref(null)
const inputRef = ref(null)
const shouldAutoScroll = ref(true)
const { reasoningEntries, resetReasoningTrace, appendReasoningEvent } = useReasoningTrace()

const showSidebar = ref(true)
const uploadedImages = ref([])
const showImageUploader = ref(false)

function renderMarkdown(text) {
  if (!text) return ''
  return DOMPurify.sanitize(marked.parse(normalizeAiMarkdown(text)))
}

onMounted(() => {
  fetchConversations()
  chatMessages.value.push({
    role: 'assistant',
    content: '你好！我是你的脑卒中智能辅导助手 🎓\n\n我可以为你解答脑卒中相关问题、讲解神经病学知识点、分析脑血管病例，并提供多模态辅导支持。\n\n请随时向我提问！',
  })
})

async function fetchConversations() {
  conversationsLoading.value = true
  try {
    const res = await getTutorConversationsAPI()
    let convList = res.data || []
    convList.sort((a, b) => new Date(b.updateTime || b.createTime || 0) - new Date(a.updateTime || a.createTime || 0))
    if (convList.length > MAX_CONVERSATIONS) {
      const toDelete = convList.slice(MAX_CONVERSATIONS)
      convList = convList.slice(0, MAX_CONVERSATIONS)
      toDelete.forEach(async (conv) => {
        try { await deleteTutorConversationAPI(conv.talkId) } catch {}
      })
    }
    conversations.value = convList
  } catch {
    // ignore
  } finally {
    conversationsLoading.value = false
  }
}

async function selectConversation(conv) {
  resetReasoningTrace()
  activeConversationId.value = conv.talkId
  talkId.value = conv.talkId
  try {
    const res = await getTutorConversationHistoryAPI(conv.talkId)
    chatMessages.value = (res.data || []).map(m => ({
      role: m.role,
      content: m.content,
    }))
    await nextTick()
    scrollToBottom()
  } catch {
    // ignore
  }
}

function startNewConversation() {
  resetReasoningTrace()
  activeConversationId.value = null
  talkId.value = null
  chatMessages.value = [{
    role: 'assistant',
    content: '开始新的辅导对话吧！请告诉我你想学习或讨论的内容。',
  }]
}

async function deleteConversation(conv, e) {
  e.stopPropagation()
  try {
    await deleteTutorConversationAPI(conv.talkId)
    conversations.value = conversations.value.filter(c => c.talkId !== conv.talkId)
    if (activeConversationId.value === conv.talkId) {
      startNewConversation()
    }
  } catch {
    // ignore
  }
}

async function handleSend() {
  const message = draftMessage.value.trim()
  if (!message || isStreaming.value) return

  draftMessage.value = ''
  shouldAutoScroll.value = true
  showImageUploader.value = false

  // 保存当前图片并清空上传列表
  const currentImages = [...uploadedImages.value]
  uploadedImages.value = []

  // 将图片信息附到消息上
  const userMsg = { role: 'user', content: message }
  if (currentImages.length > 0) {
    userMsg.images = currentImages
  }
  chatMessages.value.push(userMsg)
  chatMessages.value.push({ role: 'assistant', content: '' })
  const aiIndex = chatMessages.value.length - 1

  isStreaming.value = true
  isThinking.value = true
  thinkingHint.value = '正在思考...'
  resetReasoningTrace()

  let displayText = ''
  const charBuffer = []
  let timerId = null

  function startTypewriter() {
    if (timerId !== null) return
    function tick() {
      if (charBuffer.length === 0) { timerId = null; return }
      const pending = charBuffer.length
      const delay = pending > 200 ? 2 : pending > 50 ? 8 : 25
      const chars = charBuffer.splice(0, 2)
      displayText += chars.join('')
      chatMessages.value[aiIndex] = { role: 'assistant', content: displayText }
      if (shouldAutoScroll.value) {
        nextTick(() => scrollToBottom())
      }
      timerId = setTimeout(tick, delay)
    }
    timerId = setTimeout(tick, 0)
  }

  try {
    const result = await tutorStreamAPI(
      { talkId: talkId.value, message, images: currentImages },
      (chunk, event = {}) => {
        if (isThinking.value) { isThinking.value = false; thinkingHint.value = '' }
        if (event.replace) {
          if (timerId !== null) { clearTimeout(timerId); timerId = null }
          charBuffer.length = 0
          displayText = chunk
          chatMessages.value[aiIndex] = { role: 'assistant', content: displayText }
          return
        }
        charBuffer.push(...Array.from(chunk))
        startTypewriter()
      },
      (thinking) => {
        const title = thinking.title || 'AI 思考中...'
        thinkingHint.value = title
        currentStage.value = title
        appendReasoningEvent(thinking)
      },
    )

    if (timerId !== null) { clearTimeout(timerId); timerId = null }
    const content = result.data?.content || displayText
    chatMessages.value[aiIndex] = { role: 'assistant', content }
    if (result.data?.talkId) talkId.value = result.data.talkId

    await fetchConversations()
  } catch (error) {
    console.error('辅导对话失败', error)
    chatMessages.value.splice(aiIndex, 1)
  } finally {
    isStreaming.value = false
    isThinking.value = false
    thinkingHint.value = ''
    currentStage.value = ''
  }

  await nextTick()
  scrollToBottom()
}

function scrollToBottom() {
  if (chatContainerRef.value) {
    chatContainerRef.value.scrollTo({
      top: chatContainerRef.value.scrollHeight,
      behavior: 'smooth'
    })
  }
}

function handleScroll() {
  if (!chatContainerRef.value) return
  const { scrollTop, scrollHeight, clientHeight } = chatContainerRef.value
  const distanceFromBottom = scrollHeight - scrollTop - clientHeight
  shouldAutoScroll.value = distanceFromBottom < 100
}

function formatTime(timeStr) {
  if (!timeStr) return ''
  const date = new Date(timeStr)
  const now = new Date()
  const diff = now - date
  const minutes = Math.floor(diff / 60000)
  const hours = Math.floor(diff / 3600000)
  const days = Math.floor(diff / 86400000)

  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes}分钟前`
  if (hours < 24) return `${hours}小时前`
  if (days < 7) return `${days}天前`

  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  const currentYear = now.getFullYear()
  if (year === currentYear) {
    return `${month}-${day}`
  }
  return `${year}-${month}-${day}`
}

function handleKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    handleSend()
  }
}

const quickQuestions = [
  '讲解缺血性脑卒中的TOAST分型',
  '脑卒中静脉溶栓的适应症与禁忌症',
  '脑出血与脑梗死的鉴别诊断',
  '脑卒中二级预防的抗血小板策略',
]

/** 判断 Base64 data URL 是否为 DICOM 文件 */
function isDICOMDataUrl(dataUrl) {
  if (!dataUrl || typeof dataUrl !== 'string') return false
  return dataUrl.includes('application/dicom') ||
         dataUrl.includes('application/octet-stream') ||
         /\.dcm/i.test(dataUrl)
}
</script>

<template>
  <div class="tutor-page">
    <div class="page-header">
      <div class="header-content">
        <h1>智能辅导</h1>
        <p>脑卒中多模态智能答疑，个性化辅导支持</p>
      </div>
      <div class="header-badge">核心功能4 · 必选</div>
    </div>

    <div class="tutor-body">
      <div class="chat-area">
        <div class="chat-messages" ref="chatContainerRef" @scroll="handleScroll">
          <div
            v-for="(msg, idx) in chatMessages"
            :key="idx"
            class="chat-message"
            :class="msg.role"
          >
            <div class="message-avatar">
              <span v-if="msg.role === 'assistant'" class="avatar-ai">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
                  <rect x="3" y="8" width="18" height="12" rx="3" fill="url(#tutor-grad)" opacity="0.95"/>
                  <circle cx="9" cy="14" r="1.5" fill="#fff"/>
                  <circle cx="15" cy="14" r="1.5" fill="#fff"/>
                  <path d="M10 17c1 .7 3 .7 4 0" stroke="#fff" stroke-width="1.2" stroke-linecap="round"/>
                  <path d="M8 8V5a4 4 0 0 1 8 0v3" stroke="url(#tutor-grad)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                  <circle cx="12" cy="4" r="1" fill="#11967f"/>
                  <defs>
                    <linearGradient id="tutor-grad" x1="3" y1="8" x2="21" y2="20">
                      <stop stop-color="#11967f"/>
                      <stop offset="1" stop-color="#0ea5e9"/>
                    </linearGradient>
                  </defs>
                </svg>
              </span>
              <AppAvatar v-else :src="userStore.image" :name="userStore.name" :size="40" />
            </div>
            <div class="message-body">
              <div v-if="msg.role === 'assistant' && idx === chatMessages.length - 1 && isThinking && !msg.content && !reasoningEntries.length" class="thinking-indicator">
                <div class="thinking-dots"><span></span><span></span><span></span></div>
                <span class="thinking-text">{{ thinkingHint }}</span>
              </div>
              <ReasoningTrace
                v-if="msg.role === 'assistant' && idx === chatMessages.length - 1"
                :entries="reasoningEntries"
                :running="isStreaming"
              />
              <div v-if="msg.role === 'assistant'" class="message-content markdown-body" v-html="renderMarkdown(msg.content)"></div>
              <div v-else class="message-content markdown-body" v-html="renderMarkdown(msg.content)"></div>
              <!-- 用户消息中的医学影像 -->
              <div v-if="msg.role === 'user' && msg.images?.length" class="message-images">
                <div
                  v-for="(img, idx) in msg.images"
                  :key="idx"
                  class="message-image-thumb"
                >
                  <img v-if="!isDICOMDataUrl(img)" :src="img" alt="上传的医学影像" />
                  <div v-else class="msg-dicom-badge">🏥 DICOM</div>
                </div>
              </div>
              <div v-if="msg.role === 'assistant' && idx === chatMessages.length - 1 && isStreaming && !isThinking && currentStage" class="stage-bar">
                <span class="stage-dot"></span>
                <span class="stage-text">{{ currentStage }}</span>
              </div>
            </div>
          </div>
        </div>

        <div v-if="chatMessages.length <= 1" class="quick-questions">
          <div class="quick-label">快速提问</div>
          <div class="quick-list">
            <button v-for="q in quickQuestions" :key="q" class="quick-btn" @click="draftMessage = q; handleSend()">
              {{ q }}
            </button>
          </div>
        </div>

        <div class="chat-input-area">
          <!-- 已上传图片预览行 -->
          <div class="upload-preview-row" v-if="uploadedImages.length > 0">
            <div
              v-for="(img, idx) in uploadedImages"
              :key="idx"
              class="upload-thumb"
            >
              <img v-if="!isDICOMDataUrl(img)" :src="img" alt="预览" />
              <div v-else class="dicom-thumb-badge">🏥<br/>DICOM</div>
              <button class="upload-thumb-remove" @click="uploadedImages.splice(idx, 1)">✕</button>
            </div>
            <span class="upload-count">已上传 {{ uploadedImages.length }} 张影像</span>
          </div>

          <!-- ImageUploader 面板 -->
          <div class="image-uploader-panel" v-if="showImageUploader">
            <div class="uploader-header">
              <span>📷 上传医学影像</span>
              <button class="uploader-close" @click="showImageUploader = false">✕</button>
            </div>
            <ImageUploader
              v-model:images="uploadedImages"
              :max-count="3"
              :max-size-mb="10"
            />
            <div class="uploader-footer">
              <span class="uploader-hint">支持 JPG/PNG/WebP/DICOM(.dcm) · 最多3张 · 单张最大10MB</span>
            </div>
          </div>

          <div class="input-wrapper">
            <textarea
              ref="inputRef"
              v-model="draftMessage"
              placeholder="输入你的脑卒中相关问题..."
              rows="1"
              :disabled="isStreaming"
              @keydown="handleKeydown"
              @input="($event.target.style.height = 'auto'), ($event.target.style.height = $event.target.scrollHeight + 'px')"
            ></textarea>
            <button
              class="attach-btn"
              :class="{ active: showImageUploader || uploadedImages.length > 0 }"
              @click="showImageUploader = !showImageUploader"
              title="上传医学影像"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
                <circle cx="8.5" cy="8.5" r="1.5"/>
                <polyline points="21 15 16 10 5 21"/>
              </svg>
            </button>
            <button class="send-btn" :disabled="!draftMessage.trim() || isStreaming" @click="handleSend">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <line x1="22" y1="2" x2="11" y2="13"/>
                <polygon points="22 2 15 22 11 13 2 9 22 2"/>
              </svg>
            </button>
          </div>
        </div>
      </div>

      <div class="conversation-sidebar">
        <div class="sidebar-header">
          <span class="sidebar-title">对话历史</span>
          <button class="new-chat-btn" @click="startNewConversation">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
            </svg>
            新对话
          </button>
        </div>

        <div class="conversation-list">
          <div v-if="conversationsLoading" class="list-loading">
            <div class="loading-spinner"></div>
          </div>
          <div v-else-if="!conversations.length" class="list-empty">
            <span>暂无对话</span>
          </div>
          <div
            v-else
            v-for="conv in conversations"
            :key="conv.talkId"
            class="conv-item"
            :class="{ active: activeConversationId === conv.talkId }"
            @click="selectConversation(conv)"
          >
            <div class="conv-icon">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
              </svg>
            </div>
            <div class="conv-info">
              <div class="conv-title">{{ conv.title || '新对话' }}</div>
              <div class="conv-time">{{ formatTime(conv.updateTime || conv.createTime) }}</div>
            </div>
            <button class="conv-delete" @click="deleteConversation(conv, $event)">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
              </svg>
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.tutor-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 28px 16px;
  border-bottom: 1px solid var(--color-border-light);
  flex-shrink: 0;
  position: relative;
  overflow: hidden;

  &::after {
    content: '';
    position: absolute;
    bottom: 0; left: 0; right: 0;
    height: 2px;
    background: var(--gradient-aurora-flow);
    background-size: 300% 100%;
    animation: aurora-flow 8s ease infinite;
    opacity: 0.5;
  }
}

.header-content {
  h1 {
    margin: 0;
    font-size: 1.5rem;
    font-weight: 800;
    background: var(--gradient-aurora);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    letter-spacing: -0.02em;
  }
  p { margin: 4px 0 0; font-size: 13px; color: var(--color-text-medium); }
}

.header-badge {
  padding: 5px 14px;
  border-radius: var(--radius-pill);
  font-size: 12px;
  font-weight: 700;
  background: rgba(17, 150, 127, 0.1);
  color: var(--color-primary-dark);
}

.tutor-body {
  flex: 1;
  display: flex;
  min-height: 0;
  overflow: hidden;
}

.chat-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.chat-message {
  display: flex;
  gap: 12px;
  max-width: 85%;

  &.user {
    align-self: flex-end;
    flex-direction: row-reverse;
    .message-body { align-items: flex-end; }
    .message-content {
      background: var(--color-message-user-bg);
      border: 1px solid var(--color-message-user-border);
      border-radius: 16px 16px 4px 16px;
    }
  }

  &.assistant {
    align-self: flex-start;
    .message-content {
      background: var(--color-message-bg);
      border: 1px solid var(--color-border-light);
      border-radius: 16px 16px 16px 4px;
    }
  }
}

.message-avatar {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.avatar-ai {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, rgba(139, 92, 246, 0.08), rgba(17, 150, 127, 0.1));
  border-radius: 12px;
  border: 1px solid rgba(139, 92, 246, 0.12);
  box-shadow:
    0 2px 8px rgba(139, 92, 246, 0.12),
    0 1px 3px rgba(17, 150, 127, 0.08);
  transition: all var(--transition-bounce);
  position: relative;
  overflow: hidden;

  &::before {
    content: '';
    position: absolute;
    inset: 0;
    background: linear-gradient(135deg, rgba(139, 92, 246, 0.06), rgba(14, 165, 233, 0.04));
    opacity: 0;
    transition: opacity 0.3s ease;
  }

  &:hover {
    transform: scale(1.08) rotate(-3deg);
    box-shadow:
      0 4px 20px rgba(139, 92, 246, 0.25),
      0 2px 8px rgba(14, 165, 233, 0.2),
      var(--glow-dreamy);

    &::before { opacity: 1; }
  }

  svg {
    filter: drop-shadow(0 2px 4px rgba(139, 92, 246, 0.2));
  }
}

.avatar-user {
  width: 36px; height: 36px;
  display: flex; align-items: center; justify-content: center;
  background: var(--color-secondary-bg);
  border-radius: 50%;
  font-size: 13px; font-weight: 700; color: var(--color-text-strong);
}

.message-body { display: flex; flex-direction: column; gap: 4px; }

.message-content {
  padding: 12px 16px;
  font-size: 14px;
  line-height: 1.65;
  color: var(--color-text-strong);
  word-break: break-word;
}

.thinking-indicator {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 18px;
  background: linear-gradient(135deg, rgba(139, 92, 246, 0.03), rgba(17, 150, 127, 0.04));
  border: 1px solid rgba(139, 92, 246, 0.12);
  border-radius: 16px 16px 16px 4px;
  box-shadow:
    0 2px 8px rgba(139, 92, 246, 0.06),
    inset 0 1px 0 rgba(255, 255, 255, 0.8);
}

.thinking-dots {
  display: flex;
  gap: 5px;
  align-items: center;

  span {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--gradient-aurora);
    animation: bounce 1.4s infinite ease-in-out;
    box-shadow: 0 2px 4px rgba(17, 150, 127, 0.3);

    &:nth-child(1) { animation-delay: 0s; }
    &:nth-child(2) { animation-delay: 0.16s; }
    &:nth-child(3) { animation-delay: 0.32s; }
  }
}

.thinking-text {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-primary);
  letter-spacing: 0.01em;
}

.stage-bar {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin-top: 6px;
  padding: 4px 12px;
  background: var(--color-active-bg);
  border-radius: 12px;
}

.stage-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--gradient-aurora);
  animation: pulse 1.5s ease-in-out infinite;
}

.stage-text {
  font-size: 12px;
  font-weight: 500;
  color: var(--color-text-label);
}

@keyframes pulse {
  0%, 100% { opacity: 0.4; transform: scale(0.8); }
  50% { opacity: 1; transform: scale(1.2); }
}

@keyframes bounce {
  0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
  40% { transform: scale(1); opacity: 1; }
}

.quick-questions {
  padding: 0 24px 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.quick-label {
  font-size: 12px;
  font-weight: 700;
  color: var(--color-text-weak);
  letter-spacing: 0.05em;
}

.quick-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.quick-btn {
  padding: 8px 16px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-pill);
  background: var(--color-bg-light);
  color: var(--color-text-medium);
  font: inherit;
  font-size: 13px;
  cursor: pointer;
  transition: all var(--transition-fast);

  &:hover {
    border-color: var(--color-primary);
    color: var(--color-primary-dark);
    background: rgba(17, 150, 127, 0.04);
  }
}

.chat-input-area {
  padding: 16px 24px 20px;
  border-top: 1px solid var(--color-border-light);
  flex-shrink: 0;
}

.input-wrapper {
  display: flex;
  align-items: flex-end;
  gap: 10px;
  background: var(--color-bg-input);
  border: 1px solid var(--color-border);
  border-radius: 16px;
  padding: 8px 8px 8px 16px;
  transition: border-color var(--transition-fast), box-shadow var(--transition-fast);

  &:focus-within {
    border-color: var(--color-primary);
    box-shadow: 0 0 0 3px rgba(17, 150, 127, 0.15), var(--glow-primary);
  }

  textarea {
    flex: 1;
    border: none;
    outline: none;
    background: transparent;
    color: var(--color-text-strong);
    font: inherit;
    font-size: 14px;
    line-height: 1.5;
    resize: none;
    max-height: 120px;
    min-height: 24px;
    &::placeholder { color: var(--color-text-weak); }
  }
}

.send-btn {
  flex-shrink: 0;
  width: 36px; height: 36px;
  border: none;
  border-radius: 12px;
  background: var(--gradient-aurora);
  background-size: 200% 200%;
  animation: aurora-flow 4s ease infinite;
  color: #fff;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all var(--transition-bounce);

  &:hover:not(:disabled) {
    transform: scale(1.08);
    box-shadow: var(--glow-dreamy);
  }
  &:active:not(:disabled) { transform: scale(0.93); }
  &:disabled { opacity: 0.4; cursor: not-allowed; animation: none; }
}

.conversation-sidebar {
  width: 280px;
  min-width: 280px;
  display: flex;
  flex-direction: column;
  border-left: 1px solid var(--color-border-light);
  background: var(--color-bg-light);
}

.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  border-bottom: 1px solid var(--color-border-light);
  flex-shrink: 0;
}

.sidebar-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--color-text-strong);
}

.new-chat-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 5px 10px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-bg-base);
  color: var(--color-text-medium);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
  transition: all var(--transition-fast);

  &:hover { border-color: var(--color-primary); color: var(--color-primary-dark); }
}

.conversation-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.list-loading, .list-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px;
  color: var(--color-text-weak);
  font-size: 13px;
}

.loading-spinner {
  width: 24px; height: 24px;
  border: 3px solid var(--color-border-light);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }

.conv-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 10px;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--transition-fast);

  &:hover { background: var(--color-hover-bg); }
  &.active { background: var(--color-active-bg); }
}

.conv-icon {
  flex-shrink: 0;
  color: var(--color-text-weak);
}

.conv-info {
  flex: 1;
  min-width: 0;
}

.conv-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-strong);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.conv-time {
  font-size: 11px;
  color: var(--color-text-weak);
  margin-top: 1px;
}

.conv-delete {
  flex-shrink: 0;
  width: 24px;
  height: 24px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--color-text-weak);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: all var(--transition-fast);

  .conv-item:hover & { opacity: 1; }
  &:hover { background: rgba(220, 38, 38, 0.1); color: #dc2626; }
}

@media (max-width: 768px) {
  .tutor-body { flex-direction: column; }
  .conversation-sidebar { width: 100%; min-width: 100%; max-height: 30vh; border-left: none; border-top: 1px solid var(--color-border-light); }
}

.message { animation: fade-in-up 0.3s cubic-bezier(0.16, 1, 0.3, 1) both; }
.conv-item { transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1); }
.conv-item:hover { transform: translateX(4px); }

// ── 图片上传面板 ──
.image-uploader-panel {
  border-top: 1px solid var(--color-border-light);
  background: var(--color-bg-light);
  padding: 12px 16px;
  animation: slide-down 0.25s cubic-bezier(0.16, 1, 0.3, 1);
}
.uploader-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  font-size: 0.88rem;
  font-weight: 600;
  color: var(--color-text-strong);
}
.uploader-close {
  width: 24px; height: 24px;
  border: none; border-radius: 6px;
  background: var(--color-ghost-hover);
  color: var(--color-text-medium);
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  font-size: 0.75rem;
  transition: all var(--transition-fast);
  &:hover { background: var(--color-hover-bg); color: var(--color-text-strong); }
}
.uploader-footer {
  margin-top: 8px;
  text-align: center;
}
.uploader-hint {
  font-size: 0.72rem;
  color: var(--color-text-weak);
}

@keyframes slide-down {
  from { opacity: 0; transform: translateY(-8px); }
  to { opacity: 1; transform: translateY(0); }
}

// ── 已上传图片预览行 ──
.upload-preview-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 24px 4px;
  flex-wrap: wrap;
}
.upload-thumb {
  position: relative;
  width: 52px;
  height: 52px;
  border-radius: var(--radius-md);
  overflow: hidden;
  border: 2px solid var(--color-border);
  background: var(--color-bg-light);
  transition: all var(--transition-fast);
  &:hover { border-color: var(--color-primary); }
  img { width: 100%; height: 100%; object-fit: cover; }
}
.dicom-thumb-badge {
  width: 100%; height: 100%;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  background: linear-gradient(135deg, #1e293b, #334155);
  color: #94a3b8; font-size: 0.55rem; font-weight: 700;
  line-height: 1.2; text-align: center;
}
.upload-thumb-remove {
  position: absolute; top: 1px; right: 1px;
  width: 16px; height: 16px;
  border-radius: 50%; border: none;
  background: rgba(15, 23, 42, 0.7);
  color: #fff; font-size: 8px;
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  opacity: 0; transition: opacity var(--transition-fast);
  .upload-thumb:hover & { opacity: 1; }
}
.upload-count {
  font-size: 0.75rem;
  color: var(--color-text-weak);
  margin-left: 4px;
}

// ── 附件按钮 ──
.attach-btn {
  flex-shrink: 0;
  width: 36px; height: 36px;
  border: 1px solid var(--color-border);
  border-radius: 12px;
  background: var(--color-bg-base);
  color: var(--color-text-medium);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all var(--transition-fast);
  &:hover {
    border-color: var(--color-primary);
    color: var(--color-primary);
    background: var(--color-active-bg);
  }
  &.active {
    border-color: var(--color-primary);
    color: var(--color-primary);
    background: rgba(17, 150, 127, 0.08);
    box-shadow: 0 0 0 2px rgba(17, 150, 127, 0.12);
  }
}

// ── 消息中的图片 ──
.message-images {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}
.message-image-thumb {
  width: 72px;
  height: 72px;
  border-radius: var(--radius-md);
  overflow: hidden;
  border: 1px solid var(--color-border-light);
  cursor: pointer;
  transition: all var(--transition-fast);
  &:hover {
    border-color: var(--color-primary);
    box-shadow: var(--glow-primary);
    transform: scale(1.05);
  }
  img { width: 100%; height: 100%; object-fit: cover; }
}
.msg-dicom-badge {
  width: 100%; height: 100%;
  display: flex; align-items: center; justify-content: center;
  background: linear-gradient(135deg, #1e293b, #334155);
  color: #94a3b8; font-size: 0.64rem; font-weight: 700;
}
</style>
