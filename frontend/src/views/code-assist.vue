<script setup>
import { ref, computed, nextTick, onMounted, onActivated, onDeactivated, onBeforeUnmount } from 'vue'
import { renderMarkdown } from '@/utils/markdown'
import { executeCodeAPI, codeAssistStreamAPI } from '@/api/code'
import ReasoningTrace from '@/components/ReasoningTrace.vue'
import ThinkingIndicator from '@/components/ThinkingIndicator.vue'
import BackToLatest from '@/components/BackToLatest.vue'
import { useReasoningTrace } from '@/composables/useReasoningTrace'
import { useAutoScroll } from '@/composables/useAutoScroll'

const assistTypes = [
  { value: 'complete', label: '代码补全', icon: '✍️', detail: '补齐缺失实现，保持现有结构', placeholder: '描述需要补全的函数、流程或预期结果' },
  { value: 'diagnose', label: '错误诊断', icon: '🔍', detail: '定位报错根因并给出修复', placeholder: '补充复现步骤、期望结果或报错现象' },
  { value: 'optimize', label: '优化建议', icon: '⚡', detail: '保持行为不变并改进代码质量', placeholder: '说明要重点优化性能、可读性还是健壮性' },
  { value: 'explain', label: '代码讲解', icon: '📖', detail: '梳理结构、流程与关键语句', placeholder: '填写希望重点讲解的代码片段或概念' },
]

const assistType = ref('')
const code = ref('')
const prompt = ref('')
const stdinData = ref('')
const talkId = ref(null)

const isRunning = ref(false)
const runResult = ref(null)
const runError = ref('')

const isAssisting = ref(false)
const isThinking = ref(false)
const thinkingHint = ref('')
const assistContent = ref('')
const assistError = ref('')

const resultPaneRef = ref(null)
const { showBackToLatest, unread, onScroll, scrollToLatest, notifyNewContent, reset } = useAutoScroll(resultPaneRef)
const inlineError = ref('')
const { reasoningEntries, resetReasoningTrace, appendReasoningEvent } = useReasoningTrace()

let assistSafetyTimer = null
let assistAbortController = null

const selectedAssist = computed(() => assistTypes.find(type => type.value === assistType.value) || null)

function selectAssistType(type) {
  if (assistType.value === type) return
  if (isAssisting.value) cancelAssist()
  else resetAssistState()
  assistType.value = type
  // 不同功能不共享历史，防止上一种功能影响当前结果。
  talkId.value = null
}

/** 重置所有 AI 辅助相关状态 */
function resetAssistState() {
  isAssisting.value = false
  isThinking.value = false
  thinkingHint.value = ''
  assistContent.value = ''
  assistError.value = ''
  inlineError.value = ''
  reset()
  resetReasoningTrace()
}

/** 取消当前 AI 请求 */
function cancelAssist() {
  clearSafetyTimer()
  if (assistAbortController) {
    assistAbortController.abort()
    assistAbortController = null
  }
  resetAssistState()
}

/** 清除安全超时定时器 */
function clearSafetyTimer() {
  if (assistSafetyTimer) {
    clearTimeout(assistSafetyTimer)
    assistSafetyTimer = null
  }
}

/** 设置安全超时（60 秒），防止 isAssisting 状态永久卡死 */
function startSafetyTimer() {
  clearSafetyTimer()
  assistSafetyTimer = setTimeout(() => {
    console.warn('[code-assist] 安全超时触发，强制重置状态')
    cancelAssist()
    assistError.value = 'AI 请求超时，请检查后端模型服务是否正常运行'
    inlineError.value = assistError.value
  }, 60000)
}

onMounted(() => {
  const el = resultPaneRef.value
  if (el) el.addEventListener('scroll', onScroll, { passive: true })
})

onActivated(() => {
  const el = resultPaneRef.value
  if (el) el.addEventListener('scroll', onScroll, { passive: true })
})

onDeactivated(() => {
  cancelAssist()
})

onBeforeUnmount(() => {
  clearSafetyTimer()
  const el = resultPaneRef.value
  if (el) el.removeEventListener('scroll', onScroll)
  cancelAssist()
})

async function runCode() {
  if (!code.value.trim() || isRunning.value) return
  isRunning.value = true
  runResult.value = null
  runError.value = ''
  try {
    const res = await executeCodeAPI({
      code: code.value,
      language: 'python',
      timeout: 30,
      inputData: stdinData.value || null,
    })
    runResult.value = res.data
  } catch (e) {
    runError.value = e.message || '代码执行失败'
  } finally {
    isRunning.value = false
  }
}

