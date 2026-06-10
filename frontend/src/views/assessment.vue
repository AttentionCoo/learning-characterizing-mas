<script setup>
import { ref, computed, onMounted } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import { getAssessmentReportsAPI, getAssessmentReportDetailAPI, assessmentStreamAPI } from '@/api/assessment'

marked.setOptions({ gfm: true, breaks: true })

const reports = ref([])
const reportsLoading = ref(false)
const reportTotal = ref(0)
const reportPage = ref(1)
const selectedReportId = ref(null)
const reportDetail = ref(null)
const reportDetailLoading = ref(false)

const isGenerating = ref(false)
const isThinking = ref(false)
const thinkingHint = ref('')
const generatedContent = ref('')
const talkId = ref(null)

const assessmentType = ref('comprehensive')
const courseName = ref('')
const customMessage = ref('')

const assessmentTypes = [
  { value: 'comprehensive', label: '综合评估', icon: '📊', desc: '全面评估学习效果' },
  { value: 'knowledge', label: '知识掌握', icon: '📚', desc: '评估知识点掌握程度' },
  { value: 'skill', label: '技能水平', icon: '🎯', desc: '评估临床技能水平' },
  { value: 'progress', label: '学习进度', icon: '📈', desc: '评估学习进度与效率' },
]

function renderMarkdown(text) {
  if (!text) return ''
  return DOMPurify.sanitize(marked.parse(text))
}

onMounted(() => {
  fetchReports()
})

async function fetchReports() {
  reportsLoading.value = true
  try {
    const res = await getAssessmentReportsAPI({ page: reportPage.value, size: 12 })
    reports.value = res.data?.records || []
    reportTotal.value = res.data?.total || 0
  } catch {
    // ignore
  } finally {
    reportsLoading.value = false
  }
}

async function selectReport(id) {
  selectedReportId.value = id
  reportDetailLoading.value = true
  try {
    const res = await getAssessmentReportDetailAPI(id)
    reportDetail.value = res.data
    generatedContent.value = res.data?.content || ''
  } catch {
    // ignore
  } finally {
    reportDetailLoading.value = false
  }
}

async function handleGenerate() {
  if (isGenerating.value) return

  isGenerating.value = true
  isThinking.value = true
  thinkingHint.value = '正在评估学习效果...'
  generatedContent.value = ''
  reportDetail.value = null
  selectedReportId.value = null

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
    const result = await assessmentStreamAPI(
      {
        talkId: talkId.value,
        message: customMessage.value || '请为我进行学习评估',
        assessmentType: assessmentType.value,
        courseName: courseName.value,
      },
      (chunk) => {
        if (isThinking.value) { isThinking.value = false; thinkingHint.value = '' }
        charBuffer.push(...Array.from(chunk))
        startTypewriter()
      },
      (thinking) => { thinkingHint.value = thinking.title || 'AI 评估中...' },
    )

    if (timerId !== null) { clearTimeout(timerId); timerId = null }
    generatedContent.value = result.data?.content || displayText
    if (result.data?.talkId) talkId.value = result.data.talkId

    await fetchReports()
  } catch (error) {
    console.error('评估生成失败', error)
    generatedContent.value = '评估生成失败，请稍后重试。'
  } finally {
    isGenerating.value = false
    isThinking.value = false
    thinkingHint.value = ''
  }
}

function getTypeInfo(type) {
  return assessmentTypes.find(t => t.value === type) || { label: type, icon: '📋', desc: '' }
}

function getScoreColor(score) {
  if (score >= 80) return '#10b981'
  if (score >= 60) return '#f59e0b'
  return '#ef4444'
}
</script>

