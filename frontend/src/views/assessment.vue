<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import { getAssessmentReportsAPI, getAssessmentReportDetailAPI, assessmentStreamAPI, getAssessmentReportAPI, optimizeLearningPathAPI } from '@/api/assessment'
import { getLearningPathsAPI } from '@/api/learningPath'
import ReasoningTrace from '@/components/ReasoningTrace.vue'
import AssessmentRadarChart from '@/components/AssessmentRadarChart.vue'
import { useReasoningTrace } from '@/composables/useReasoningTrace'
import { normalizeAiMarkdown } from '@/utils/aiMarkdown'
import { buildAssessmentRadar } from '@/utils/assessmentRadar'

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
const { reasoningEntries, resetReasoningTrace, appendReasoningEvent } = useReasoningTrace()

const assessmentType = ref('comprehensive')
const courseName = ref('')
const customMessage = ref('')

const isOptimizing = ref(false)
const optimizeResult = ref(null)
const currentReportData = ref(null)
const learningPathId = ref(null)

const resultContentRef = ref(null)
const userScrolled = ref(false)

const radarDimensions = computed(() => {
  const generatedSource = generatedContent.value
  if (isGenerating.value) return generatedSource

  const sources = [
    reportDetail.value?.scores,
    reportDetail.value?.dimensions,
    generatedSource,
    currentReportData.value?.dimensions,
  ]
  return sources.find(source => (
    buildAssessmentRadar(source).some(item => item.hasData)
  )) || {}
})

const radarOverallScore = computed(() => (
  reportDetail.value?.score
  ?? reportDetail.value?.overallScore
  ?? currentReportData.value?.overallScore
  ?? null
))

function onResultScroll() {
  const el = resultContentRef.value
  if (!el) return
  const distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
  userScrolled.value = distFromBottom > 80
}

function scrollToBottom(force = false) {
  const el = resultContentRef.value
  if (!el) return
  if (!force && userScrolled.value) return
  el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
}

const assessmentTypes = [
  { value: 'comprehensive', label: '综合评估', icon: '📊', desc: '全面评估脑卒中学习效果' },
  { value: 'knowledge', label: '知识掌握', icon: '📚', desc: '评估脑卒中知识点掌握程度' },
  { value: 'skill', label: '临床技能', icon: '🎯', desc: '评估脑卒中临床技能水平' },
  { value: 'progress', label: '学习进度', icon: '📈', desc: '评估脑卒中学习进度与效率' },
]

function renderMarkdown(text) {
  if (!text) return ''
  return DOMPurify.sanitize(marked.parse(normalizeAiMarkdown(text)))
}

onMounted(() => {
  fetchReports()
  fetchCurrentReport()
  fetchLearningPathId()
})

async function fetchLearningPathId() {
  try {
    const res = await getLearningPathsAPI()
    const firstPath = res.data?.records?.[0]
    if (firstPath?.pathId) learningPathId.value = firstPath.pathId
  } catch {
    // ignore
  }
}

async function fetchCurrentReport() {
  try {
    const res = await getAssessmentReportAPI()
    if (res.data) currentReportData.value = res.data
  } catch {
    // ignore
  }
}

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
  resetReasoningTrace()
  reportDetail.value = null
  selectedReportId.value = null
  userScrolled.value = false

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
      nextTick(() => scrollToBottom())
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
      (thinking) => {
        thinkingHint.value = thinking.title || 'AI 评估中...'
        appendReasoningEvent(thinking)
      },
    )

    if (timerId !== null) { clearTimeout(timerId); timerId = null }
    generatedContent.value = result.data?.content || displayText
    if (result.data?.talkId) talkId.value = result.data.talkId
    nextTick(() => scrollToBottom(true))

    await fetchReports()
    setTimeout(fetchReports, 1200)
    await fetchCurrentReport()
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

