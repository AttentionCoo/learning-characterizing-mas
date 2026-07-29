<script setup>
import { ref, onMounted, onUpdated, nextTick, computed, reactive } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import { getProfileAPI, getProfileConversationsAPI, getProfileConversationHistoryAPI, profileStreamAPI, updateProfileDimensionsAPI, deleteProfileConversationAPI } from '@/api/profile'
import AppAvatar from '@/components/AppAvatar.vue'
import ImageUploader from '@/components/ImageUploader.vue'
import ReasoningTrace from '@/components/ReasoningTrace.vue'
import { useUserStore } from '@/stores/user'
import { useReasoningTrace } from '@/composables/useReasoningTrace'
import { normalizeAiMarkdown } from '@/utils/aiMarkdown'

const userStore = useUserStore()

marked.setOptions({ gfm: true, breaks: true })

const MAX_CONVERSATIONS = 50

const profile = ref(null)
const profileLoading = ref(false)
const isProfileCollapsed = ref(false)
const chatMessages = ref([])
const draftMessage = ref('')
const isStreaming = ref(false)
const isThinking = ref(false)
const thinkingHint = ref('')
const chatContainerRef = ref(null)
const inputRef = ref(null)
const talkId = ref(null)
const hasLoadedHistory = ref(false)
const editingDim = ref(null)
const editForm = reactive({})
const saving = ref(false)
const { reasoningEntries, resetReasoningTrace, appendReasoningEvent } = useReasoningTrace()

const conversations = ref([])
const conversationsLoading = ref(false)

const uploadedImages = ref([])
const showImageUploader = ref(false)

const FILLER_PATTERNS = [
  /根据对话推断/g, /暂无信息/g, /信息不足/g, /待补充/g, /暂缺/g,
  /无法判断/g, /尚不明确/g, /未提供/g, /待确认/g, /未知/g,
]

function cleanText(text) {
  if (!text || typeof text !== 'string') return ''
  let cleaned = text.trim()
  for (const p of FILLER_PATTERNS) {
    cleaned = cleaned.replace(p, '')
  }
  cleaned = cleaned.replace(/[，。、；：]$/, '').trim()
  return cleaned
}

function cleanList(list) {
  if (!Array.isArray(list)) return []
  return list
    .map(t => (typeof t === 'string' ? t.trim() : String(t)))
    .filter(t => {
      if (!t) return false
      for (const p of FILLER_PATTERNS) {
        if (p.test(t)) return false
      }
      return true
    })
}

