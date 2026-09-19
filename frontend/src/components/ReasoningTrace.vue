<script setup>
import { computed, nextTick, ref, watch } from 'vue'

const props = defineProps({
  entries: { type: Array, default: () => [] },
  running: { type: Boolean, default: false },
})

/* ── 统计（头部摘要用）────────────────────────────────────────── */
const stats = computed(() => {
  let sources = 0
  let experts = 0
  let debateRounds = 0
  let skippedDebate = false
  for (const e of props.entries) {
    sources += e.sources?.length || 0
    if (e.experts?.active?.length) experts = Math.max(experts, e.experts.active.length)
    if (e.debate?.skipped) skippedDebate = true
    if (e.debate?.rounds) debateRounds = Math.max(debateRounds, e.debate.rounds)
    if (e.experts?.debateRounds) debateRounds = Math.max(debateRounds, e.experts.debateRounds)
  }
  return { sources, experts, debateRounds, skippedDebate }
})

/* ── 推理窗自动跟随：用户滚离底部时暂停贴底，滚回底部自动恢复 ── */
const traceBodyRef = ref(null)
const followTrace = ref(true)
const TRACE_FOLLOW_THRESHOLD = 40
let wheelTimer = null
let wheelActive = false

function onTraceScroll() {
  const el = traceBodyRef.value
  if (!el) return
  const dist = el.scrollHeight - el.scrollTop - el.clientHeight
  followTrace.value = dist < TRACE_FOLLOW_THRESHOLD
}

// 用户主动滚动推理窗（离开底部）时暂停贴底，手势结束后自动恢复
function onTraceWheel(e) {
  const el = traceBodyRef.value
  if (!el) return
  const dist = el.scrollHeight - el.scrollTop - el.clientHeight
  // 已在底部且继续向下滚 = 保持跟随；其余手势 = 用户主动滚动
  if (dist < TRACE_FOLLOW_THRESHOLD && e.deltaY > 0) return
  wheelActive = true
  clearTimeout(wheelTimer)
  wheelTimer = setTimeout(() => { wheelActive = false }, 250)
}

/* 内容签名：逐 token 流式只改条目内部文本长度，entries.length 不变——
   自动跟随若只监听条目数，内容超过窗高后新 token 会滚出可视区。 */
const contentSignature = computed(() => props.entries.map((e) => {
  let n = (e.content || '').length + (e.verdictText || '').length
  if (e.experts?.advices) n += e.experts.advices.reduce((s, a) => s + ((a && a.content) || '').length, 0)
  if (e.debate?.history) n += e.debate.history.reduce((s, h) => s + ((h && h.content) || '').length, 0)
  if (e.messages) n += e.messages.reduce((s, m) => s + ((m && m.content) || '').length, 0)
  if (e.blackboard?.entries) n += e.blackboard.entries.reduce((s, b) => s + ((b && b.content) || '').length, 0)
  return n
}).join(':'))

watch(
  contentSignature,
  async () => {
    if (!props.running || !followTrace.value || wheelActive) return
    await nextTick()
    const element = traceBodyRef.value
    if (element) element.scrollTop = element.scrollHeight
  },
)

// 新一轮推理开始时重置跟随状态
watch(
  () => props.entries.length,
  (len) => {
    if (len === 0) {
      followTrace.value = true
      wheelActive = false
      clearTimeout(wheelTimer)
    }
  },
)

/* ── 长文折叠：证据摘录 / 专家发言默认收起，点击展开 ───────────
   阈值与 .clamped 的两行截断对应；只有确实会被截断的文本才加截断类并给出
   展开按钮，避免出现「被截断但没有展开入口」的静默丢失。 */
const CLAMP_LIMIT = 110
const needsClamp = (text) => (text || '').length > CLAMP_LIMIT

const expanded = ref({})
const isOpen = (key) => !!expanded.value[key]
function toggle(key) {
  expanded.value = { ...expanded.value, [key]: !expanded.value[key] }
}

/* ── 标签映射 ─────────────────────────────────────────────────── */
const PHASE_META = {
  start: { label: '开始', tone: 'slate' },
  progress: { label: '处理中', tone: 'primary' },
  experts: { label: '专家', tone: 'violet' },
  agent_msg: { label: '会诊', tone: 'blue' },
  blackboard: { label: '黑板', tone: 'amber' },
  debate: { label: '辩论', tone: 'rose' },
  done: { label: '完成', tone: 'green' },
  verdict: { label: '结论', tone: 'amber' },
}
function phaseLabel(phase) {
  return PHASE_META[phase]?.label || '处理中'
}
function phaseTone(phase) {
  return PHASE_META[phase]?.tone || 'primary'
}

