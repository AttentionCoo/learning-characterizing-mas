<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { renderMarkdown } from '@/utils/markdown'
import { getLearningPathAPI, updateTaskProgressAPI, learningPathStreamAPI } from '@/api/learningPath'
import { submitBehaviorAPI } from '@/api/assessment'
import ReasoningTrace from '@/components/ReasoningTrace.vue'
import { useReasoningTrace } from '@/composables/useReasoningTrace'

const learningPath = ref(null)
const pathLoading = ref(false)
const isGenerating = ref(false)
const isThinking = ref(false)
const thinkingHint = ref('')
const generatedContent = ref('')
const talkId = ref(null)
const expandedSteps = ref(new Set([0]))
const { reasoningEntries, resetReasoningTrace, appendReasoningEvent } = useReasoningTrace()

const courseName = ref('')
const customGoal = ref('')

const pageEnterTime = Date.now()
const stepViewTimes = ref({})
let behaviorFlushTimer = null
const pendingBehaviors = ref([])

function trackStepView(stepId) {
  stepViewTimes.value[stepId] = Date.now()
}

function trackStepLeave(stepId) {
  const enterTime = stepViewTimes.value[stepId]
  if (!enterTime) return
  const durationSec = Math.round((Date.now() - enterTime) / 1000)
  delete stepViewTimes.value[stepId]
  if (durationSec < 5) return
  pendingBehaviors.value.push({
    type: 'resource_view',
    resourceId: stepId,
    duration: durationSec,
    timestamp: new Date().toISOString(),
  })
}

async function flushBehaviors() {
  if (!learningPath.value?.pathId) return
  const behaviors = [...pendingBehaviors.value]
  if (behaviors.length === 0) return
  pendingBehaviors.value = []

  const totalDuration = Math.round((Date.now() - pageEnterTime) / 1000)
  behaviors.push({
    type: 'page_stay',
    duration: totalDuration,
    timestamp: new Date().toISOString(),
  })

  try {
    await submitBehaviorAPI({
      pathId: learningPath.value.pathId,
      stepId: null,
      behaviors,
    })
  } catch {
    // ignore
  }
}

function startBehaviorFlush() {
  if (behaviorFlushTimer) return
  behaviorFlushTimer = setInterval(flushBehaviors, 60000)
}


onMounted(() => {
  fetchLearningPath()
  startBehaviorFlush()
})

onUnmounted(() => {
  if (behaviorFlushTimer) { clearInterval(behaviorFlushTimer); behaviorFlushTimer = null }
  flushBehaviors()
})

async function fetchLearningPath() {
  pathLoading.value = true
  try {
    const res = await getLearningPathAPI()
    if (res.data) learningPath.value = res.data
  } catch {
    // path may not exist yet
  } finally {
    pathLoading.value = false
  }
}

function toggleStep(index) {
  const s = new Set(expandedSteps.value)
  const step = learningPath.value?.steps?.[index]
  if (s.has(index)) {
    s.delete(index)
    if (step?.stepId) trackStepLeave(step.stepId)
  } else {
    s.add(index)
    if (step?.stepId) trackStepView(step.stepId)
  }
  expandedSteps.value = s
}

function normalizeStatus(status) {
  if (status === 'not_started') return 'pending'
  return status || 'pending'
}

function getStatusIcon(status) {
  switch (status) {
    case 'completed': return '✅'
    case 'in_progress': return '🔄'
    default: return '⬜'
  }
}

async function handleGenerate() {
  if (isGenerating.value) return

  isGenerating.value = true
  isThinking.value = true
  thinkingHint.value = '正在规划学习路径...'
  generatedContent.value = ''
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
      generatedContent.value = displayText
      timerId = setTimeout(tick, delay)
    }
    timerId = setTimeout(tick, 0)
  }

  try {
    const result = await learningPathStreamAPI(
      {
        goalDescription: customGoal.value || '请为我规划学习路径',
        courseName: courseName.value,
      },
      (chunk, event = {}) => {
        if (isThinking.value) { isThinking.value = false; thinkingHint.value = '' }
        if (event.replace) {
          if (timerId !== null) { clearTimeout(timerId); timerId = null }
          charBuffer.length = 0
          displayText = chunk
          generatedContent.value = displayText
          return
        }
        charBuffer.push(...Array.from(chunk))
        startTypewriter()
      },
      (thinking) => {
        thinkingHint.value = thinking.title || 'AI 规划中...'
        appendReasoningEvent(thinking)
      },
    )

    if (timerId !== null) { clearTimeout(timerId); timerId = null }
    generatedContent.value = result.data?.content || displayText
    if (result.data?.talkId) talkId.value = result.data.talkId

    await fetchLearningPath()
    setTimeout(fetchLearningPath, 1200)
  } catch (error) {
    console.error('路径生成失败', error)
    generatedContent.value = '生成失败，请稍后重试。'
  } finally {
    isGenerating.value = false
    isThinking.value = false
    thinkingHint.value = ''
  }
}

