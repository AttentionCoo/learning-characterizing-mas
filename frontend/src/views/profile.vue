<script setup>
import { ref, onMounted, nextTick, computed } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import { getProfileAPI, profileStreamAPI } from '@/api/profile'

marked.setOptions({ gfm: true, breaks: true })

const profile = ref(null)
const profileLoading = ref(false)
const chatMessages = ref([])
const draftMessage = ref('')
const isStreaming = ref(false)
const isThinking = ref(false)
const thinkingHint = ref('')
const chatContainerRef = ref(null)
const inputRef = ref(null)
const talkId = ref(null)

const dimensionLabels = {
  knowledgeBase: '知识基础',
  cognitiveStyle: '认知风格',
  learningGoal: '学习目标',
  errorPattern: '易错点',
  learningPace: '学习节奏',
  resourcePreference: '资源偏好',
  clinicalExperience: '临床经验',
  emotionState: '情绪状态',
}

const dimensionIcons = {
  knowledgeBase: '📚',
  cognitiveStyle: '🧠',
  learningGoal: '🎯',
  errorPattern: '⚠️',
  learningPace: '⏱️',
  resourcePreference: '📋',
  clinicalExperience: '🏥',
  emotionState: '💪',
}

const hasProfile = computed(() => profile.value && Object.keys(profile.value.dimensions || {}).length > 0)

const dimensionList = computed(() => {
  if (!profile.value?.dimensions) return []
  return Object.entries(profile.value.dimensions).map(([key, value]) => ({
    key,
    label: dimensionLabels[key] || key,
    icon: dimensionIcons[key] || '📌',
    ...value,
  }))
})

onMounted(async () => {
  await fetchProfile()
  chatMessages.value.push({
    role: 'assistant',
    content: '你好！我是你的学习画像构建助手 🎓\n\n请告诉我你的专业、年级、学习目标，以及目前的学习情况，我会为你构建专属的学习画像。\n\n例如：\n- "我是临床医学大三学生，正在学神经病学"\n- "我的药理学比较薄弱，想重点补强"\n- "我偏好看视频和做病例分析"',
  })
})

async function fetchProfile() {
  profileLoading.value = true
  try {
    const res = await getProfileAPI()
    if (res.data) profile.value = res.data
  } catch {
    // profile may not exist yet
  } finally {
    profileLoading.value = false
  }
}

function renderMarkdown(text) {
  if (!text) return ''
  return DOMPurify.sanitize(marked.parse(text))
}

async function handleSend() {
  const message = draftMessage.value.trim()
  if (!message || isStreaming.value) return

  draftMessage.value = ''
  chatMessages.value.push({ role: 'user', content: message })
  chatMessages.value.push({ role: 'assistant', content: '' })
  const aiIndex = chatMessages.value.length - 1

  isStreaming.value = true
  isThinking.value = true
  thinkingHint.value = '正在分析你的学习特征...'

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
      timerId = setTimeout(tick, delay)
    }
    timerId = setTimeout(tick, 0)
  }

  try {
    const result = await profileStreamAPI(
      { talkId: talkId.value, message },
      (chunk) => {
        if (isThinking.value) {
          isThinking.value = false
          thinkingHint.value = ''
        }
        charBuffer.push(...Array.from(chunk))
        startTypewriter()
      },
      (thinking) => {
        thinkingHint.value = thinking.title || 'AI 思考中...'
      },
    )

    if (timerId !== null) { clearTimeout(timerId); timerId = null }
    const content = result.data?.content || displayText
    chatMessages.value[aiIndex] = { role: 'assistant', content }
    if (result.data?.talkId) talkId.value = result.data.talkId

    await fetchProfile()
  } catch (error) {
    console.error('画像对话失败', error)
    chatMessages.value.splice(aiIndex, 1)
    chatMessages.value[aiIndex - 1] && (chatMessages.value[aiIndex - 1].error = true)
  } finally {
    isStreaming.value = false
    isThinking.value = false
    thinkingHint.value = ''
  }

  await nextTick()
  scrollToBottom()
}

function scrollToBottom() {
  if (chatContainerRef.value) {
    chatContainerRef.value.scrollTop = chatContainerRef.value.scrollHeight
  }
}

function handleKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    handleSend()
  }
}
</script>