const KIND_LABELS = {
  question: '提问',
  reply: '回复',
  revise: '修订',
  agree: '认同',
  object: '异议',
  finding: '发现',
}
function kindLabel(kind) {
  return KIND_LABELS[kind] || kind || '消息'
}

/* ── 专家头像：去掉「智能体」后缀取首字，按名字哈希取稳定主题色 ── */
function roleAvatar(role) {
  if (!role) return '专'
  const cleaned = String(role).replace(/智能体$/, '').trim()
  return cleaned ? cleaned.slice(0, 1) : '专'
}

const AVATAR_COLORS = [
  '#2563a8', '#0f9d7a', '#7c3aed', '#b45309',
  '#c0392b', '#0e7490', '#1e7d46', '#9333ea',
  '#d97706', '#0284c7', '#4d7c0f', '#be185d',
]
function roleColor(role) {
  if (!role) return AVATAR_COLORS[0]
  let hash = 0
  for (let i = 0; i < role.length; i += 1) {
    hash = (hash * 31 + role.charCodeAt(i)) >>> 0
  }
  return AVATAR_COLORS[hash % AVATAR_COLORS.length]
}

/* ── 内联 SVG 图标（统一 24 格线性风格，替代原先混用的 emoji）── */
const ICONS = {
  search: ['M11 3a8 8 0 1 0 0 16 8 8 0 0 0 0-16z', 'M21 21l-4.3-4.3'],
  evidence: ['M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z', 'M14 2v6h6', 'M16 13H8', 'M16 17H8'],
  users: ['M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2', 'M9 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8z', 'M23 21v-2a4 4 0 0 0-3-3.87', 'M16 3.13a4 4 0 0 1 0 7.75'],
  chat: ['M21 11.5a8.5 8.5 0 0 1-9.5 8.4 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7a8.4 8.4 0 0 1-.9-3.8A8.5 8.5 0 0 1 12.5 3h.5a8.5 8.5 0 0 1 8 8v.5z'],
  board: ['M3 3h7v7H3z', 'M14 3h7v7h-7z', 'M14 14h7v7h-7z', 'M3 14h7v7H3z'],
  scale: ['M12 3v18', 'M5 7h14', 'M8 6l-3.5 7h7z', 'M16 6l-3.5 7h7z'],
  compass: ['M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20z', 'M16.2 7.8l-2.1 6.3-6.3 2.1 2.1-6.3z'],
  check: ['M20 6L9 17l-5-5'],
  info: ['M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20z', 'M12 16v-4', 'M12 8h.01'],
  list: ['M8 6h13', 'M8 12h13', 'M8 18h13', 'M3 6h.01', 'M3 12h.01', 'M3 18h.01'],
  spark: ['M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z'],
}
function stepIcon(phase) {
  if (phase === 'experts') return 'users'
  if (phase === 'agent_msg') return 'chat'
  if (phase === 'blackboard') return 'board'
  if (phase === 'debate') return 'scale'
  if (phase === 'verdict') return 'compass'
  if (phase === 'done') return 'check'
  if (phase === 'start') return 'spark'
  return 'list'
}

/* ── 流式长文本区块（综合 / 收敛 / 仲裁）── */
const VERDICT_META = {
  synthesis: { label: '综合提案与风险批判', icon: 'spark', blk: '' },
  convergence: { label: '教学总监收敛结论', icon: 'compass', blk: 'blk-board' },
  arbitration: { label: '仲裁裁决', icon: 'scale', blk: 'blk-debate' },
}
function verdictMeta(kind) {
  return VERDICT_META[kind] || { label: '结论', icon: 'info', blk: '' }
}
</script>

