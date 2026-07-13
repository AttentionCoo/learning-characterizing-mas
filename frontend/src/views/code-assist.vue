<script setup>
import { ref, nextTick, onMounted, onActivated, onDeactivated, onBeforeUnmount } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import { executeCodeAPI, codeAssistStreamAPI } from '@/api/code'

marked.setOptions({ gfm: true, breaks: true })

const assistTypes = [
  { value: 'complete', label: '代码补全', icon: '✍️' },
  { value: 'diagnose', label: '错误诊断', icon: '🔍' },
  { value: 'optimize', label: '优化建议', icon: '⚡' },
  { value: 'explain', label: '代码讲解', icon: '📖' },
]

const assistType = ref('complete')
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
const userScrolled = ref(false)
const inlineError = ref('')

/** 当前 SSE 请求的 AbortController，用于主动取消 */
let assistAbortController = null
/** 安全超时计时器 */
let assistSafetyTimer = null

/** 重置所有 AI 辅助相关状态 */
function resetAssistState() {
  isAssisting.value = false
  isThinking.value = false
  thinkingHint.value = ''
  assistContent.value = ''
  assistError.value = ''
  inlineError.value = ''
  userScrolled.value = false
}

/** 取消正在进行的 AI 辅助请求 */
function cancelAssist() {
  if (assistSafetyTimer) {
    clearTimeout(assistSafetyTimer)
    assistSafetyTimer = null
  }
  if (assistAbortController) {
    assistAbortController.abort()
    assistAbortController = null
  }
  resetAssistState()
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

/** 清除安全超时计时器 */
function clearSafetyTimer() {
  if (assistSafetyTimer) {
    clearTimeout(assistSafetyTimer)
    assistSafetyTimer = null
  }
}

// ── 生命周期管理：确保组件在任意生命周期阶段都能正确清理状态 ──

/** 首次挂载时初始化 clean 状态 */
onMounted(() => {
  resetAssistState()
})

/** keep-alive 激活时重置状态 */
onActivated(() => {
  resetAssistState()
})

/** keep-alive 失活时取消请求并清理 */
onDeactivated(() => {
  cancelAssist()
})

/** 组件销毁时取消请求并清理 */
onBeforeUnmount(() => {
  cancelAssist()
})

function onPaneScroll() {
  const el = resultPaneRef.value
  if (!el) return
  userScrolled.value = el.scrollHeight - el.scrollTop - el.clientHeight > 80
}

function scrollToBottom() {
  const el = resultPaneRef.value
  if (!el || userScrolled.value) return
  el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
}

function renderMarkdown(text) {
  if (!text) return ''
  try {
    return DOMPurify.sanitize(marked.parse(text))
  } catch (e) {
    console.error('[code-assist] Markdown 渲染失败:', e)
    return '<pre style="white-space:pre-wrap;word-break:break-word">' +
      text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;') +
      '</pre>'
  }
}

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
    runError.value = e.msg || e.message || '代码执行失败，请稍后重试'
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

  if (!code.value.trim() && !prompt.value.trim()) {
    assistError.value = '请先输入代码或描述你的诉求'
    inlineError.value = assistError.value
    console.warn('[code-assist] 输入为空，拒绝请求')
    return
  }

  isAssisting.value = true
  isThinking.value = true
  thinkingHint.value = 'AI 正在分析代码...'
  assistContent.value = ''
  assistError.value = ''
  inlineError.value = ''
  userScrolled.value = false

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
      (chunk) => {
        if (isThinking.value) isThinking.value = false
        if (chunk != null && chunk !== '') {
          assistContent.value += chunk
          nextTick(scrollToBottom)
        }
      },
      (thinking) => {
        thinkingHint.value = thinking.title || 'AI 正在分析代码...'
      },
      { signal: assistAbortController.signal },
    )
    console.log('[code-assist] SSE 请求完成: talkId=', result.data?.talkId)
    if (result.data?.talkId) talkId.value = result.data.talkId
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
            <div class="type-chips">
              <button
                v-for="t in assistTypes"
                :key="t.value"
                class="type-chip"
                :class="{ active: assistType === t.value }"
                @click="assistType = t.value"
              >
                {{ t.icon }} {{ t.label }}
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
          <input
            v-model="prompt"
            class="prompt-input"
            placeholder="描述你的诉求（如：帮我补全缺失值处理逻辑）"
            @keyup.enter="requestAssist"
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
            <button class="btn assist-btn" :disabled="isAssisting" @click="requestAssist">
              {{ isAssisting ? 'AI 分析中...' : '✨ AI 辅助' }}
            </button>
          </div>
          <transition name="fade-inline-error">
            <p v-if="inlineError" class="inline-error">{{ inlineError }}</p>
          </transition>
        </div>

        <div class="panel output-panel">
          <div class="panel-title"><span>运行结果</span>
            <span v-if="runResult" class="run-meta">
              退出码 {{ runResult.exitCode }} · 耗时 {{ runResult.executionTime }}s
              <span v-if="runResult.truncated"> · 输出已截断</span>
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
      </div>

      <div class="assist-column panel">
        <div class="panel-title"><span>AI 辅助结果</span></div>
        <div class="assist-pane" ref="resultPaneRef" @scroll="onPaneScroll">
          <div v-if="isThinking" class="thinking-hint">
            <span class="thinking-dot"></span>{{ thinkingHint }}
          </div>
          <div v-if="assistError" class="output-error">{{ assistError }}</div>
          <div
            v-if="assistContent"
            class="markdown-body"
            v-html="renderMarkdown(assistContent)"
          ></div>
          <div v-if="!assistContent && !isThinking && !assistError" class="output-empty">
            选择辅助类型并点击「✨ AI 辅助」，结果将在此流式呈现
          </div>
        </div>
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