<template>
  <div class="assessment-page">
    <div class="page-header">
      <div class="header-content">
        <h1>学习评估</h1>
        <p>多维度学习效果评估与优化建议</p>
      </div>
      <div class="header-badge">核心功能5 · 必选</div>
    </div>

    <div class="assessment-body">
      <div class="assessment-main">
        <div class="generate-section">
          <div class="section-title">发起评估</div>
          <div class="type-selector">
            <button
              v-for="t in assessmentTypes"
              :key="t.value"
              class="type-btn"
              :class="{ active: assessmentType === t.value }"
              @click="assessmentType = t.value"
            >
              <span class="type-icon">{{ t.icon }}</span>
              <div class="type-text">
                <span class="type-label">{{ t.label }}</span>
                <span class="type-desc">{{ t.desc }}</span>
              </div>
            </button>
          </div>

          <div class="form-row">
            <div class="form-field">
              <label>课程名称 <span class="hint">可选</span></label>
              <input v-model="courseName" placeholder="如：内科学" />
            </div>
            <div class="form-field">
              <label>补充说明 <span class="hint">可选</span></label>
              <input v-model="customMessage" placeholder="如：重点评估神经病学" />
            </div>
          </div>

          <button class="assess-btn" :disabled="isGenerating" @click="handleGenerate">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="18" y1="20" x2="18" y2="10"/>
              <line x1="12" y1="20" x2="12" y2="4"/>
              <line x1="6" y1="20" x2="6" y2="14"/>
            </svg>
            {{ isGenerating ? '评估中...' : '开始评估' }}
          </button>
        </div>

        <div v-if="isThinking || generatedContent" class="result-section">
          <div class="section-title">评估结果</div>

          <div v-if="isThinking && !generatedContent" class="thinking-bar">
            <div class="thinking-dots"><span></span><span></span><span></span></div>
            <span>{{ thinkingHint }}</span>
          </div>

          <div v-if="reportDetail?.scores" class="score-cards">
            <div v-for="(score, key) in reportDetail.scores" :key="key" class="score-card">
              <div class="score-ring">
                <svg viewBox="0 0 100 100">
                  <circle cx="50" cy="50" r="40" fill="none" stroke="var(--color-border-light)" stroke-width="6"/>
                  <circle cx="50" cy="50" r="40" fill="none" :stroke="getScoreColor(score)" stroke-width="6"
                    :stroke-dasharray="`${score * 2.51} 251`"
                    stroke-linecap="round"
                    transform="rotate(-90 50 50)"
                    style="transition: stroke-dasharray 0.6s ease"
                  />
                </svg>
                <div class="score-value" :style="{ color: getScoreColor(score) }">{{ score }}</div>
              </div>
              <div class="score-label">{{ key }}</div>
            </div>
          </div>

          <div v-if="generatedContent" class="result-content markdown-body" v-html="renderMarkdown(generatedContent)"></div>
        </div>
      </div>

      <div class="reports-sidebar">
        <div class="sidebar-title">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="18" y1="20" x2="18" y2="10"/>
            <line x1="12" y1="20" x2="12" y2="4"/>
            <line x1="6" y1="20" x2="6" y2="14"/>
          </svg>
          <span>评估记录</span>
          <span class="count-badge">{{ reportTotal }}</span>
        </div>

        <div class="reports-list">
          <div v-if="reportsLoading" class="list-loading">
            <div class="loading-spinner"></div>
          </div>
          <div v-else-if="!reports.length" class="list-empty">
            <span>暂无评估记录</span>
          </div>
          <div
            v-else
            v-for="r in reports"
            :key="r.reportId"
            class="report-item"
            :class="{ active: selectedReportId === r.reportId }"
            @click="selectReport(r.reportId)"
          >
            <div class="report-icon">{{ getTypeInfo(r.type).icon }}</div>
            <div class="report-info">
              <div class="report-title">{{ r.title || '评估报告' }}</div>
              <div class="report-meta">
                <span>{{ getTypeInfo(r.type).label }}</span>
                <span v-if="r.score" class="report-score" :style="{ color: getScoreColor(r.score) }">{{ r.score }}分</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.assessment-page {
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

.assessment-body {
  flex: 1;
  display: flex;
  min-height: 0;
  overflow: hidden;
}

.assessment-main {
  flex: 1;
  overflow-y: auto;
  padding: 24px 28px;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.section-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--color-text-strong);
  margin-bottom: 14px;
}