<template>
  <details v-if="entries.length" class="trace" open>
    <summary class="trace-head">
      <span class="trace-badge" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">
          <path v-for="(d, i) in ICONS.spark" :key="i" :d="d" />
        </svg>
      </span>

      <span class="trace-heading">
        <span class="trace-title">AI 推理与检索依据</span>
        <span class="trace-meta">
          <span class="meta-item">{{ entries.length }} 个步骤</span>
          <span v-if="stats.sources" class="meta-item">· {{ stats.sources }} 条指南证据</span>
          <span v-if="stats.experts" class="meta-item">· {{ stats.experts }} 位专家</span>
          <span v-if="stats.debateRounds" class="meta-item">· 辩论 {{ stats.debateRounds }} 轮</span>
        </span>
      </span>

      <span class="trace-status" :class="{ active: running }">
        <span class="status-dot" aria-hidden="true"></span>
        {{ running ? '推理中' : '已完成' }}
      </span>

      <span class="trace-chevron" aria-hidden="true"></span>
    </summary>

    <div
      ref="traceBodyRef"
      class="trace-body"
      aria-live="polite"
      @scroll="onTraceScroll"
      @wheel="onTraceWheel"
    >
      <ol class="trace-list">
        <li
          v-for="entry in entries"
          :key="entry.key"
          class="trace-step"
          :class="`tone-${phaseTone(entry.phase)}`"
        >
          <div class="rail" aria-hidden="true">
            <span class="rail-dot">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">
                <path v-for="(d, i) in ICONS[stepIcon(entry.phase)]" :key="i" :d="d" />
              </svg>
            </span>
          </div>

          <div class="step-body">
            <div class="step-head">
              <span class="phase-chip">{{ phaseLabel(entry.phase) }}</span>
              <span class="step-title">{{ entry.title }}</span>
            </div>
            <p v-if="entry.content" class="step-text">{{ entry.content }}</p>

            <!-- 专家与选人理由 -->
            <div v-if="entry.experts && (entry.experts.active?.length || entry.experts.advices?.length)" class="blk blk-experts">
              <div class="blk-head">
                <span class="blk-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path v-for="(d, i) in ICONS.users" :key="i" :d="d" /></svg></span>
                <span class="blk-label">参与专家</span>
                <span class="blk-count">{{ entry.experts.active?.length || 0 }} 位</span>
                <span v-if="entry.experts.debateRounds" class="blk-tag">辩论 {{ entry.experts.debateRounds }} 轮</span>
              </div>
              <p v-if="entry.experts.selectionReason" class="blk-note">{{ entry.experts.selectionReason }}</p>
              <div v-if="entry.experts.active?.length" class="chips">
                <span
                  v-for="(name, index) in entry.experts.active"
                  :key="`${entry.key}-ex-${index}`"
                  class="chip"
                >
                  <span class="chip-dot" :style="{ background: roleColor(name) }"></span>{{ name }}
                </span>
              </div>
              <div
                v-for="(advice, index) in entry.experts.advices"
                :key="`${entry.key}-ad-${index}`"
                class="said"
              >
                <div class="said-head">
                  <span class="said-avatar" :style="{ background: roleColor(advice.role) }">{{ roleAvatar(advice.role) }}</span>
                  <span class="said-role">{{ advice.role }}</span>
                </div>
                <!-- 流式期间不裁剪、不弹展开按钮：这是最主要的流式通道，边生成边全文可见 -->
                <p class="said-text" :class="{ clamped: needsClamp(advice.content) && !advice.streaming && !isOpen(`${entry.key}-ad-${index}`) }">
                  {{ advice.content }}<span v-if="advice.streaming && running" class="stream-caret" aria-hidden="true"></span>
                </p>
                <button
                  v-if="needsClamp(advice.content) && !advice.streaming"
                  type="button"
                  class="more"
                  @click="toggle(`${entry.key}-ad-${index}`)"
                >{{ isOpen(`${entry.key}-ad-${index}`) ? '收起' : '展开全文' }}</button>
              </div>
            </div>

            <!-- 专家会诊对话（M2） -->
            <div v-if="entry.messages?.length" class="blk blk-dialogue">
              <div class="blk-head">
                <span class="blk-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path v-for="(d, i) in ICONS.chat" :key="i" :d="d" /></svg></span>
                <span class="blk-label">专家会诊对话</span>
                <span class="blk-count">{{ entry.messages.length }} 条</span>
              </div>
              <div class="stream">
                <div
                  v-for="(msg, index) in entry.messages"
                  :key="`${entry.key}-msg-${index}`"
                  class="msg"
                  :class="`kind-${msg.kind || 'msg'}`"
                >
                  <span class="msg-avatar" :style="{ background: roleColor(msg.from) }" :title="msg.from">{{ roleAvatar(msg.from) }}</span>
                  <div class="msg-body">
                    <div class="msg-head">
                      <span class="msg-from">{{ msg.from }}</span>
                      <span class="msg-arrow" aria-hidden="true">→</span>
                      <span class="msg-to">{{ msg.to === '__all__' ? '全体专家' : msg.to }}</span>
                      <span v-if="msg.round" class="msg-round">R{{ msg.round }}</span>
                      <span class="msg-kind">{{ kindLabel(msg.kind) }}</span>
                    </div>
                    <p class="msg-text">{{ msg.content }}</p>
                    <p v-if="msg.evidence" class="msg-evidence">
                      <span class="ev-label">依据</span>{{ msg.evidence }}
                    </p>
                  </div>
                </div>
              </div>
            </div>

            <!-- 会诊黑板（M3） -->
            <div
              v-if="entry.blackboard && (entry.blackboard.entries?.length || entry.blackboard.convergence)"
              class="blk blk-board"
            >
              <div class="blk-head">
                <span class="blk-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path v-for="(d, i) in ICONS.board" :key="i" :d="d" /></svg></span>
                <span class="blk-label">会诊黑板</span>
                <span class="blk-count">{{ entry.blackboard.entries?.length || 0 }} 条发现</span>
              </div>
              <div class="notes">
                <div
                  v-for="(item, index) in entry.blackboard.entries"
                  :key="`${entry.key}-bb-${index}`"
                  class="note"
                >
                  <div class="note-head">
                    <span class="note-avatar" :style="{ background: roleColor(item.role) }" :title="item.role">{{ roleAvatar(item.role) }}</span>
                    <span class="note-role">{{ item.role }}</span>
                    <span v-if="item.round" class="note-round">R{{ item.round }}</span>
                  </div>
                  <p class="note-text">{{ item.content }}</p>
                </div>
              </div>

              <div v-if="entry.blackboard.convergence" class="verdict verdict-converge">
                <span class="verdict-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path v-for="(d, i) in ICONS.compass" :key="i" :d="d" /></svg></span>
                <div class="verdict-body">
                  <div class="verdict-label">教学总监收敛结论</div>
                  <p class="verdict-text">{{ entry.blackboard.convergence }}</p>
                </div>
              </div>

              <div v-if="entry.blackboard.arbitration" class="verdict verdict-arbitrate">
                <span class="verdict-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path v-for="(d, i) in ICONS.scale" :key="i" :d="d" /></svg></span>
                <div class="verdict-body">
                  <div class="verdict-label">仲裁裁决</div>
                  <p class="verdict-text">{{ entry.blackboard.arbitration }}</p>
                </div>
              </div>
            </div>

            <!-- 辩论与仲裁 -->
            <div v-if="entry.debate && entry.debate.history?.length" class="blk blk-debate">
              <div class="blk-head">
                <span class="blk-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path v-for="(d, i) in ICONS.scale" :key="i" :d="d" /></svg></span>
                <span class="blk-label">多专家辩论</span>
                <span class="blk-count">{{ entry.debate.rounds }} 条发言</span>
                <!-- running 兜底：SSE 异常/断连时 streaming 可能残留，生成结束即隐藏 -->
                <span v-if="entry.streaming && running" class="blk-tag">生成中</span>
              </div>
              <div class="stream">
                <div
                  v-for="(item, index) in entry.debate.history"
                  :key="`${entry.key}-debate-${index}`"
                  class="msg"
                >
                  <span class="msg-avatar" :style="{ background: roleColor(item.role) }" :title="item.role">{{ roleAvatar(item.role) }}</span>
                  <div class="msg-body">
                    <div class="msg-head">
                      <span class="msg-from">{{ item.role }}</span>
                      <span v-if="item.round" class="msg-round">R{{ item.round }}</span>
                    </div>
                    <p class="msg-text">{{ item.content }}<span v-if="item.streaming && running" class="stream-caret" aria-hidden="true"></span></p>
                  </div>
                </div>
              </div>
              <div v-if="entry.debate.arbitration" class="verdict verdict-arbitrate">
                <span class="verdict-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path v-for="(d, i) in ICONS.scale" :key="i" :d="d" /></svg></span>
                <div class="verdict-body">
                  <div class="verdict-label">仲裁裁决</div>
                  <p class="verdict-text">{{ entry.debate.arbitration }}</p>
                </div>
              </div>
            </div>

            <!-- 分歧门控跳过辩论：显式说明，避免静默消失被误读为链路故障 -->
            <div v-else-if="entry.debate && entry.debate.skipped" class="skip">
              <span class="skip-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path v-for="(d, i) in ICONS.info" :key="i" :d="d" /></svg></span>
              <span class="skip-title">未触发辩论</span>
              <span class="skip-reason">{{ entry.debate.skipReason || '专家意见一致' }}</span>
            </div>

            <!-- 流式长文本区块：综合提案 / 收敛结论 / 仲裁裁决，边生成边逐字打印 -->
            <div v-if="entry.phase === 'verdict'" class="blk" :class="verdictMeta(entry.verdictKind).blk">
              <div class="blk-head">
                <span class="blk-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path v-for="(d, i) in ICONS[verdictMeta(entry.verdictKind).icon]" :key="i" :d="d" /></svg></span>
                <span class="blk-label">{{ entry.verdictLabel || verdictMeta(entry.verdictKind).label }}</span>
                <span v-if="entry.streaming && running" class="blk-tag">生成中</span>
              </div>
              <div class="verdict" :class="entry.verdictKind === 'arbitration' ? 'verdict-arbitrate' : 'verdict-converge'">
                <span class="verdict-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path v-for="(d, i) in ICONS[verdictMeta(entry.verdictKind).icon]" :key="i" :d="d" /></svg></span>
                <div class="verdict-body">
                  <p class="verdict-text">{{ entry.verdictText }}<span v-if="entry.streaming && running" class="stream-caret" aria-hidden="true"></span></p>
                </div>
              </div>
            </div>

            <!-- 循证依据 -->
            <div v-if="entry.sources?.length" class="blk blk-evidence">
              <div class="blk-head">
                <span class="blk-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path v-for="(d, i) in ICONS.search" :key="i" :d="d" /></svg></span>
                <span class="blk-label">循证依据</span>
                <span class="blk-count">{{ entry.sources.length }} 条</span>
              </div>
              <div
                v-for="(source, index) in entry.sources"
                :key="`${entry.key}-src-${index}`"
                class="cite"
              >
                <div class="cite-head">
                  <span class="cite-guide">{{ source.guide || '未知指南' }}</span>
                  <span v-if="source.page && source.page !== '?'" class="cite-page">P{{ source.page }}</span>
                  <span v-if="source.score && source.score !== 'N/A'" class="cite-score">相关度 {{ source.score }}</span>
                </div>
                <p v-if="source.query" class="cite-query">检索：{{ source.query }}</p>
                <p v-if="source.excerpt" class="cite-text" :class="{ clamped: needsClamp(source.excerpt) && !isOpen(`${entry.key}-src-${index}`) }">{{ source.excerpt }}</p>
                <button
                  v-if="needsClamp(source.excerpt)"
                  type="button"
                  class="more"
                  @click="toggle(`${entry.key}-src-${index}`)"
                >{{ isOpen(`${entry.key}-src-${index}`) ? '收起' : '展开摘录' }}</button>
              </div>
            </div>
          </div>
        </li>
      </ol>
    </div>
  </details>
