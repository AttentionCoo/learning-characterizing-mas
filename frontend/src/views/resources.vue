<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import { getResourcesAPI, getResourceDetailAPI, resourceStreamAPI } from '@/api/resources'

marked.setOptions({ gfm: true, breaks: true })

const resourceTypes = [
  { value: 'document', label: '课程讲解文档', icon: '📄', color: '#3b82f6' },
  { value: 'mindmap', label: '知识体系思维导图', icon: '🧠', color: '#8b5cf6' },
  { value: 'quiz', label: '练习题目', icon: '✏️', color: '#f59e0b' },
  { value: 'reading', label: '临床指南与文献', icon: '📖', color: '#10b981' },
  { value: 'video_script', label: '教学视频脚本', icon: '🎬', color: '#ef4444' },
  { value: 'case_study', label: '脑卒中临床案例', icon: '🏥', color: '#f97316' },
  { value: 'ppt', label: '课程PPT', icon: '📊', color: '#6366f1' },
  { value: 'plan', label: '资源设计方案', icon: '📋', color: '#14b8a6' },
]

const selectedTypes = ref([])
const courseName = ref('神经病学')
const knowledgePoints = ref('')
const difficulty = ref('intermediate')
const customMessage = ref('')
const isGenerating = ref(false)
const isThinking = ref(false)
const thinkingHint = ref('')
const generatedContent = ref('')
const talkId = ref(null)

const resources = ref([])
const resourceTotal = ref(0)
const resourcePage = ref(1)
const resourcesLoading = ref(false)
const selectedResource = ref(null)
const resourceDetail = ref(null)
const resourceDetailLoading = ref(false)

const showGenerator = ref(true)

const difficultyOptions = [
  { value: 'beginner', label: '入门' },
  { value: 'intermediate', label: '中级' },
  { value: 'advanced', label: '进阶' },
]

function toggleType(type) {
  const idx = selectedTypes.value.indexOf(type)
  if (idx >= 0) selectedTypes.value.splice(idx, 1)
  else selectedTypes.value.push(type)
}

function renderMarkdown(text) {
  if (!text) return ''
  return DOMPurify.sanitize(marked.parse(text))
}

async function handleGenerate() {
  if (!selectedTypes.value.length || isGenerating.value) return

  isGenerating.value = true
  isThinking.value = true
  thinkingHint.value = '正在分析学习需求...'
  generatedContent.value = ''
  showGenerator.value = false

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
      generatedContent.value = displayText
      timerId = setTimeout(tick, delay)
    }
    timerId = setTimeout(tick, 0)
  }

  try {
    const points = knowledgePoints.value.split(/[,，、\n]/).map(s => s.trim()).filter(Boolean)
    const result = await resourceStreamAPI(
      {
        talkId: talkId.value,
        message: customMessage.value || `请为我生成${courseName.value}相关的学习资料`,
        resourceTypes: selectedTypes.value,
        courseName: courseName.value,
        knowledgePoints: points,
        difficulty: difficulty.value,
      },
      (chunk) => {
        if (isThinking.value) {
          isThinking.value = false
          thinkingHint.value = ''
        }
        charBuffer.push(...Array.from(chunk))
        startTypewriter()
      },
      (thinking) => {
        thinkingHint.value = thinking.title || 'AI 协同生成中...'
      },
    )

    if (timerId !== null) { clearTimeout(timerId); timerId = null }
    generatedContent.value = result.data?.content || displayText
    if (result.data?.talkId) talkId.value = result.data.talkId

    await fetchResources()
  } catch (error) {
    console.error('资源生成失败', error)
    const errorMsg = error?.message || error?.msg || '未知错误'
    if (errorMsg.includes('未登录') || errorMsg.includes('401') || errorMsg.includes('403')) {
      generatedContent.value = '⚠️ 登录已过期，请重新登录后重试。'
    } else if (errorMsg.includes('网络') || errorMsg.includes('fetch') || errorMsg.includes('Failed')) {
      generatedContent.value = '❌ 网络连接失败，请检查后端服务是否启动。'
    } else if (errorMsg.includes('timeout') || errorMsg.includes('Timeout')) {
      generatedContent.value = '⏰ 请求超时，请稍后重试。'
    } else {
      generatedContent.value = `❌ 生成失败：${errorMsg}`
    }
  } finally {
    isGenerating.value = false
    isThinking.value = false
    thinkingHint.value = ''
  }
}