const dimensionLabels = {
  knowledgeBase: '知识基础',
  cognitiveStyle: '认知风格',
  learningGoal: '学习目标',
  errorPattern: '易错模式',
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

const levelLabels = {
  beginner: '入门', intermediate: '进阶', advanced: '高级',
  slow: '较慢', moderate: '适中', fast: '较快',
  none: '无', basic: '基础', moderate: '中等', extensive: '丰富',
  conceptual: '概念性', careful: '粗心性', procedural: '程序性',
  visual: '视觉型', auditory: '听觉型', kinesthetic: '动觉型', reading: '阅读型',
  motivated: '积极', anxious: '焦虑', confident: '自信', overwhelmed: '压力',
}

function levelLabel(val) {
  return levelLabels[val] || val || ''
}

const levelColors = {
  beginner: '#ef4444', intermediate: '#f59e0b', advanced: '#10b981',
  slow: '#f59e0b', moderate: '#3b82f6', fast: '#10b981',
  none: '#94a3b8', basic: '#f59e0b', extensive: '#10b981',
  conceptual: '#8b5cf6', careful: '#f59e0b', procedural: '#3b82f6',
  visual: '#3b82f6', auditory: '#8b5cf6', kinesthetic: '#f59e0b', reading: '#10b981',
  motivated: '#10b981', anxious: '#f59e0b', confident: '#3b82f6', overwhelmed: '#ef4444',
}

function levelColor(val) {
  return levelColors[val] || '#6b7280'
}

const hasProfile = computed(() => profile.value && Object.keys(profile.value.dimensions || {}).length > 0)

const dimensionList = computed(() => {
  if (!profile.value?.dimensions) return []
  return Object.entries(profile.value.dimensions).map(([key, value]) => {
    const dim = { key, label: dimensionLabels[key] || key, icon: dimensionIcons[key] || '📌' }
    if (value && typeof value === 'object') {
      dim.level = value.level || value.speed || value.type || value.status || value.errorType || ''
      dim.levelText = levelLabel(dim.level)
      dim.levelColor = levelColor(dim.level)
      dim.description = cleanText(value.description)
      dim.masteredTopics = cleanList(value.masteredTopics)
      dim.weakTopics = cleanList(value.weakTopics)
      dim.preferences = cleanList(value.preferences)
      dim.frequentErrors = cleanList(value.frequentErrors)
      dim.shortTerm = cleanText(value.shortTerm)
      dim.longTerm = cleanText(value.longTerm)
      dim.currentCourse = cleanText(value.currentCourse)
      dim.weeklyHours = value.weeklyHours || 0
    }
    return dim
  })
})

onMounted(async () => {
  await fetchProfile()
  await fetchConversations()
  if (conversations.value.length > 0) {
    const latest = conversations.value[0]
    if (latest?.talkId) {
      talkId.value = latest.talkId
      await loadConversationHistory(latest.talkId)
      return
    }
  }
  chatMessages.value.push(WELCOME_MESSAGE)
})

async function fetchConversations() {
  conversationsLoading.value = true
  try {
    const res = await getProfileConversationsAPI()
    let convList = res.data || []
    convList.sort((a, b) => new Date(b.updateTime || b.createTime || 0) - new Date(a.updateTime || a.createTime || 0))
    if (convList.length > MAX_CONVERSATIONS) {
      const toDelete = convList.slice(MAX_CONVERSATIONS)
      convList = convList.slice(0, MAX_CONVERSATIONS)
      toDelete.forEach(async (conv) => {
        try { await deleteProfileConversationAPI(conv.talkId) } catch {}
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
  talkId.value = conv.talkId
  await loadConversationHistory(conv.talkId)
}

function startNewConversation() {
  resetReasoningTrace()
  talkId.value = null
  chatMessages.value = [WELCOME_MESSAGE]
}

async function deleteConversation(conv, e) {
  e.stopPropagation()
  try {
    await deleteProfileConversationAPI(conv.talkId)
    conversations.value = conversations.value.filter(c => c.talkId !== conv.talkId)
    if (talkId.value === conv.talkId) {
      startNewConversation()
    }
  } catch {
    // ignore
  }
}

async function loadConversationHistory(selectedTalkId) {
  hasLoadedHistory.value = true
  try {
    const historyRes = await getProfileConversationHistoryAPI(selectedTalkId)
    const messages = historyRes.data
    if (messages && messages.length > 0) {
      chatMessages.value = messages.map((m) => ({
        role: m.role,
        content: m.content,
      }))
      return
    }
  } catch {
    // ignore
  }
  chatMessages.value = [WELCOME_MESSAGE]
}

const WELCOME_MESSAGE = {
  role: 'assistant',
  content: '你好！我是你的脑卒中学习画像构建助手 🎓\n\n请告诉我你的专业、年级、脑卒中学习目标，以及目前的学习情况，我会为你构建专属的学习画像。\n\n例如：\n- "我是临床医学大三学生，正在学神经病学，关注脑卒中方向"\n- "我的脑血管解剖比较薄弱，想重点补强"\n- "我偏好看视频和做脑卒中病例分析"',
}

async function fetchProfile() {
  profileLoading.value = true
  try {
    const res = await getProfileAPI()
    if (res.data) profile.value = res.data
  } catch {
  } finally {
    profileLoading.value = false
  }
}

function renderMarkdown(text) {
  if (!text) return ''
  return DOMPurify.sanitize(marked.parse(normalizeAiMarkdown(text)))
}

function startEdit(dim) {
  const raw = profile.value?.dimensions?.[dim.key] || {}
  editingDim.value = dim.key
  editForm.description = raw.description || ''
  editForm.level = raw.level || raw.speed || raw.type || raw.status || raw.errorType || ''
  editForm.masteredTopics = (raw.masteredTopics || []).join('、')
  editForm.weakTopics = (raw.weakTopics || []).join('、')
  editForm.preferences = (raw.preferences || []).join('、')
  editForm.frequentErrors = (raw.frequentErrors || []).join('、')
  editForm.shortTerm = raw.shortTerm || ''
  editForm.longTerm = raw.longTerm || ''
  editForm.currentCourse = raw.currentCourse || ''
  editForm.weeklyHours = raw.weeklyHours || 0
}

function cancelEdit() {
  editingDim.value = null
}

async function saveEdit(dim) {
  saving.value = true
  try {
    const raw = profile.value?.dimensions?.[dim.key] || {}
    const updated = { ...raw }
    updated.description = editForm.description.trim()
    if (raw.level !== undefined) updated.level = editForm.level
    if (raw.speed !== undefined) updated.speed = editForm.level
    if (raw.type !== undefined) updated.type = editForm.level
    if (raw.status !== undefined) updated.status = editForm.level
    if (raw.errorType !== undefined) updated.errorType = editForm.level
    if (raw.masteredTopics !== undefined) updated.masteredTopics = editForm.masteredTopics ? editForm.masteredTopics.split(/[、,，]/).map(s => s.trim()).filter(Boolean) : []
    if (raw.weakTopics !== undefined) updated.weakTopics = editForm.weakTopics ? editForm.weakTopics.split(/[、,，]/).map(s => s.trim()).filter(Boolean) : []
    if (raw.preferences !== undefined) updated.preferences = editForm.preferences ? editForm.preferences.split(/[、,，]/).map(s => s.trim()).filter(Boolean) : []
    if (raw.frequentErrors !== undefined) updated.frequentErrors = editForm.frequentErrors ? editForm.frequentErrors.split(/[、,，]/).map(s => s.trim()).filter(Boolean) : []
    if (raw.shortTerm !== undefined) updated.shortTerm = editForm.shortTerm.trim()
    if (raw.longTerm !== undefined) updated.longTerm = editForm.longTerm.trim()
    if (raw.currentCourse !== undefined) updated.currentCourse = editForm.currentCourse.trim()
    if (raw.weeklyHours !== undefined) updated.weeklyHours = Number(editForm.weeklyHours) || 0

    const allDimensions = { ...profile.value.dimensions, [dim.key]: updated }
    await updateProfileDimensionsAPI(allDimensions)
    await fetchProfile()
    editingDim.value = null
  } catch (e) {
    console.error('保存画像维度失败', e)
  } finally {
    saving.value = false
  }
}

async function handleSend() {
  const message = draftMessage.value.trim()
  if (!message || isStreaming.value) return

  draftMessage.value = ''
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
  thinkingHint.value = '正在分析你的学习特征...'
  resetReasoningTrace()

  await nextTick()
  scrollToBottom()

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
      scrollToBottom()
      timerId = setTimeout(tick, delay)
    }
    timerId = setTimeout(tick, 0)
  }

  try {
    const result = await profileStreamAPI(
      { talkId: talkId.value, message, images: currentImages },
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
        appendReasoningEvent(thinking)
      },
    )

    if (timerId !== null) { clearTimeout(timerId); timerId = null }
    const content = result.data?.content || displayText
    chatMessages.value[aiIndex] = { role: 'assistant', content }
    if (result.data?.talkId) talkId.value = result.data.talkId

    if (result.data?.profileDimensions && Object.keys(result.data.profileDimensions).length > 0) {
      try {
        console.log('🎯 自动保存学习画像维度:', result.data.profileDimensions)
        await updateProfileDimensionsAPI(result.data.profileDimensions)
        console.log('✅ 画像维度已自动保存到数据库')
      } catch (saveError) {
        console.error('❌ 自动保存画像维度失败:', saveError)
      }
    }

    await fetchProfile()
    await fetchConversations()
    setTimeout(async () => {
      await fetchProfile()
      await fetchConversations()
    }, 5000)
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

/** 判断 Base64 data URL 是否为 DICOM 文件 */
function isDICOMDataUrl(dataUrl) {
  if (!dataUrl || typeof dataUrl !== 'string') return false
  return dataUrl.includes('application/dicom') ||
         dataUrl.includes('application/octet-stream') ||
         /\.dcm/i.test(dataUrl)
}
</script>

<template>
  <div class="profile-page">
    <div class="page-header">
      <div class="header-content">
        <h1>学习画像</h1>
        <p>通过自然语言对话，自动构建你的脑卒中专属学习画像</p>
      </div>
      <div class="header-badge">核心功能1 · 必选</div>
    </div>

    <div class="profile-body">
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
            :class="{ active: talkId === conv.talkId }"
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

      <div class="chat-panel">
        <div class="chat-messages" ref="chatContainerRef">
          <div
            v-for="(msg, idx) in chatMessages"
            :key="idx"
            class="chat-message"
            :class="[msg.role, { error: msg.error }]"
          >
            <div class="message-avatar">
              <span v-if="msg.role === 'assistant'" class="avatar-ai">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
                  <rect x="4" y="6" width="16" height="12" rx="4" fill="currentColor" opacity="0.9"/>
                  <circle cx="9.5" cy="12" r="1.5" fill="#fff"/>
                  <circle cx="14.5" cy="12" r="1.5" fill="#fff"/>
                  <path d="M10 15.5c1 .8 3 .8 4 0" stroke="#fff" stroke-width="1" stroke-linecap="round"/>
                  <line x1="8" y1="6" x2="6" y2="3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                  <line x1="16" y1="6" x2="18" y2="3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                  <circle cx="6" cy="2.5" r="1.2" fill="currentColor"/>
                  <circle cx="18" cy="2.5" r="1.2" fill="currentColor"/>
                </svg>
              </span>
              <AppAvatar v-else :src="userStore.image" :name="userStore.name" :size="40" />
            </div>
            <div class="message-body">
              <div v-if="msg.role === 'assistant' && idx === chatMessages.length - 1 && isThinking && !msg.content && !reasoningEntries.length" class="thinking-indicator">
                <div class="thinking-dots">
                  <span></span><span></span><span></span>
                </div>
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
            </div>
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
              placeholder="告诉我你的学习情况，如专业、年级、脑卒中学习目标..."
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

      <div class="profile-panel" :class="{ collapsed: isProfileCollapsed }">
        <div class="panel-title">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
            <circle cx="12" cy="7" r="4"/>
          </svg>
          <span v-if="!isProfileCollapsed">我的学习画像</span>
          <span v-if="!isProfileCollapsed && hasProfile" class="edit-hint">点击卡片可编辑</span>
          <button
            class="profile-collapse-btn"
            :title="isProfileCollapsed ? '展开学习画像' : '收起学习画像'"
            :aria-label="isProfileCollapsed ? '展开学习画像' : '收起学习画像'"
            @click="isProfileCollapsed = !isProfileCollapsed"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polyline :points="isProfileCollapsed ? '9 18 15 12 9 6' : '15 18 9 12 15 6'"/>
            </svg>
          </button>
        </div>

        <template v-if="!isProfileCollapsed">
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
          <div
            v-for="dim in dimensionList"
            :key="dim.key"
            class="dimension-card"
            :class="{ editing: editingDim === dim.key }"
            @click="editingDim !== dim.key && startEdit(dim)"
          >
            <div class="dim-header">
              <span class="dim-icon">{{ dim.icon }}</span>
              <span class="dim-label">{{ dim.label }}</span>
              <span v-if="dim.levelText" class="dim-level-badge" :style="{ background: dim.levelColor + '18', color: dim.levelColor }">
                {{ dim.levelText }}
              </span>
              <button class="dim-edit-btn" @click.stop="startEdit(dim)" title="编辑">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                  <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                </svg>
              </button>
            </div>

            <template v-if="editingDim === dim.key">
              <div class="edit-form">
                <div class="edit-row">
                  <label>描述</label>
                  <textarea v-model="editForm.description" rows="2" placeholder="输入描述..."></textarea>
                </div>
                <div v-if="dim.level" class="edit-row">
                  <label>等级</label>
                  <input v-model="editForm.level" placeholder="如 入门/进阶/高级" />
                </div>
                <div v-if="dim.masteredTopics !== undefined" class="edit-row">
                  <label>已掌握</label>
                  <input v-model="editForm.masteredTopics" placeholder="用顿号分隔，如：脑血管解剖、脑卒中诊疗" />
                </div>
                <div v-if="dim.weakTopics !== undefined" class="edit-row">
                  <label>待加强</label>
                  <input v-model="editForm.weakTopics" placeholder="用顿号分隔" />
                </div>
                <div v-if="dim.preferences !== undefined" class="edit-row">
                  <label>偏好</label>
                  <input v-model="editForm.preferences" placeholder="用顿号分隔" />
                </div>
                <div v-if="dim.frequentErrors !== undefined" class="edit-row">
                  <label>高频错误</label>
                  <input v-model="editForm.frequentErrors" placeholder="用顿号分隔" />
                </div>
                <div v-if="dim.shortTerm !== undefined" class="edit-row">
                  <label>短期目标</label>
                  <input v-model="editForm.shortTerm" placeholder="短期目标" />
                </div>
                <div v-if="dim.longTerm !== undefined" class="edit-row">
                  <label>长期目标</label>
                  <input v-model="editForm.longTerm" placeholder="长期目标" />
                </div>
                <div v-if="dim.currentCourse !== undefined" class="edit-row">
                  <label>当前课程</label>
                  <input v-model="editForm.currentCourse" placeholder="当前课程" />
                </div>
                <div v-if="dim.weeklyHours" class="edit-row">
                  <label>每周学时</label>
                  <input v-model.number="editForm.weeklyHours" type="number" min="0" />
                </div>
                <div class="edit-actions">
                  <button class="btn-cancel" @click.stop="cancelEdit">取消</button>
                  <button class="btn-save" :disabled="saving" @click.stop="saveEdit(dim)">
                    {{ saving ? '保存中...' : '保存' }}
                  </button>
                </div>
              </div>
            </template>

            <template v-else>
              <div v-if="dim.description" class="dim-description">{{ dim.description }}</div>

              <div v-if="dim.key === 'learningGoal'" class="goal-section">
                <div v-if="dim.shortTerm" class="goal-item">
                  <span class="goal-dot short"></span>
                  <span class="goal-label">短期</span>
                  <span class="goal-text">{{ dim.shortTerm }}</span>
                </div>
                <div v-if="dim.longTerm" class="goal-item">
                  <span class="goal-dot long"></span>
                  <span class="goal-label">长期</span>
                  <span class="goal-text">{{ dim.longTerm }}</span>
                </div>
                <div v-if="dim.currentCourse" class="goal-item">
                  <span class="goal-dot course"></span>
                  <span class="goal-label">课程</span>
                  <span class="goal-text">{{ dim.currentCourse }}</span>
                </div>
              </div>

              <div v-if="dim.key === 'learningPace' && dim.weeklyHours" class="pace-section">
                <div class="pace-bar-wrap">
                  <div class="pace-bar" :style="{ width: Math.min(dim.weeklyHours / 40 * 100, 100) + '%', background: dim.levelColor }"></div>
                </div>
                <span class="pace-hours">{{ dim.weeklyHours }} 小时/周</span>
              </div>

              <div v-if="dim.masteredTopics?.length" class="dim-tags">
                <span class="tag-label success">已掌握</span>
                <span v-for="t in dim.masteredTopics" :key="t" class="tag success">{{ t }}</span>
              </div>
              <div v-if="dim.weakTopics?.length" class="dim-tags">
                <span class="tag-label warn">待加强</span>
                <span v-for="t in dim.weakTopics" :key="t" class="tag warn">{{ t }}</span>
              </div>
              <div v-if="dim.preferences?.length" class="dim-tags">
                <span class="tag-label info">偏好</span>
                <span v-for="t in dim.preferences" :key="t" class="tag info">{{ t }}</span>
              </div>
              <div v-if="dim.frequentErrors?.length" class="dim-tags">
                <span class="tag-label danger">易错</span>
                <span v-for="t in dim.frequentErrors" :key="t" class="tag danger">{{ t }}</span>
              </div>
            </template>
          </div>

          <div class="profile-meta">
            <span>更新时间：{{ profile.updateTime || '刚刚' }}</span>
          </div>
          </div>
        </template>
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

.conversation-sidebar {
  width: 260px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  border-right: 1px solid var(--color-border-light);
  background: var(--color-bg-base);
}

.sidebar-header {
  padding: 16px;
  border-bottom: 1px solid var(--color-border-light);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
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
  padding: 6px 12px;
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--color-text-medium);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;

  &:hover {
    background: var(--color-hover-bg);
    border-color: var(--color-primary);
    color: var(--color-primary);
  }
}

.conversation-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;

  &::-webkit-scrollbar {
    width: 4px;
  }

  &::-webkit-scrollbar-thumb {
    background: var(--color-border-medium);
    border-radius: 2px;
  }
}

.list-loading,
.list-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 120px;
  color: var(--color-text-light);
  font-size: 13px;
}

.loading-spinner {
  width: 24px;
  height: 24px;
  border: 3px solid var(--color-border-light);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.conv-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  margin-bottom: 4px;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all 0.15s ease;
  position: relative;

  &:hover {
    background: var(--color-ghost-hover);

    .conv-delete {
      opacity: 1;
    }
  }

  &.active {
    background: rgba(17, 150, 127, 0.08);
    box-shadow: inset 3px 0 0 var(--color-primary);

    .conv-title {
      color: var(--color-primary-dark);
      font-weight: 600;
    }
  }
}

.conv-icon {
  flex-shrink: 0;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-sm);
  background: var(--color-secondary-bg);
  color: var(--color-text-medium);
}