</template>

<style scoped>
/* ══════════════ 面板外壳：对齐全站视觉语言（柔和染色 + 气泡尾圆角） ══════════════ */
.trace {
  --trace-surface: linear-gradient(135deg, rgba(17, 150, 127, 0.045), rgba(139, 92, 246, 0.035));
  --trace-border: rgba(17, 150, 127, 0.16);
  --trace-line: rgba(17, 150, 127, 0.14);
  --trace-rail: #cbd9d6;
  --trace-chip: rgba(17, 150, 127, 0.09);

  width: 100%;
  margin: 4px 0 14px;
  overflow: hidden;
  border: 1px solid var(--trace-border);
  border-radius: 14px 14px 14px 4px;
  background: var(--trace-surface);
  box-shadow:
    0 2px 12px rgba(15, 65, 79, 0.05),
    inset 0 1px 0 rgba(255, 255, 255, 0.6);
}

:global(html[data-theme='dark']) .trace {
  --trace-surface: linear-gradient(135deg, rgba(45, 212, 191, 0.06), rgba(139, 92, 246, 0.06));
  --trace-border: rgba(94, 234, 212, 0.18);
  --trace-line: rgba(94, 234, 212, 0.16);
  --trace-rail: #3f5560;
  --trace-chip: rgba(45, 212, 191, 0.12);
  box-shadow:
    0 2px 12px rgba(0, 0, 0, 0.25),
    inset 0 1px 0 rgba(255, 255, 255, 0.04);
}