.type-chips { display: flex; gap: 6px; flex-wrap: wrap; }

.type-chip {
  padding: 4px 10px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-pill);
  background: transparent;
  color: var(--color-text-medium);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;

  &.active {
    border-color: var(--color-primary-dark);
    color: var(--color-primary-dark);
    background: var(--color-secondary-bg);
    font-weight: 700;
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
  font-size: 13px;
  line-height: 1.6;
}

.prompt-input {
  margin: 0 12px 10px;
  padding: 8px 12px;
  border: 1px solid var(--color-border);
  border-radius: 10px;
  background: transparent;
  color: var(--color-text-strong);
  font-size: 13px;
  outline: none;

  &:focus { border-color: var(--color-primary-dark); }
}

.action-row {
  display: flex;
  gap: 10px;
  padding: 0 12px 12px;
  flex-shrink: 0;
}

.btn {
  flex: 1;
  padding: 9px 0;
  border: none;
  border-radius: 10px;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  transition: opacity 0.15s;

  &:disabled { opacity: 0.5; cursor: not-allowed; }
}

.run-btn { background: var(--color-secondary-bg); color: var(--color-primary-dark); }
.assist-btn { background: linear-gradient(135deg, #6366f1, #11967f); color: #fff; }

.inline-error {
  margin: 6px 12px 0;
  padding: 8px 12px;
  border-radius: 8px;
  background: rgba(239, 68, 68, 0.1);
  color: #dc2626;
  font-size: 12.5px;
  font-weight: 500;
  line-height: 1.4;
}

.fade-inline-error-enter-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}
.fade-inline-error-leave-active {
  transition: opacity 0.15s ease;
}
.fade-inline-error-enter-from {
  opacity: 0;
  transform: translateY(-6px);
}
.fade-inline-error-leave-to {
  opacity: 0;
}

.output-panel { flex: 1; min-height: 120px; }

.output-body {
  flex: 1;
  overflow-y: auto;
  padding: 10px 14px;
  min-height: 0;
}

.output-stdout, .output-stderr {
  margin: 0 0 8px;
  padding: 10px 12px;
  border-radius: 10px;
  font-family: 'SF Mono', Menlo, Consolas, monospace;
  font-size: 12.5px;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-word;
}

.output-stdout {
  background: var(--color-secondary-bg);
  color: var(--color-text-strong);
}

.output-stderr {
  background: rgba(239, 68, 68, 0.08);
  color: #dc2626;
}

.output-error { padding: 8px 0; font-size: 13px; color: #dc2626; }
.output-empty { padding: 14px 0; font-size: 13px; color: var(--color-text-weak); text-align: center; }

.assist-column { min-height: 0; }

.assist-pane {
  flex: 1;
  overflow-y: auto;
  padding: 14px 16px;
  min-height: 0;
}

.thinking-hint {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--color-text-medium);
  padding-bottom: 10px;
}

.thinking-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--color-primary-dark);
  animation: pulse 1.2s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 0.3; transform: scale(0.85); }
  50% { opacity: 1; transform: scale(1.1); }
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