.conv-info {
  flex: 1;
  min-width: 0;
  overflow: hidden;
}

.conv-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-strong);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.4;
}

.conv-time {
  font-size: 11px;
  color: var(--color-text-light);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.3;
}

.conv-delete {
  opacity: 0;
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: var(--color-text-light);
  cursor: pointer;
  transition: all 0.15s;

  &:hover {
    background: rgba(220, 38, 38, 0.1);
    color: #dc2626;
  }
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
  background: var(--gradient-aurora);
  border-radius: 50%;
  color: #fff;
  box-shadow: 0 2px 8px rgba(17, 150, 127, 0.3);
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
  &:disabled {
    opacity: 0.4;
    cursor: not-allowed;
    animation: none;
  }
}

.profile-panel {
  width: 400px;
  min-width: 400px;
  display: flex;
  flex-direction: column;
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
  overflow-y: auto;
  transition: width var(--transition-fast), min-width var(--transition-fast), max-height var(--transition-fast);

  &.collapsed {
    width: 56px;
    min-width: 56px;
    overflow: hidden;

    .panel-title {
      flex-direction: column;
      padding: 14px 8px;
    }
  }
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
  position: sticky;
  top: 0;
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur));
  z-index: 2;
}

.edit-hint {
  margin-left: auto;
  font-size: 11px;
  font-weight: 500;
  color: var(--color-text-weak);
  background: rgba(17, 150, 127, 0.08);
  padding: 2px 10px;
  border-radius: var(--radius-pill);
}