/* ══════════════ 头部 ══════════════ */
.trace-head {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr) auto 16px;
  align-items: center;
  gap: 10px;
  min-height: 50px;
  padding: 8px 14px;
  cursor: pointer;
  list-style: none;
  user-select: none;
}

.trace-head::-webkit-details-marker { display: none; }

.trace-badge {
  display: grid;
  width: 28px;
  height: 28px;
  place-items: center;
  border-radius: 9px;
  background: var(--gradient-aurora);
  color: #fff;
  box-shadow: 0 3px 10px rgba(17, 150, 127, 0.28);
}

.trace-badge svg { width: 15px; height: 15px; }

.trace-heading {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 2px;
}

.trace-title {
  color: var(--color-text-strong);
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.01em;
}

.trace-meta {
  display: flex;
  overflow: hidden;
  gap: 4px;
  color: var(--color-text-light);
  font-size: 11px;
  white-space: nowrap;
}

.meta-item { flex: none; }

.trace-status {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 9px;
  border-radius: var(--radius-pill);
  background: var(--trace-chip);
  color: var(--color-text-medium);
  font-size: 11px;
  font-weight: 650;
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--color-text-light);
}

.trace-status.active { color: var(--color-primary-dark); }
.trace-status.active .status-dot {
  background: var(--color-primary-light);
  box-shadow: 0 0 0 3px rgba(16, 185, 129, 0.16);
  animation: dot-breathe 1.5s ease-in-out infinite;
}