.generate-section {
  background: var(--color-bg-light);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-xl);
  padding: 20px 24px;
}

.type-selector {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 10px;
  margin-bottom: 18px;
}

.type-btn {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  border: 2px solid var(--color-border-light);
  border-radius: var(--radius-lg);
  background: var(--color-bg-base);
  cursor: pointer;
  transition: all var(--transition-fast);
  font: inherit;
  text-align: left;

  &:hover { border-color: var(--color-border); }

  &.active {
    border-color: var(--color-primary);
    background: rgba(17, 150, 127, 0.04);
    box-shadow: 0 0 0 3px rgba(17, 150, 127, 0.1);
  }
}

.type-icon { font-size: 24px; line-height: 1; }

.type-text { display: flex; flex-direction: column; }
.type-label { font-size: 14px; font-weight: 700; color: var(--color-text-strong); }
.type-desc { font-size: 11px; color: var(--color-text-weak); margin-top: 1px; }

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
  margin-bottom: 14px;
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

  input {
    padding: 10px 14px;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-md);
    background: var(--color-bg-input);
    color: var(--color-text-strong);
    font: inherit;
    font-size: 14px;
    transition: border-color var(--transition-fast), box-shadow var(--transition-fast);

    &:focus { outline: none; border-color: var(--color-primary); box-shadow: 0 0 0 3px rgba(17, 150, 127, 0.12); }
    &::placeholder { color: var(--color-text-weak); }
  }
}

.assess-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 12px 24px;
  border: none;
  border-radius: var(--radius-lg);
  background: var(--color-primary-gradient);
  color: #fff;
  font: inherit;
  font-size: 14px;
  font-weight: 700;
  cursor: pointer;
  transition: all var(--transition-fast);

  &:hover:not(:disabled) { opacity: 0.88; transform: translateY(-1px); box-shadow: 0 4px 16px rgba(17, 150, 127, 0.3); }
  &:disabled { opacity: 0.5; cursor: not-allowed; }
}

.result-section {
  background: var(--color-bg-light);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-xl);
  padding: 20px 24px;
}

.thinking-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  background: rgba(17, 150, 127, 0.04);
  border-radius: var(--radius-md);
  font-size: 13px;
  color: var(--color-primary-dark);
  margin-bottom: 16px;
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

.score-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 14px;
  margin-bottom: 20px;
}

.score-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 16px 12px;
  background: var(--color-bg-base);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-lg);
}

.score-ring {
  position: relative;
  width: 64px;
  height: 64px;
  svg { width: 100%; height: 100%; }
}

.score-value {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.1rem;
  font-weight: 800;
}

.score-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text-medium);
  text-align: center;
}

.result-content {
  line-height: 1.7;
}

.reports-sidebar {
  width: 300px;
  min-width: 300px;
  display: flex;
  flex-direction: column;
  border-left: 1px solid var(--color-border-light);
  background: var(--color-bg-light);
}

.sidebar-title {
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

.reports-list {
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

.report-item {
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

.report-icon {
  flex-shrink: 0;
  width: 36px; height: 36px;
  border-radius: var(--radius-md);
  background: rgba(17, 150, 127, 0.08);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
}

.report-info { flex: 1; min-width: 0; }

.report-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-strong);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.report-meta {
  display: flex;
  gap: 8px;
  margin-top: 2px;
  font-size: 11px;
  color: var(--color-text-weak);
}

.report-score {
  font-weight: 700;
}

@media (max-width: 1024px) {
  .reports-sidebar { width: 260px; min-width: 260px; }
  .type-selector { grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); }
}

@media (max-width: 768px) {
  .assessment-body { flex-direction: column; }
  .reports-sidebar { width: 100%; min-width: 100%; max-height: 30vh; border-left: none; border-top: 1px solid var(--color-border-light); }
  .form-row { grid-template-columns: 1fr; }
  .type-selector { grid-template-columns: 1fr 1fr; }
}
</style>