async function toggleTaskStatus(task) {
  const newStatus = task.status === 'completed' ? 'pending' : 'completed'
  try {
    await updateTaskProgressAPI(task.stepId, { status: newStatus === 'pending' ? 'not_started' : newStatus })
    task.status = newStatus

    if (newStatus === 'completed' && learningPath.value?.pathId) {
      pendingBehaviors.value.push({
        type: 'step_complete',
        resourceId: task.stepId,
        timestamp: new Date().toISOString(),
      })
    }

    await fetchLearningPath()
  } catch {
    // ignore
  }
}

const overallProgress = computed(() => {
  const total = learningPath.value?.totalSteps || learningPath.value?.steps?.length || 0
  if (!total) return 0
  const completed = learningPath.value?.completedSteps ?? learningPath.value.steps.filter(t => t.status === 'completed').length
  return Math.round((completed / total) * 100)
})
</script>

<template>
  <div class="learning-path-page">
    <div class="page-header">
      <div class="header-content">
        <h1>学习路径</h1>
        <p>基于学习画像的脑卒中个性化路径规划与推荐</p>
      </div>
      <div class="header-badge">核心功能3 · 必选</div>
    </div>

    <div class="path-body">
      <div class="path-main">
        <div v-if="pathLoading" class="path-loading">
          <div class="loading-spinner"></div>
          <span>加载学习路径...</span>
        </div>

        <div v-else-if="!learningPath" class="path-empty">
          <div class="empty-visual">
            <div class="empty-icon">🗺️</div>
          </div>
          <div class="empty-title">尚未生成学习路径</div>
          <div class="empty-desc">请在右侧填写信息，系统将为你规划专属学习路径</div>
        </div>

        <div v-else class="path-content">
          <div class="progress-overview">
            <div class="progress-ring">
              <svg viewBox="0 0 100 100">
                <circle cx="50" cy="50" r="42" fill="none" stroke="var(--color-border-light)" stroke-width="6"/>
                <circle cx="50" cy="50" r="42" fill="none" stroke="var(--color-primary)" stroke-width="6"
                  :stroke-dasharray="`${overallProgress * 2.64} 264`"
                  stroke-linecap="round"
                  transform="rotate(-90 50 50)"
                  style="transition: stroke-dasharray 0.6s ease"
                />
              </svg>
              <div class="progress-text">{{ overallProgress }}%</div>
            </div>
            <div class="progress-info">
              <div class="progress-title">总体进度</div>
              <div class="progress-sub">{{ learningPath.totalSteps || learningPath.steps?.length || 0 }} 个步骤</div>
            </div>
          </div>

          <div class="phases-timeline">
            <div
              v-for="(step, pIdx) in learningPath.steps"
              :key="pIdx"
              class="phase-card"
              :class="{ expanded: expandedSteps.has(pIdx), [normalizeStatus(step.status)]: true }"
            >
              <div class="phase-header" @click="toggleStep(pIdx)">
                <div class="phase-marker">
                  <div class="marker-dot"></div>
                  <div v-if="pIdx < learningPath.steps.length - 1" class="marker-line"></div>
                </div>
                <div class="phase-info">
                  <div class="phase-name">{{ step.title }}</div>
                  <div class="phase-meta">
                    <span class="phase-duration">预计 {{ step.estimatedHours || '—' }} 小时</span>
                    <span class="phase-status-badge" :class="normalizeStatus(step.status)">
                      {{ normalizeStatus(step.status) === 'completed' ? '已完成' : normalizeStatus(step.status) === 'in_progress' ? '进行中' : '待开始' }}
                    </span>
                  </div>
                </div>
                <svg class="expand-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
                  :style="{ transform: expandedSteps.has(pIdx) ? 'rotate(180deg)' : 'rotate(0)' }">
                  <polyline points="6 9 12 15 18 9"/>
                </svg>
              </div>

              <transition name="expand">
                <div v-if="expandedSteps.has(pIdx)" class="phase-tasks">
                  <div
                    :key="step.stepId"
                    class="task-item"
                    :class="{ completed: step.status === 'completed' }"
                    @click="toggleTaskStatus(step)"
                  >
                    <div class="task-check">
                      <span v-if="step.status === 'completed'">✓</span>
                      <span v-else>{{ getStatusIcon(normalizeStatus(step.status)) }}</span>
                    </div>
                    <div class="task-content">
                      <div class="task-name">{{ step.title }}</div>
                      <div v-if="step.description" class="task-desc">{{ step.description }}</div>
                      <div v-if="step.knowledgePoints" class="task-resources">
                        <span v-for="point in step.knowledgePoints.split(/[、,，]/).filter(Boolean)" :key="point" class="task-resource-tag">{{ point }}</span>
                      </div>
                      <div v-if="step.resources?.length" class="task-resources">
                        <span v-for="resource in step.resources" :key="resource.resourceId" class="task-resource-tag">{{ resource.title }}</span>
                      </div>
                    </div>
                  </div>
                </div>
              </transition>
            </div>
          </div>
        </div>
      </div>

      <div class="path-sidebar">
        <div class="sidebar-card">
          <div class="card-title">生成学习路径</div>
          <div class="card-body">
            <div class="form-field">
              <label>课程名称 <span class="hint">可选</span></label>
              <input v-model="courseName" placeholder="如：脑卒中诊疗" />
            </div>
            <div class="form-field">
              <label>学习目标</label>
              <textarea v-model="customGoal" placeholder="描述你的学习目标，如：\n系统掌握脑卒中诊疗核心知识\n重点突破缺血性脑卒中溶栓治疗" rows="4"></textarea>
            </div>
            <button class="gen-btn" :disabled="isGenerating" @click="handleGenerate">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
              </svg>
              {{ isGenerating ? '生成中...' : '规划路径' }}
            </button>
          </div>
        </div>

        <ReasoningTrace :entries="reasoningEntries" :running="isGenerating" />

        <div v-if="generatedContent" class="sidebar-card ai-advice-card">
          <div class="card-title">AI 建议</div>
          <div class="card-body">
            <div class="markdown-body compact" v-html="renderMarkdown(generatedContent)"></div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.learning-path-page {
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

.path-body {
  flex: 1;
  display: flex;
  min-height: 0;
  overflow: hidden;
}

.path-main {
  flex: 1;
  overflow-y: auto;
  padding: 24px 28px;
  min-width: 0;
}

.path-loading, .path-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 12px;
  color: var(--color-text-weak);
}