.profile-collapse-btn {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--color-text-medium);
  cursor: pointer;
  transition: all var(--transition-fast);

  &:hover {
    border-color: var(--color-primary);
    background: var(--color-hover-bg);
    color: var(--color-primary);
  }

  .collapsed & {
    margin-left: 0;
  }
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
  gap: 10px;
}

.dimension-card {
  padding: 14px 16px;
  background: var(--color-bg-base);
  border: 1px solid var(--color-border-light);
  border-radius: 12px;
  transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
  cursor: pointer;
  position: relative;
  overflow: hidden;

  &::before {
    content: '';
    position: absolute;
    left: 0;
    top: 0;
    bottom: 0;
    width: 3px;
    background: var(--color-primary);
    opacity: 0;
    transition: opacity 0.2s;
  }

  &:hover {
    border-color: rgba(17, 150, 127, 0.3);
    box-shadow: 0 2px 12px rgba(17, 150, 127, 0.08);

    &::before { opacity: 1; }
  }

  &.editing {
    border-color: var(--color-primary);
    box-shadow: 0 0 0 3px rgba(17, 150, 127, 0.12);
    cursor: default;

    &::before { opacity: 1; }
  }
}

.dim-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
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

.dim-level-badge {
  margin-left: 4px;
  padding: 2px 10px;
  border-radius: var(--radius-pill);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.02em;
}