async function requestAssist() {
  console.log('[code-assist] requestAssist 触发, isAssisting=', isAssisting.value)

  if (isAssisting.value) {
    console.log('[code-assist] 检测到正在进行的请求，取消并重试')
    cancelAssist()
    await nextTick()
  }

  if (!assistType.value) {
    assistError.value = '请先选择一种代码辅助功能'
    inlineError.value = assistError.value
    return
  }

  if (!code.value.trim() && !prompt.value.trim()) {
    assistError.value = '请先输入代码或描述你的诉求'
    inlineError.value = assistError.value
    console.warn('[code-assist] 输入为空，拒绝请求')
    return
  }

  isAssisting.value = true
  isThinking.value = true
  thinkingHint.value = `AI 正在执行${selectedAssist.value?.label || '代码辅助'}...`
  assistContent.value = ''
  assistError.value = ''
  inlineError.value = ''
  reset()
  resetReasoningTrace()

  assistAbortController = new AbortController()
  startSafetyTimer()

  await nextTick()

  try {
    console.log('[code-assist] 开始 SSE 请求: assistType=', assistType.value, 'promptLen=', prompt.value.length, 'codeLen=', code.value.length)
    const result = await codeAssistStreamAPI(
      {
        talkId: talkId.value,
        assistType: assistType.value,
        prompt: prompt.value,
        language: 'python',
        existingCode: code.value,
        errorMessage: runResult.value && !runResult.value.success ? runResult.value.stderr : null,
      },
      (chunk, event = {}) => {
        if (isThinking.value) isThinking.value = false
        if (chunk != null && chunk !== '') {
          assistContent.value = event.replace ? chunk : assistContent.value + chunk
          nextTick(() => notifyNewContent())
        }
      },
      (thinking) => {
        thinkingHint.value = thinking.title || `AI 正在执行${selectedAssist.value?.label || '代码辅助'}...`
        appendReasoningEvent(thinking)
      },
      (error) => {
        console.error('[code-assist] SSE 收到错误事件:', error)
        assistError.value = error
        inlineError.value = error
      },
      { signal: assistAbortController.signal },
    )
    console.log('[code-assist] SSE 请求完成: talkId=', result.data?.talkId, 'contentLen=', result.data?.content?.length || 0)
    if (result.data?.talkId) talkId.value = result.data.talkId

    // 以 SSE 累积出的最终内容收口，避免打字缓冲或完整报告替换产生时序差异。
    if (result.data?.content) {
      assistContent.value = result.data.content
      isThinking.value = false
    }

    if (!assistContent.value && !assistError.value) {
      assistError.value = 'AI 未返回有效内容，请检查模型服务日志或稍后重试'
      inlineError.value = assistError.value
    }
  } catch (e) {
    console.error('[code-assist] SSE 请求失败:', e.message)
    if (e.message === '请求被取消') {
      console.log('[code-assist] 请求已被用户取消')
      return
    }
    const msg = e.message || 'AI 辅助失败，请稍后重试'
    assistError.value = msg
    inlineError.value = msg
  } finally {
    clearSafetyTimer()
    isAssisting.value = false
    isThinking.value = false
    assistAbortController = null
  }
}
</script>

<template>
  <div class="code-page">
    <div class="page-header">
      <div class="header-content">
        <h1>代码辅助</h1>
        <p>医学数据分析编程助手 · 补全 / 诊断 / 优化 / 沙箱运行</p>
      </div>
      <div class="header-badge">代码辅助开发</div>
    </div>

    <div class="code-body">
      <div class="editor-column">
        <div class="panel">
          <div class="panel-title">
            <span>Python 代码</span>
            <div class="type-chips" aria-label="代码辅助功能">
              <button
                v-for="t in assistTypes"
                :key="t.value"
                class="type-chip"
                :class="{ active: assistType === t.value }"
                :aria-pressed="assistType === t.value"
                @click="selectAssistType(t.value)"
              >
                <span class="type-icon">{{ t.icon }}</span>
                <span class="type-copy">
                  <strong>{{ t.label }}</strong>
                  <small>{{ t.detail }}</small>
                </span>
              </button>
            </div>
          </div>
          <textarea
            v-model="code"
            class="code-editor"
            spellcheck="false"
            placeholder="# 在此输入或粘贴 Python 代码，例如：