async function fetchResources() {
  resourcesLoading.value = true
  try {
    const res = await getResourcesAPI({ page: resourcePage.value, size: 12 })
    resources.value = res.data?.records || []
    resourceTotal.value = res.data?.total || 0
  } catch {
    // ignore
  } finally {
    resourcesLoading.value = false
  }
}

async function handleSelectResource(id) {
  selectedResource.value = id
  resourceDetailLoading.value = true
  showGenerator.value = false
  try {
    const res = await getResourceDetailAPI(id)
    resourceDetail.value = res.data
    generatedContent.value = res.data?.content || ''
  } catch {
    // ignore
  } finally {
    resourceDetailLoading.value = false
  }
}

function backToGenerator() {
  showGenerator.value = true
  generatedContent.value = ''
  resourceDetail.value = null
  selectedResource.value = null
}

function getTypeInfo(type) {
  return resourceTypes.find(t => t.value === type) || { label: type, icon: '📌', color: '#64748b' }
}

onMounted(() => {
  fetchResources()
})
</script>

<template>
  <div class="resources-page">
    <div class="page-header">
      <div class="header-content">
        <h1>资源生成</h1>
        <p>多智能体协同生成脑卒中个性化多模态学习资源</p>
      </div>
      <div class="header-badge">核心功能2 · 必选</div>
    </div>

    <div class="resources-body">
      <div class="generator-area">
        <div v-if="showGenerator" class="generator-form">
          <div class="form-section">
            <div class="section-label">选择资源类型 <span class="required">*</span></div>
            <div class="type-grid">
              <button
                v-for="rt in resourceTypes"
                :key="rt.value"
                class="type-chip"
                :class="{ active: selectedTypes.includes(rt.value) }"
                :style="{ '--chip-color': rt.color }"
                @click="toggleType(rt.value)"
              >
                <span class="chip-icon">{{ rt.icon }}</span>
                <span class="chip-label">{{ rt.label }}</span>
              </button>
            </div>
          </div>

          <div class="form-row">
            <div class="form-field">
              <label>课程名称</label>
              <input v-model="courseName" placeholder="如：神经病学" />
            </div>
            <div class="form-field">
              <label>难度级别</label>
              <div class="difficulty-selector">
                <button
                  v-for="d in difficultyOptions"
                  :key="d.value"
                  class="diff-btn"
                  :class="{ active: difficulty === d.value }"
                  @click="difficulty = d.value"
                >{{ d.label }}</button>
              </div>
            </div>
          </div>

          <div class="form-field">
            <label>知识点 <span class="hint">用逗号分隔</span></label>
            <input v-model="knowledgePoints" placeholder="如：缺血性脑卒中, 静脉溶栓, TOAST分型, 脑出血" />
          </div>

          <div class="form-field">
            <label>补充说明 <span class="hint">可选</span></label>
            <textarea v-model="customMessage" placeholder="描述你的具体需求，如：重点讲解溶栓时间窗和rt-PA用法..." rows="2"></textarea>
          </div>

          <button class="generate-btn" :disabled="!selectedTypes.length || isGenerating" @click="handleGenerate">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
            </svg>
            <span>{{ isGenerating ? '生成中...' : '开始生成' }}</span>
          </button>
        </div>

        <div v-else class="result-area">
          <div class="result-header">
            <button class="back-btn" @click="backToGenerator">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/>
              </svg>
              返回
            </button>
            <span class="result-title">{{ resourceDetail?.title || '生成结果' }}</span>
          </div>

          <div v-if="isThinking" class="thinking-bar">
            <div class="thinking-dots"><span></span><span></span><span></span></div>
            <span>{{ thinkingHint }}</span>
          </div>

          <div class="result-content markdown-body" v-html="renderMarkdown(generatedContent)"></div>

          <div v-if="isGenerating && !generatedContent" class="generating-overlay">
            <div class="gen-spinner"></div>
            <div class="gen-text">多智能体协同生成中...</div>
            <div class="gen-sub">{{ thinkingHint || '请稍候' }}</div>
          </div>
        </div>
      </div>

      <div class="resource-list-panel">
        <div class="panel-title">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
            <polyline points="14 2 14 8 20 8"/>
          </svg>
          <span>已生成资源</span>
          <span class="count-badge">{{ resourceTotal }}</span>
        </div>

        <div class="resource-list">
          <div v-if="resourcesLoading" class="list-loading">
            <div class="loading-spinner"></div>
          </div>
          <div v-else-if="!resources.length" class="list-empty">
            <span>暂无资源</span>
          </div>
          <div
            v-else
            v-for="r in resources"
            :key="r.resourceId"
            class="resource-item"
            :class="{ active: selectedResource === r.resourceId }"
            @click="handleSelectResource(r.resourceId)"
          >
            <div class="item-icon" :style="{ background: getTypeInfo(r.type).color + '18', color: getTypeInfo(r.type).color }">
              {{ getTypeInfo(r.type).icon }}
            </div>
            <div class="item-info">
              <div class="item-title">{{ r.title }}</div>
              <div class="item-meta">
                <span class="item-type">{{ getTypeInfo(r.type).label }}</span>
                <span class="item-course">{{ r.courseName }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.resources-page {
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
}

.header-content {
  h1 { margin: 0; font-size: 1.5rem; font-weight: 800; color: var(--color-text-strong); letter-spacing: -0.02em; }
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

.resources-body {
  flex: 1;
  display: flex;
  min-height: 0;
  overflow: hidden;
}

.generator-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  overflow: hidden;
}

.generator-form {
  padding: 24px 28px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.form-section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.section-label {
  font-size: 14px;
  font-weight: 700;
  color: var(--color-text-strong);

  .required { color: var(--color-red); }
}

.type-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 8px;
}

.type-chip {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border: 2px solid var(--color-border-light);
  border-radius: var(--radius-lg);
  background: var(--color-bg-base);
  cursor: pointer;
  transition: all var(--transition-fast);
  font: inherit;

  &:hover {
    border-color: var(--chip-color, var(--color-border));
    background: color-mix(in srgb, var(--chip-color) 4%, var(--color-bg-base));
  }

  &.active {
    border-color: var(--chip-color);
    background: color-mix(in srgb, var(--chip-color) 8%, var(--color-bg-base));
    box-shadow: 0 0 0 3px color-mix(in srgb, var(--chip-color) 12%, transparent);
  }
}

.chip-icon { font-size: 18px; line-height: 1; }
.chip-label { font-size: 13px; font-weight: 600; color: var(--color-text-strong); }

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.form-field {
  display: flex;
  flex-direction: column;
  gap: 6px;

  label {
    font-size: 13px;
    font-weight: 700;
    color: var(--color-text-strong);

    .hint { font-weight: 400; color: var(--color-text-weak); font-size: 12px; }
  }

  input, textarea {
    padding: 10px 14px;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-md);
    background: var(--color-bg-input);
    color: var(--color-text-strong);
    font: inherit;
    font-size: 14px;
    transition: border-color var(--transition-fast), box-shadow var(--transition-fast);

    &:focus {
      outline: none;
      border-color: var(--color-primary);
    box-shadow: 0 0 0 3px rgba(17, 150, 127, 0.15), var(--glow-primary);
    }

    &::placeholder { color: var(--color-text-weak); }
  }

  textarea { resize: vertical; min-height: 60px; }
}