.loading-spinner {
  width: 32px; height: 32px;
  border: 3px solid var(--color-border-light);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }

.empty-visual { position: relative; }
.empty-icon { font-size: 4rem; line-height: 1; }
.empty-title { font-size: 16px; font-weight: 700; color: var(--color-text-medium); }
.empty-desc { font-size: 13px; text-align: center; line-height: 1.6; max-width: 300px; }

.path-content {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.progress-overview {
  display: flex;
  align-items: center;
  gap: 20px;
  padding: 20px 24px;
  background: var(--color-bg-light);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-xl);
}

.progress-ring {
  position: relative;
  width: 80px;
  height: 80px;
  flex-shrink: 0;

  svg { width: 100%; height: 100%; }
}

.progress-text {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.2rem;
  font-weight: 800;
  color: var(--color-primary-dark);
}

.progress-info { display: flex; flex-direction: column; gap: 2px; }
.progress-title { font-size: 16px; font-weight: 700; color: var(--color-text-strong); }
.progress-sub { font-size: 13px; color: var(--color-text-medium); }

.phases-timeline {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.phase-card {
  position: relative;
}

.phase-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  cursor: pointer;
  border-radius: var(--radius-lg);
  transition: background var(--transition-fast);

  &:hover { background: var(--color-hover-bg); }
}

.phase-marker {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 20px;
  flex-shrink: 0;
}

.marker-dot {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  border: 3px solid var(--color-border);
  background: var(--color-bg-base);
  transition: all var(--transition-fast);

  .completed & { background: var(--color-primary); border-color: var(--color-primary); }
  animation: pulse-glow 2s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(17, 150, 127, 0.4); }
  50% { box-shadow: 0 0 0 6px rgba(17, 150, 127, 0); }
}

.marker-line {
  width: 2px;
  height: 24px;
  background: var(--color-border-light);
  margin-top: 4px;
}