import pandas as pd
df = pd.DataFrame({'NIHSS评分': [4, 12, 20], '预后': ['良好', '中等', '差']})
print(df.describe())"
          ></textarea>
        </div>
        <div class="prompt-bar">
          <input
            v-model="prompt"
            class="prompt-input"
            :placeholder="selectedAssist?.placeholder || '请先选择上方的一种代码辅助功能'"
            :disabled="!assistType"
          />
          <input
            v-model="stdinData"
            class="prompt-input"
            placeholder="标准输入（可选，程序 input() 读取的内容）"
          />
          <div class="action-row">
            <button class="btn run-btn" :disabled="isRunning || !code.trim()" @click="runCode">
              {{ isRunning ? '运行中...' : '▶ 运行代码' }}
            </button>
            <button class="btn assist-btn" :disabled="isAssisting || !assistType" @click="requestAssist">
              {{ isAssisting ? `${selectedAssist?.label || 'AI 辅助'}中...` : (selectedAssist ? `执行${selectedAssist.label}` : '请选择辅助功能') }}
            </button>
          </div>
        </div>
      </div>

      <div class="result-column panel">
        <div class="panel-title">
          <span>运行结果</span>
          <span class="run-meta" v-if="runResult">
            退出码 {{ runResult.exitCode }} · 耗时 {{ runResult.executionTime }}s
          </span>
        </div>
        <div class="output-body">
          <div v-if="runError" class="output-error">{{ runError }}</div>
          <template v-else-if="runResult">
            <pre v-if="runResult.stdout" class="output-stdout">{{ runResult.stdout }}</pre>
            <pre v-if="runResult.stderr" class="output-stderr">{{ runResult.stderr }}</pre>
            <div v-if="runResult.error" class="output-error">{{ runResult.error }}</div>
            <div v-if="!runResult.stdout && !runResult.stderr && !runResult.error" class="output-empty">
              程序执行完成，无输出
            </div>
          </template>
          <div v-else class="output-empty">点击「▶ 运行代码」在沙箱中执行</div>
        </div>
      </div>

      <div class="assist-column panel">
        <div class="panel-title">
          <span>{{ selectedAssist ? `${selectedAssist.label}结果` : 'AI 辅助结果' }}</span>
        </div>
        <div class="assist-pane" ref="resultPaneRef" @scroll="onScroll">
          <div v-if="isThinking" class="thinking-hint">
            <ThinkingIndicator :hint="thinkingHint" />
          </div>
          <ReasoningTrace :entries="reasoningEntries" :running="isAssisting" />
          <div v-if="assistError" class="output-error">{{ assistError }}</div>
          <div
            v-if="assistContent"
            class="markdown-body"
            v-html="renderMarkdown(assistContent)"
          ></div>
          <div v-if="!assistContent && !isThinking && !assistError" class="output-empty">
            选择一种辅助功能后，结果将在此流式呈现
          </div>
        </div>
        <BackToLatest :unread="unread" @click="scrollToLatest({ smooth: true })" />
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.code-page {
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

  h1 { margin: 0; font-size: 1.5rem; font-weight: 800; color: var(--color-text-strong); letter-spacing: -0.02em; }
  p { margin: 4px 0 0; font-size: 13px; color: var(--color-text-medium); }
}

.header-badge {
  padding: 6px 14px;
  border-radius: var(--radius-pill);
  background: var(--color-secondary-bg);
  font-size: 12px;
  font-weight: 700;
  color: var(--color-primary-dark);
}

.code-body {
  flex: 1;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 16px;
  padding: 16px 28px 20px;
  min-height: 0;
}

.editor-column {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-height: 0;
}

.panel {
  display: flex;
  flex-direction: column;
  min-height: 0;
  border: 1px solid var(--color-border-light);
  border-radius: 14px;
  background: var(--color-message-bg, transparent);
  overflow: hidden;
}

.panel-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 10px 14px;
  font-size: 13px;
  font-weight: 700;
  color: var(--color-text-strong);
  border-bottom: 1px solid var(--color-border-light);
  flex-shrink: 0;
}

.run-meta { font-size: 12px; font-weight: 500; color: var(--color-text-weak); }

.editor-column .panel-title {
  align-items: stretch;
  flex-direction: column;
}

.type-chips {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px;
}

.type-chip {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 48px;
  padding: 7px 9px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--color-text-medium);
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition: all 0.15s;

  &.active {
    border-color: var(--color-primary-dark);
    color: var(--color-primary-dark);
    background: var(--color-secondary-bg);
    font-weight: 700;
  }
}

.type-icon {
  flex-shrink: 0;
  font-size: 16px;
}

.type-copy {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;

  strong {
    font-size: 12px;
    line-height: 1.2;
  }

  small {
    color: var(--color-text-weak);
    font-size: 10px;
    font-weight: 500;
    line-height: 1.3;
  }
}