<template>
  <div class="profile-page">
    <div class="page-header">
      <div class="header-content">
        <h1>学习画像</h1>
        <p>通过自然语言对话，自动构建你的专属学习画像</p>
      </div>
      <div class="header-badge">核心功能1 · 必选</div>
    </div>

    <div class="profile-body">
      <div class="chat-panel">
        <div class="chat-messages" ref="chatContainerRef">
          <div
            v-for="(msg, idx) in chatMessages"
            :key="idx"
            class="chat-message"
            :class="[msg.role, { error: msg.error }]"
          >
            <div class="message-avatar">
              <span v-if="msg.role === 'assistant'" class="avatar-ai">🤖</span>
              <span v-else class="avatar-user">{{ '我' }}</span>
            </div>
            <div class="message-body">
              <div v-if="msg.role === 'assistant'" class="message-content markdown-body" v-html="renderMarkdown(msg.content)"></div>
              <div v-else class="message-content">{{ msg.content }}</div>
            </div>
          </div>
          <div v-if="isThinking" class="chat-message assistant">
            <div class="message-avatar"><span class="avatar-ai">🤖</span></div>
            <div class="message-body">
              <div class="thinking-indicator">
                <div class="thinking-dots">
                  <span></span><span></span><span></span>
                </div>
                <span class="thinking-text">{{ thinkingHint }}</span>
              </div>
            </div>
          </div>
        </div>

        <div class="chat-input-area">
          <div class="input-wrapper">
            <textarea
              ref="inputRef"
              v-model="draftMessage"
              placeholder="告诉我你的学习情况，如专业、年级、学习目标..."
              rows="1"
              :disabled="isStreaming"
              @keydown="handleKeydown"
              @input="($event.target.style.height = 'auto'), ($event.target.style.height = $event.target.scrollHeight + 'px')"
            ></textarea>
            <button class="send-btn" :disabled="!draftMessage.trim() || isStreaming" @click="handleSend">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <line x1="22" y1="2" x2="11" y2="13"/>
                <polygon points="22 2 15 22 11 13 2 9 22 2"/>
              </svg>
            </button>
          </div>
        </div>
      </div>

      <div class="profile-panel">
        <div class="panel-title">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
            <circle cx="12" cy="7" r="4"/>
          </svg>
          <span>我的学习画像</span>
        </div>

        <div v-if="profileLoading" class="profile-loading">
          <div class="loading-spinner"></div>
          <span>加载画像中...</span>
        </div>

        <div v-else-if="!hasProfile" class="profile-empty">
          <div class="empty-icon">🎯</div>
          <div class="empty-title">尚未构建画像</div>
          <div class="empty-desc">请在左侧对话中描述你的学习情况，系统将自动为你构建学习画像</div>
        </div>

        <div v-else class="profile-dimensions">
          <div v-for="dim in dimensionList" :key="dim.key" class="dimension-card">
            <div class="dim-header">
              <span class="dim-icon">{{ dim.icon }}</span>
              <span class="dim-label">{{ dim.label }}</span>
              <span v-if="dim.level" class="dim-level" :class="dim.level">{{ dim.level }}</span>
            </div>
            <div class="dim-description">{{ dim.description }}</div>
            <div v-if="dim.masteredTopics?.length" class="dim-tags mastered">
              <span class="tag-label">已掌握</span>
              <span v-for="t in dim.masteredTopics" :key="t" class="tag">{{ t }}</span>
            </div>
            <div v-if="dim.weakTopics?.length" class="dim-tags weak">
              <span class="tag-label">待加强</span>
              <span v-for="t in dim.weakTopics" :key="t" class="tag">{{ t }}</span>
            </div>
            <div v-if="dim.preferences?.length" class="dim-tags">
              <span v-for="t in dim.preferences" :key="t" class="tag accent">{{ t }}</span>
            </div>
            <div v-if="dim.frequentErrors?.length" class="dim-tags weak">
              <span class="tag-label">高频错误</span>
              <span v-for="t in dim.frequentErrors" :key="t" class="tag error">{{ t }}</span>
            </div>
          </div>

          <div class="profile-meta">
            <span>更新时间：{{ profile.updateTime || '刚刚' }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.profile-page {
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
  background: var(--color-bg-base);
}

.header-content {
  h1 {
    margin: 0;
    font-size: 1.5rem;
    font-weight: 800;
    color: var(--color-text-strong);
    letter-spacing: -0.02em;
  }
  p {
    margin: 4px 0 0;
    font-size: 13px;
    color: var(--color-text-medium);
  }
}

.header-badge {
  padding: 5px 14px;
  border-radius: var(--radius-pill);
  font-size: 12px;
  font-weight: 700;
  background: rgba(17, 150, 127, 0.1);
  color: var(--color-primary-dark);
  white-space: nowrap;
}

.profile-body {
  flex: 1;
  display: flex;
  min-height: 0;
  overflow: hidden;
}

.chat-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  border-right: 1px solid var(--color-border-light);
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

    .message-body {
      align-items: flex-end;
    }

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

  &.error .message-content {
    border-color: rgba(220, 38, 38, 0.3);
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
  font-size: 16px;
}

.avatar-ai {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #11967f 0%, #0f7666 100%);
  border-radius: 50%;
}

.avatar-user {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-secondary-bg);
  border-radius: 50%;
  font-size: 13px;
  font-weight: 700;
  color: var(--color-text-strong);
}