.phase-info { flex: 1; min-width: 0; }

.phase-name {
  font-size: 15px;
  font-weight: 700;
  color: var(--color-text-strong);
}

.phase-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 3px;
  font-size: 12px;
  color: var(--color-text-weak);
}

.phase-status-badge {
  padding: 1px 8px;
  border-radius: var(--radius-pill);
  font-size: 11px;
  font-weight: 700;

  &.completed { background: rgba(17, 150, 127, 0.1); color: var(--color-primary-dark); }
  &.in_progress { background: rgba(59, 130, 246, 0.1); color: #3b82f6; }
  &.pending { background: var(--color-border-light); color: var(--color-text-weak); }
}

.expand-icon {
  flex-shrink: 0;
  color: var(--color-text-weak);
  transition: transform 0.2s ease;
}

.phase-tasks {
  padding: 0 16px 12px 48px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.task-item {
  display: flex;
  gap: 10px;
  padding: 10px 14px;
  border-radius: var(--radius-md);
  background: var(--color-bg-base);
  border: 1px solid var(--color-border-light);
  cursor: pointer;
  transition: all var(--transition-fast);

  &:hover { border-color: rgba(17, 150, 127, 0.3); box-shadow: var(--glow-primary); transform: translateX(4px); }

  &.completed {
    opacity: 0.7;
    .task-name { text-decoration: line-through; }
  }
}

.task-check {
  flex-shrink: 0;
  width: 22px;
  height: 22px;
  border-radius: 6px;
  border: 2px solid var(--color-border);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  color: var(--color-primary);
  transition: all var(--transition-fast);

  .completed & { background: var(--color-primary); border-color: var(--color-primary); color: #fff; }
}

.task-content { flex: 1; min-width: 0; }

.task-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-strong);
}

.task-desc {
  font-size: 12px;
  color: var(--color-text-medium);
  margin-top: 2px;
  line-height: 1.5;
}

.task-resources {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 6px;
}

.task-resource-tag {
  padding: 1px 8px;
  border-radius: var(--radius-pill);
  font-size: 10px;
  font-weight: 600;
  background: rgba(59, 130, 246, 0.1);
  color: #3b82f6;
}

.path-sidebar {
  width: 340px;
  min-width: 340px;
  border-left: 1px solid var(--color-border-light);
  background: var(--color-bg-light);
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.sidebar-card {
  background: var(--color-bg-base);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-xl);
  overflow: hidden;
  flex-shrink: 0;
}

.ai-advice-card {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;

  .card-body {
    flex: 1;
    overflow-y: auto;
    min-height: 0;
  }
}

.card-title {
  padding: 14px 18px;
  font-size: 14px;
  font-weight: 700;
  color: var(--color-text-strong);
  border-bottom: 1px solid var(--color-border-light);
}

.card-body {
  padding: 16px 18px;
  display: flex;
  flex-direction: column;
  gap: 14px;
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

    &::placeholder { color: var(--color-text-weak); }
    &:focus {
      outline: none;
      border-color: var(--color-primary);
      box-shadow: 0 0 0 3px rgba(17, 150, 127, 0.15), var(--glow-primary);
    }
  }

  textarea { resize: vertical; min-height: 80px; }
}

.gen-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 12px 20px;
  border: none;
  border-radius: var(--radius-lg);
  background: var(--color-primary-gradient);
  color: #fff;
  font: inherit;
  font-size: 14px;
  font-weight: 700;
  cursor: pointer;
  transition: all var(--transition-fast);

  &:hover:not(:disabled) { opacity: 0.88; transform: translateY(-1px); }
  &:disabled { opacity: 0.5; cursor: not-allowed; }
}

.expand-enter-active, .expand-leave-active {
  transition: all 0.25s ease;
  overflow: hidden;
}

.expand-enter-from, .expand-leave-to {
  opacity: 0;
  max-height: 0;
}

@media (max-width: 1024px) {
  .path-sidebar { width: 300px; min-width: 300px; }
}

@media (max-width: 768px) {
  .path-body { flex-direction: column; }
  .path-sidebar { width: 100%; min-width: 100%; border-left: none; border-top: 1px solid var(--color-border-light); max-height: 40vh; }
}

.task-item { animation: fade-in-up 0.3s cubic-bezier(0.16, 1, 0.3, 1) both; }
.phase-row { animation: fade-in-up 0.4s cubic-bezier(0.16, 1, 0.3, 1) both; }
</style>