.difficulty-selector {
  display: flex;
  gap: 6px;
}

.diff-btn {
  flex: 1;
  padding: 8px 12px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-bg-input);
  color: var(--color-text-medium);
  cursor: pointer;
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  transition: all var(--transition-fast);

  &:hover { border-color: var(--color-primary); }

  &.active {
  background: var(--gradient-aurora);
    color: #fff;
    border-color: transparent;
  }
}

.generate-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 14px 24px;
  border: none;
  border-radius: var(--radius-lg);
  background: var(--gradient-aurora);
  color: #fff;
  font: inherit;
  font-size: 15px;
  font-weight: 700;
  cursor: pointer;
  transition: all var(--transition-fast);

  &:hover:not(:disabled) { opacity: 0.88; transform: translateY(-1px); box-shadow: 0 4px 16px rgba(17, 150, 127, 0.3); }
  &:disabled { opacity: 0.5; cursor: not-allowed; }
}

.result-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  position: relative;
}

.result-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 24px;
  border-bottom: 1px solid var(--color-border-light);
  flex-shrink: 0;
}

.back-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-bg-base);
  color: var(--color-text-medium);
  cursor: pointer;
  font: inherit;
  font-size: 13px;
  transition: all var(--transition-fast);

  &:hover { background: var(--color-ghost-hover); color: var(--color-text-strong); }
}