.message-body {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

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
  gap: 10px;
  padding: 12px 16px;
  background: var(--color-message-bg);
  border: 1px solid var(--color-border-light);
  border-radius: 16px 16px 16px 4px;
}

.thinking-dots {
  display: flex;
  gap: 4px;

  span {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--color-primary);
    animation: bounce 1.4s infinite ease-in-out;

    &:nth-child(1) { animation-delay: 0s; }
    &:nth-child(2) { animation-delay: 0.2s; }
    &:nth-child(3) { animation-delay: 0.4s; }
  }
}

.thinking-text {
  font-size: 13px;
  color: var(--color-text-medium);
}

@keyframes bounce {
  0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
  40% { transform: scale(1); opacity: 1; }
}

.chat-input-area {
  padding: 16px 24px 20px;
  border-top: 1px solid var(--color-border-light);
  flex-shrink: 0;
  background: var(--color-bg-base);
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
    box-shadow: 0 0 0 3px rgba(17, 150, 127, 0.12);
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

    &::placeholder {
      color: var(--color-text-weak);
    }
  }
}

.send-btn {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  border: none;
  border-radius: 12px;
  background: var(--color-primary-gradient);
  color: #fff;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all var(--transition-fast);

  &:hover:not(:disabled) {
    opacity: 0.85;
    transform: scale(1.05);
  }

  &:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }
}

.profile-panel {
  width: 380px;
  min-width: 380px;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  background: var(--color-bg-light);
}

.panel-title {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 16px 20px;
  font-size: 15px;
  font-weight: 700;
  color: var(--color-text-strong);
  border-bottom: 1px solid var(--color-border-light);
  flex-shrink: 0;
}

.profile-loading,
.profile-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 40px 20px;
  color: var(--color-text-weak);
}

.loading-spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--color-border-light);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.empty-icon {
  font-size: 3rem;
  line-height: 1;
}

.empty-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--color-text-medium);
}

.empty-desc {
  font-size: 13px;
  text-align: center;
  line-height: 1.6;
  max-width: 260px;
}

.profile-dimensions {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.dimension-card {
  padding: 14px 16px;
  background: var(--color-bg-base);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-lg);
  transition: all var(--transition-fast);

  &:hover {
    border-color: var(--color-border);
    box-shadow: 0 2px 12px rgba(17, 150, 127, 0.06);
  }
}

.dim-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.dim-icon {
  font-size: 18px;
  line-height: 1;
}

.dim-label {
  font-size: 14px;
  font-weight: 700;
  color: var(--color-text-strong);
}

.dim-level {
  margin-left: auto;
  padding: 2px 8px;
  border-radius: var(--radius-pill);
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;

  &.beginner { background: rgba(239, 68, 68, 0.1); color: #dc2626; }
  &.intermediate { background: rgba(245, 158, 11, 0.1); color: #b45309; }
  &.advanced { background: rgba(17, 150, 127, 0.1); color: #0f7666; }
  &.good { background: rgba(59, 130, 246, 0.1); color: #3b82f6; }
  &.needs_improvement { background: rgba(239, 68, 68, 0.1); color: #dc2626; }
  &.slow, &.moderate, &.fast { background: rgba(17, 150, 127, 0.1); color: #0f7666; }
}

.dim-description {
  font-size: 13px;
  color: var(--color-text-medium);
  line-height: 1.5;
  margin-bottom: 8px;
}

.dim-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 6px;

  &.mastered .tag { background: rgba(17, 150, 127, 0.1); color: var(--color-primary-dark); }
  &.weak .tag { background: rgba(245, 158, 11, 0.1); color: #b45309; }
  &.weak .tag.error { background: rgba(239, 68, 68, 0.1); color: #dc2626; }
}

.tag-label {
  font-size: 11px;
  font-weight: 700;
  color: var(--color-text-weak);
  margin-right: 2px;
  line-height: 22px;
}

.tag {
  padding: 2px 8px;
  border-radius: var(--radius-pill);
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
  line-height: 20px;

  &.accent {
    background: rgba(59, 130, 246, 0.1);
    color: #3b82f6;
  }
}

.profile-meta {
  padding-top: 8px;
  font-size: 11px;
  color: var(--color-text-weak);
  text-align: center;
}

@media (max-width: 1024px) {
  .profile-panel {
    width: 320px;
    min-width: 320px;
  }
}

@media (max-width: 768px) {
  .profile-body {
    flex-direction: column;
  }
  .profile-panel {
    width: 100%;
    min-width: 100%;
    max-height: 40vh;
    border-top: 1px solid var(--color-border-light);
  }
}
</style>