async function handleOptimize() {
  if (isOptimizing.value) return
  isOptimizing.value = true
  optimizeResult.value = null

  try {
    const pathId = learningPathId.value || null

    const evalData = reportDetail.value || currentReportData.value
    const res = await optimizeLearningPathAPI({
      pathId: pathId,
      triggerReason: 'evaluation_optimize',
      evaluationData: evalData ? {
        overallScore: evalData.overallScore ?? evalData.score ?? 0,
        level: evalData.level,
        dimensions: evalData.dimensions,
        weaknesses: evalData.weaknesses,
        suggestions: evalData.suggestions,
      } : null,
    })
    optimizeResult.value = res.data
  } catch (error) {
    console.error('优化失败', error)
    optimizeResult.value = { optimizationApplied: false, changes: [], reason: '优化服务暂时不可用' }
  } finally {
    isOptimizing.value = false
  }
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
        <p>脑卒中多维度学习效果评估与优化建议</p>
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
              <input v-model="courseName" placeholder="如：脑卒中诊疗" />
            </div>
            <div class="form-field">
              <label>补充说明 <span class="hint">可选</span></label>
              <input v-model="customMessage" placeholder="如：重点评估脑卒中诊疗知识" />
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

        <div class="result-section">
          <div class="section-title">评估结果</div>

          <div v-if="isThinking && !generatedContent" class="thinking-bar">
            <div class="thinking-dots"><span></span><span></span><span></span></div>
            <span>{{ thinkingHint }}</span>
          </div>

          <ReasoningTrace :entries="reasoningEntries" :running="isGenerating" />

          <AssessmentRadarChart
            :dimensions="radarDimensions"
            :overall-score="radarOverallScore"
          />

          <div ref="resultContentRef" v-if="generatedContent" class="result-content markdown-body" @scroll="onResultScroll" v-html="renderMarkdown(generatedContent)"></div>

          <div v-if="reportDetail || currentReportData" class="optimize-section">
            <button class="optimize-btn" :disabled="isOptimizing" @click="handleOptimize">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M12 20V10"/>
                <path d="M18 20V4"/>
                <path d="M6 20v-4"/>
              </svg>
              {{ isOptimizing ? '优化中...' : '基于评估优化学习路径' }}
            </button>

            <div v-if="optimizeResult" class="optimize-result">
              <div v-if="optimizeResult.optimizationApplied" class="optimize-success">
                <div class="optimize-badge success">已优化</div>
                <div class="optimize-changes">
                  <div v-for="(change, idx) in optimizeResult.changes" :key="idx" class="change-item">
                    <span class="change-type">{{ change.type === 'adjust_difficulty' ? '调整难度' : change.type === 'insert_step' ? '新增步骤' : '更新资源' }}</span>
                    <span class="change-desc">{{ change.description }}</span>
                    <span v-if="change.reason" class="change-reason">{{ change.reason }}</span>
                  </div>
                </div>
              </div>
              <div v-else class="optimize-skip">
                <div class="optimize-badge skip">无需调整</div>
                <span>{{ optimizeResult.reason || '当前学习路径无需优化' }}</span>
              </div>
            </div>
          </div>
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

    box-shadow: 0 0 0 3px rgba(17, 150, 127, 0.15), var(--glow-primary);
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
  background: var(--gradient-aurora);
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

.result-content {
  line-height: 1.7;
  max-height: 60vh;
  overflow-y: auto;
  scroll-behavior: smooth;
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

.optimize-section {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--color-border-light);
}

.optimize-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 10px 20px;
  border: 2px solid var(--color-primary);
  border-radius: var(--radius-lg);
  background: transparent;
  color: var(--color-primary);
  font: inherit;
  font-size: 14px;
  font-weight: 700;
  cursor: pointer;
  transition: all var(--transition-fast);

  &:hover:not(:disabled) { background: rgba(17, 150, 127, 0.08); transform: translateY(-1px); }
  &:disabled { opacity: 0.5; cursor: not-allowed; }
}

.optimize-result {
  margin-top: 12px;
  padding: 14px 16px;
  border-radius: var(--radius-md);
  background: var(--color-bg-base);
  border: 1px solid var(--color-border-light);
}

.optimize-badge {
  display: inline-block;
  padding: 2px 10px;
  border-radius: var(--radius-pill);
  font-size: 12px;
  font-weight: 700;
  margin-bottom: 8px;

  &.success { background: rgba(16, 185, 129, 0.1); color: #10b981; }
  &.skip { background: rgba(245, 158, 11, 0.1); color: #f59e0b; }
}

.optimize-changes {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.change-item {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 6px;
  font-size: 13px;
}

.change-type {
  padding: 1px 8px;
  border-radius: var(--radius-pill);
  font-size: 11px;
  font-weight: 700;
  background: rgba(59, 130, 246, 0.1);
  color: #3b82f6;
}

.change-desc {
  font-weight: 600;
  color: var(--color-text-strong);
}

.change-reason {
  font-size: 12px;
  color: var(--color-text-medium);
}

.optimize-skip {
  font-size: 13px;
  color: var(--color-text-medium);
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

.report-card { animation: fade-in-up 0.4s cubic-bezier(0.16, 1, 0.3, 1) both; }
.report-card:hover { transform: translateY(-3px); }
.message { animation: fade-in-up 0.3s cubic-bezier(0.16, 1, 0.3, 1) both; }
.conv-item { transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1); }
.conv-item:hover { transform: translateX(4px); }
</style>