.code-editor {
  flex: 1;
  min-height: 180px;
  padding: 12px 14px;
  border: none;
  outline: none;
  resize: none;
  background: transparent;
  color: var(--color-text-strong);
  font-family: 'SF Mono', Menlo, Consolas, monospace;
  font-size: 13.5px;
  line-height: 1.6;
  tab-size: 4;
}

.prompt-bar {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.prompt-input {
  padding: 10px 12px;
  border: 1px solid var(--color-border);
  border-radius: 10px;
  background: var(--color-message-bg, transparent);
  color: var(--color-text-strong);
  font-size: 13px;
  outline: none;
  transition: border-color 0.15s;

  &:focus { border-color: var(--color-primary-dark); }
}

.action-row { display: flex; gap: 10px; }

.btn {
  padding: 9px 20px;
  border: none;
  border-radius: 10px;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  transition: opacity 0.15s, background 0.15s;

  &:disabled { opacity: 0.45; cursor: not-allowed; }
}

.run-btn { background: var(--color-primary-dark); color: #fff; }
.assist-btn { background: var(--color-secondary-bg); color: var(--color-primary-dark); }

.result-column { min-height: 0; }

.output-body {
  flex: 1;
  overflow-y: auto;
  padding: 12px 14px;
  min-height: 0;
}

.output-stdout,
.output-stderr {
  margin: 0;
  padding: 10px 12px;
  border-radius: 10px;
  font-family: 'SF Mono', Menlo, Consolas, monospace;
  font-size: 12.5px;
  white-space: pre-wrap;
  word-break: break-word;
}

.output-stdout { background: var(--color-secondary-bg); color: var(--color-text-strong); }
.output-stderr { background: #fef2f2; color: #dc2626; }

.output-error {
  padding: 10px 12px;
  border-radius: 10px;
  background: #fef2f2;
  color: #dc2626;
  font-size: 13px;
  font-weight: 600;
}

.output-empty {
  font-size: 13px;
  color: var(--color-text-weak);
  text-align: center;
  padding: 24px 0;
}

.assist-column { min-height: 0; position: relative; }

.assist-pane {
  flex: 1;
  overflow-y: auto;
  padding: 14px 16px;
  min-height: 0;
}

.thinking-hint {
  display: flex;
  align-items: center;
  padding-bottom: 10px;
}

.markdown-body {
  font-size: 14px;
  line-height: 1.7;
  color: var(--color-text-strong);

  :deep(pre) {
    padding: 12px 14px;
    border-radius: 10px;
    background: var(--color-secondary-bg);
    overflow-x: auto;
    font-size: 12.5px;
  }

  :deep(code) { font-family: 'SF Mono', Menlo, Consolas, monospace; }
}

@media (max-width: 960px) {
  .code-body { grid-template-columns: 1fr; overflow-y: auto; }
  .assist-column { min-height: 320px; }
}
</style>

<!-- 非 scoped 样式：确保 v-html 渲染的 Markdown 代码块可见 -->
<style lang="scss">
.assist-pane .markdown-body {
  font-size: 14px;
  line-height: 1.75;
  color: #1e293b;
  word-break: break-word;
}
.assist-pane .markdown-body h2 { font-size: 1.1rem; font-weight: 700; margin: 16px 0 8px; color: #0f172a; }
.assist-pane .markdown-body h3 { font-size: 1rem; font-weight: 700; margin: 12px 0 6px; color: #1e293b; }
.assist-pane .markdown-body p { margin: 6px 0; }
.assist-pane .markdown-body ul, .assist-pane .markdown-body ol { padding-left: 20px; margin: 6px 0; }
.assist-pane .markdown-body li { margin: 3px 0; }
.assist-pane .markdown-body strong { font-weight: 700; }
.assist-pane .markdown-body pre {
  background: #f1f5f9;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 14px 16px;
  overflow-x: auto;
  margin: 10px 0;
}
.assist-pane .markdown-body pre code {
  font-family: 'SF Mono', Menlo, Consolas, 'Courier New', monospace;
  font-size: 13px;
  line-height: 1.6;
  color: #0f172a;
  white-space: pre;
  background: transparent;
  padding: 0;
}
.assist-pane .markdown-body code {
  font-family: 'SF Mono', Menlo, Consolas, 'Courier New', monospace;
  font-size: 13px;
  background: #f1f5f9;
  padding: 2px 6px;
  border-radius: 4px;
  color: #c7254e;
}
.assist-pane .markdown-body pre code {
  color: #0f172a;
  background: transparent;
  padding: 0;
  border-radius: 0;
}
</style>