.dim-edit-btn {
  margin-left: auto;
  width: 28px;
  height: 28px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--color-text-weak);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
  opacity: 0;

  .dimension-card:hover & { opacity: 1; }

  &:hover {
    background: rgba(17, 150, 127, 0.1);
    color: var(--color-primary);
  }
}

.dim-description {
  font-size: 13px;
  color: var(--color-text-medium);
  line-height: 1.55;
  margin-bottom: 8px;
}

.goal-section {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 4px;
}

.goal-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.goal-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;

  &.short { background: #3b82f6; }
  &.long { background: #10b981; }
  &.course { background: #f59e0b; }
}

.goal-label {
  font-size: 11px;
  font-weight: 700;
  color: var(--color-text-weak);
  min-width: 28px;
}

.goal-text {
  color: var(--color-text-medium);
}

.pace-section {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 4px;
}

.pace-bar-wrap {
  flex: 1;
  height: 6px;
  background: var(--color-border-light);
  border-radius: 3px;
  overflow: hidden;
}

.pace-bar {
  height: 100%;
  border-radius: 3px;
  transition: width 0.5s cubic-bezier(0.16, 1, 0.3, 1);
}

.pace-hours {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text-medium);
  white-space: nowrap;
}

.dim-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 6px;
}

.tag-label {
  font-size: 11px;
  font-weight: 700;
  margin-right: 2px;
  line-height: 22px;

  &.success { color: #10b981; }
  &.warn { color: #f59e0b; }
  &.info { color: #3b82f6; }
  &.danger { color: #ef4444; }
}

.tag {
  padding: 2px 10px;
  border-radius: var(--radius-pill);
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
  line-height: 20px;

  &.success { background: rgba(16, 185, 129, 0.1); color: #059669; }
  &.warn { background: rgba(245, 158, 11, 0.1); color: #b45309; }
  &.info { background: rgba(59, 130, 246, 0.1); color: #2563eb; }
  &.danger { background: rgba(239, 68, 68, 0.1); color: #dc2626; }
}

.edit-form {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 4px;
}

.edit-row {
  display: flex;
  flex-direction: column;
  gap: 4px;

  label {
    font-size: 11px;
    font-weight: 700;
    color: var(--color-text-weak);
    letter-spacing: 0.04em;
  }

  input, textarea {
    width: 100%;
    padding: 8px 12px;
    border: 1px solid var(--color-border);
    border-radius: 8px;
    background: var(--color-bg-input);
    color: var(--color-text-strong);
    font: inherit;
    font-size: 13px;
    outline: none;
    transition: border-color 0.2s;

    &:focus {
      border-color: var(--color-primary);
      box-shadow: 0 0 0 2px rgba(17, 150, 127, 0.12);
    }

    &::placeholder { color: var(--color-text-weak); }
  }

  textarea {
    resize: vertical;
    min-height: 48px;
    line-height: 1.5;
  }
}

.edit-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 4px;
}

.btn-cancel, .btn-save {
  padding: 6px 18px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  border: none;
  transition: all 0.2s;
}

.btn-cancel {
  background: var(--color-border-light);
  color: var(--color-text-medium);

  &:hover { background: var(--color-border); }
}

.btn-save {
  background: var(--gradient-aurora);
  color: #fff;

  &:hover:not(:disabled) { opacity: 0.85; }
  &:disabled { opacity: 0.5; cursor: not-allowed; }
}

.profile-meta {
  padding-top: 8px;
  font-size: 11px;
  color: var(--color-text-weak);
  text-align: center;
}

@media (max-width: 1024px) {
  .profile-panel {
    width: 340px;
    min-width: 340px;
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

    &.collapsed {
      width: 100%;
      min-width: 100%;
      max-height: 52px;

      .panel-title {
        flex-direction: row;
        padding: 11px 16px;
      }
    }
  }
}

.dimension-card {
  animation: fade-in-up 0.4s cubic-bezier(0.16, 1, 0.3, 1) both;
}

@keyframes fade-in-up {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

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