.result-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--color-text-strong);
}

.thinking-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 24px;
  background: rgba(17, 150, 127, 0.04);
  font-size: 13px;
  color: var(--color-primary-dark);
  flex-shrink: 0;
}

.thinking-dots {
  display: flex;
  gap: 4px;
  span {
    width: 5px; height: 5px; border-radius: 50%; background: var(--color-primary);
    animation: bounce 1.4s infinite ease-in-out;
    &:nth-child(1) { animation-delay: 0s; }
    &:nth-child(2) { animation-delay: 0.2s; }
    &:nth-child(3) { animation-delay: 0.4s; }
  }
}

@keyframes bounce {
  0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
  40% { transform: scale(1); opacity: 1; }
}

.result-content {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
}

.generating-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  background: var(--color-bg-base);
  z-index: 5;
}

.gen-spinner {
  width: 48px; height: 48px;
  border: 4px solid var(--color-border-light);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }

.gen-text { font-size: 16px; font-weight: 700; color: var(--color-text-strong); }
.gen-sub { font-size: 13px; color: var(--color-text-medium); }

.resource-list-panel {
  width: 320px;
  min-width: 320px;
  display: flex;
  flex-direction: column;
  border-left: 1px solid var(--color-border-light);
  background: var(--color-bg-light);
}

.panel-title {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 14px 16px;
  font-size: 14px;
  font-weight: 700;
  color: var(--color-text-strong);
  border-bottom: 1px solid var(--color-border-light);
  flex-shrink: 0;
}

.count-badge {
  padding: 1px 8px;
  border-radius: var(--radius-pill);
  font-size: 11px;
  font-weight: 700;
  background: rgba(17, 150, 127, 0.1);
  color: var(--color-primary-dark);
}

.resource-list {
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

.resource-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--transition-fast);

  &:hover { background: var(--color-hover-bg); }
  &.active { background: var(--color-active-bg); }
}

.item-icon {
  flex-shrink: 0;
  width: 36px; height: 36px;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
}

.item-info { min-width: 0; flex: 1; }

.item-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-strong);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.item-meta {
  display: flex;
  gap: 6px;
  margin-top: 2px;
  font-size: 11px;
  color: var(--color-text-weak);
}

@media (max-width: 1024px) {
  .resource-list-panel { width: 260px; min-width: 260px; }
  .type-grid { grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); }
}

@media (max-width: 768px) {
  .resources-body { flex-direction: column; }
  .resource-list-panel { width: 100%; min-width: 100%; max-height: 30vh; border-left: none; border-top: 1px solid var(--color-border-light); }
  .form-row { grid-template-columns: 1fr; }
}

.resource-card { animation: fade-in-up 0.4s cubic-bezier(0.16, 1, 0.3, 1) both; }
.resource-card:hover { transform: translateY(-3px); }
.message { animation: fade-in-up 0.3s cubic-bezier(0.16, 1, 0.3, 1) both; }
.conv-item { transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1); }
.conv-item:hover { transform: translateX(4px); }
</style>