.trace-chevron {
  width: 7px;
  height: 7px;
  border-right: 1.5px solid var(--color-text-light);
  border-bottom: 1.5px solid var(--color-text-light);
  transform: rotate(45deg) translateY(-2px);
  transition: transform var(--transition-normal);
}

.trace[open] .trace-chevron { transform: rotate(225deg) translate(-1px, -1px); }

/* ══════════════ 滚动区（保留自然滚动链，不设 overscroll-behavior） ══════════════ */
.trace-body {
  max-height: min(42vh, 420px);
  overflow-y: auto;
  /* 保留自然滚动链：面板滚到底后滚轮继续带动外层（聊天列表/页面）滚动 */
  scrollbar-width: thin;
  scrollbar-color: rgba(94, 115, 121, 0.35) transparent;
}

.trace-list {
  margin: 0;
  padding: 4px 14px 14px;
  list-style: none;
}

/* ══════════════ 步骤与时间轴 ══════════════ */
.trace-step {
  --tone: var(--color-primary);
  --tone-soft: rgba(17, 150, 127, 0.14);
  display: grid;
  grid-template-columns: 20px minmax(0, 1fr);
  gap: 9px;
  min-width: 0;
  padding-top: 10px;
}

.tone-slate { --tone: #64748b; --tone-soft: rgba(100, 116, 139, 0.16); }
.tone-primary { --tone: var(--color-primary); --tone-soft: rgba(17, 150, 127, 0.16); }
.tone-violet { --tone: #7c3aed; --tone-soft: rgba(124, 58, 237, 0.16); }
.tone-blue { --tone: #2563a8; --tone-soft: rgba(37, 99, 168, 0.16); }
.tone-amber { --tone: #b45309; --tone-soft: rgba(180, 83, 9, 0.16); }
.tone-rose { --tone: #be185d; --tone-soft: rgba(190, 24, 93, 0.16); }
.tone-green { --tone: #0f7666; --tone-soft: rgba(15, 118, 102, 0.18); }

.rail {
  position: relative;
  display: flex;
  justify-content: center;
}

.trace-step:not(:last-child) .rail::after {
  position: absolute;
  top: 26px;
  bottom: -14px;
  width: 1px;
  background: var(--trace-line);
  content: '';
}

.rail-dot {
  position: relative;
  z-index: 1;
  display: grid;
  width: 20px;
  height: 20px;
  place-items: center;
  border-radius: 50%;
  background: var(--tone-soft);
  color: var(--tone);
}

.rail-dot svg { width: 11px; height: 11px; }

.step-body { min-width: 0; padding-bottom: 2px; }

.step-head {
  display: flex;
  align-items: baseline;
  gap: 7px;
  min-width: 0;
}

.phase-chip {
  flex: none;
  padding: 1px 7px;
  border-radius: var(--radius-pill);
  background: var(--tone-soft);
  color: var(--tone);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.03em;
}

.step-title {
  min-width: 0;
  color: var(--color-text-strong);
  font-size: 12.5px;
  font-weight: 650;
  line-height: 1.5;
}

.step-text {
  margin: 5px 0 0;
  color: var(--color-text-medium);
  font-size: 12px;
  line-height: 1.65;
}

/* ══════════════ 区块通用：一套色条体系替代原先六套边框 ══════════════ */
.blk {
  --blk: var(--color-primary);
  --blk-soft: rgba(17, 150, 127, 0.06);
  margin-top: 9px;
  padding: 9px 11px 10px;
  border-left: 2px solid var(--blk);
  border-radius: 3px 9px 9px 3px;
  background: var(--blk-soft);
}

.blk-experts { --blk: #7c3aed; --blk-soft: rgba(124, 58, 237, 0.05); }
.blk-dialogue { --blk: #2563a8; --blk-soft: rgba(37, 99, 168, 0.05); }
.blk-board { --blk: #b45309; --blk-soft: rgba(180, 83, 9, 0.05); }
.blk-debate { --blk: #be185d; --blk-soft: rgba(190, 24, 93, 0.05); }
.blk-evidence { --blk: var(--color-primary); --blk-soft: rgba(17, 150, 127, 0.05); }

.blk-head {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 7px;
}

.blk-icon {
  display: grid;
  width: 16px;
  height: 16px;
  place-items: center;
  color: var(--blk);
}

.blk-icon svg { width: 13px; height: 13px; }

.blk-label {
  color: var(--blk);
  font-size: 11.5px;
  font-weight: 700;
  letter-spacing: 0.02em;
}

.blk-count {
  color: var(--color-text-light);
  font-size: 11px;
}

.blk-tag {
  margin-left: auto;
  padding: 1px 7px;
  border-radius: var(--radius-pill);
  background: rgba(17, 150, 127, 0.1);
  color: var(--color-text-label);
  font-size: 10px;
  font-weight: 650;
}

.blk-note {
  margin: 0 0 8px;
  color: var(--color-text-light);
  font-size: 11.5px;
  line-height: 1.6;
}

/* ══════════════ 专家 chips ══════════════ */
.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}

.chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 9px 3px 7px;
  border: 1px solid var(--trace-border);
  border-radius: var(--radius-pill);
  background: var(--color-bg-base);
  color: var(--color-text-medium);
  font-size: 11px;
  font-weight: 600;
}

.chip-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}

/* ══════════════ 专家发言 ══════════════ */
.said {
  padding: 8px 0 0;
}

.said + .said {
  margin-top: 8px;
  border-top: 1px dashed var(--trace-border);
}

.said-head {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}

.said-avatar,
.msg-avatar,
.note-avatar {
  display: grid;
  flex: none;
  width: 18px;
  height: 18px;
  place-items: center;
  border-radius: 50%;
  color: #fff;
  font-size: 10px;
  font-weight: 700;
}

.said-role {
  color: var(--color-text-medium);
  font-size: 11.5px;
  font-weight: 650;
}

.said-text {
  margin: 0;
  color: var(--color-text-medium);
  font-size: 12px;
  line-height: 1.68;
}

/* ══════════════ 对话流（气泡式） ══════════════ */
.stream {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.msg {
  display: grid;
  grid-template-columns: 18px minmax(0, 1fr);
  gap: 8px;
}

.msg-body {
  min-width: 0;
  padding: 7px 10px;
  border-radius: 3px 10px 10px 10px;
  background: var(--color-bg-base);
  box-shadow: 0 1px 3px rgba(15, 65, 79, 0.05);
}

.msg-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 5px;
  margin-bottom: 3px;
}

.msg-from {
  color: var(--color-text-strong);
  font-size: 11.5px;
  font-weight: 650;
}

.msg-arrow { color: var(--color-text-weak); font-size: 11px; }

.msg-to {
  color: var(--color-text-medium);
  font-size: 11.5px;
}

.msg-round {
  padding: 0 5px;
  border-radius: 4px;
  background: var(--trace-chip);
  color: var(--color-text-label);
  font-size: 10px;
  font-weight: 700;
}

.msg-kind {
  margin-left: auto;
  padding: 1px 7px;
  border-radius: var(--radius-pill);
  background: rgba(37, 99, 168, 0.1);
  color: #2563a8;
  font-size: 10px;
  font-weight: 700;
}

:global(html[data-theme='dark']) .msg-kind { color: #93b8f0; }

.kind-object .msg-kind { background: rgba(190, 24, 93, 0.1); color: #be185d; }
.kind-revise .msg-kind { background: rgba(180, 83, 9, 0.12); color: #b45309; }
.kind-finding .msg-kind { background: rgba(15, 118, 102, 0.12); color: #0f766e; }
.kind-question .msg-kind { background: rgba(124, 58, 237, 0.1); color: #7c3aed; }

:global(html[data-theme='dark']) .kind-object .msg-kind { color: #f0a3c0; }
:global(html[data-theme='dark']) .kind-revise .msg-kind { color: #e0b070; }
:global(html[data-theme='dark']) .kind-finding .msg-kind { color: #5eead4; }
:global(html[data-theme='dark']) .kind-question .msg-kind { color: #c4b5fd; }

.msg-text {
  margin: 0;
  color: var(--color-text-medium);
  font-size: 12px;
  line-height: 1.68;
}

.msg-evidence {
  display: flex;
  gap: 5px;
  margin: 5px 0 0;
  padding: 4px 7px;
  border-radius: 5px;
  background: var(--trace-chip);
  color: var(--color-text-light);
  font-size: 11px;
  line-height: 1.55;
}

.ev-label {
  flex: none;
  color: var(--color-text-label);
  font-weight: 700;
}

/* ══════════════ 黑板便签 ══════════════ */
.notes {
  display: grid;
  gap: 7px;
  grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
}

.note {
  padding: 8px 9px;
  border-radius: 8px;
  background: var(--color-bg-base);
  box-shadow: 0 1px 3px rgba(15, 65, 79, 0.05);
}

.note-head {
  display: flex;
  align-items: center;
  gap: 5px;
  margin-bottom: 4px;
}

.note-role {
  overflow: hidden;
  color: var(--color-text-medium);
  font-size: 11px;
  font-weight: 650;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.note-round {
  margin-left: auto;
  color: var(--color-text-weak);
  font-size: 10px;
  font-weight: 700;
}

.note-text {
  margin: 0;
  color: var(--color-text-medium);
  font-size: 11.5px;
  line-height: 1.6;
}

/* ══════════════ 结论条（收敛 / 仲裁） ══════════════ */
.verdict {
  display: grid;
  grid-template-columns: 18px minmax(0, 1fr);
  gap: 8px;
  margin-top: 9px;
  padding: 9px 11px;
  border-radius: 9px;
}

.verdict-converge {
  background: linear-gradient(135deg, rgba(17, 150, 127, 0.1), rgba(14, 165, 233, 0.07));
  border: 1px solid rgba(17, 150, 127, 0.18);
}

.verdict-arbitrate {
  background: linear-gradient(135deg, rgba(180, 83, 9, 0.1), rgba(190, 24, 93, 0.06));
  border: 1px solid rgba(180, 83, 9, 0.2);
}

.verdict-icon {
  display: grid;
  width: 18px;
  height: 18px;
  place-items: center;
}

.verdict-icon svg { width: 14px; height: 14px; }

.verdict-converge .verdict-icon { color: var(--color-primary-dark); }
.verdict-arbitrate .verdict-icon { color: #b45309; }

:global(html[data-theme='dark']) .verdict-converge .verdict-icon { color: #5eead4; }
:global(html[data-theme='dark']) .verdict-arbitrate .verdict-icon { color: #e0b070; }

.verdict-label {
  margin-bottom: 3px;
  color: var(--color-text-strong);
  font-size: 11.5px;
  font-weight: 700;
}

.verdict-text {
  margin: 0;
  color: var(--color-text-medium);
  font-size: 12px;
  line-height: 1.7;
  white-space: pre-wrap;
}

/* ══════════════ 跳过辩论提示 ══════════════ */
.skip {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-top: 9px;
  padding: 7px 10px;
  border: 1px dashed var(--trace-border);
  border-radius: 8px;
  color: var(--color-text-light);
  font-size: 11.5px;
  line-height: 1.55;
}

.skip-icon {
  display: grid;
  flex: none;
  width: 14px;
  height: 14px;
  place-items: center;
  color: var(--color-text-light);
}

.skip-icon svg { width: 12px; height: 12px; }

.skip-title {
  color: var(--color-text-medium);
  font-weight: 700;
}

/* ══════════════ 引证卡片 ══════════════ */
.cite {
  padding: 8px 0 0;
}

.cite + .cite {
  margin-top: 8px;
  border-top: 1px dashed var(--trace-border);
}

.cite-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}

.cite-guide {
  color: var(--color-text-strong);
  font-size: 11.5px;
  font-weight: 650;
}

.cite-page,
.cite-score {
  padding: 1px 6px;
  border-radius: 4px;
  background: var(--trace-chip);
  color: var(--color-text-label);
  font-size: 10px;
  font-weight: 650;
}

.cite-query {
  margin: 0 0 4px;
  color: var(--color-text-light);
  font-size: 11px;
}

.cite-text {
  margin: 0;
  padding: 6px 9px;
  border-left: 2px solid rgba(17, 150, 127, 0.3);
  border-radius: 0 6px 6px 0;
  background: var(--color-bg-base);
  color: var(--color-text-medium);
  font-size: 11.5px;
  line-height: 1.68;
}

/* ══════════════ 折叠 ══════════════ */
.clamped {
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.more {
  margin-top: 4px;
  padding: 0;
  border: 0;
  background: none;
  color: var(--color-primary-dark);
  font-size: 11px;
  font-weight: 650;
  cursor: pointer;
}

.more:hover { text-decoration: underline; }

:global(html[data-theme='dark']) .more { color: #5eead4; }

/* 逐字打印光标：贴在被流式写入的文本末尾 */
.stream-caret {
  display: inline-block;
  width: 2px;
  height: 1em;
  margin-left: 2px;
  vertical-align: text-bottom;
  background: var(--color-primary);
  animation: caret-blink 1s steps(2, start) infinite;
}

@keyframes caret-blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

@keyframes dot-breathe {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.35; }
}

@media (max-width: 640px) {
  .trace-head { grid-template-columns: 24px minmax(0, 1fr) auto; gap: 8px; padding: 8px 11px; }
  .trace-badge { width: 24px; height: 24px; border-radius: 8px; }
  .trace-chevron { display: none; }
  .trace-list { padding: 4px 11px 12px; }
  .blk { padding: 8px 9px 9px; }
  .notes { grid-template-columns: 1fr; }
}
</style>
