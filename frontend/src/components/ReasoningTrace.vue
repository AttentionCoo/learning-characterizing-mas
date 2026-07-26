<script setup>
import { computed, nextTick, ref, watch } from 'vue'

const props = defineProps({
  entries: { type: Array, default: () => [] },
  running: { type: Boolean, default: false },
})

const sourceCount = computed(() => props.entries.reduce(
  (total, entry) => total + (entry.sources?.length || 0),
  0,
))
const traceBodyRef = ref(null)

watch(
  () => props.entries.length,
  async () => {
    if (!props.running) return
    await nextTick()
    const element = traceBodyRef.value
    if (element) element.scrollTop = element.scrollHeight
  },
)

function phaseLabel(phase) {
  if (phase === 'start') return '开始'
  if (phase === 'done') return '完成'
  return '处理中'
}
</script>

<template>
  <details v-if="entries.length" class="reasoning-trace" open>
    <summary class="trace-header">
      <span class="trace-mark" aria-hidden="true">AI</span>
      <span class="trace-heading">
        <span class="trace-title">AI 推理与检索依据</span>
        <span class="trace-meta">{{ entries.length }} 条事件<span v-if="sourceCount"> · {{ sourceCount }} 条指南证据</span></span>
      </span>
      <span class="trace-status" :class="{ active: running }">
        <span class="status-dot" aria-hidden="true"></span>
        {{ running ? '推理中' : '已完成' }}
      </span>
      <span class="trace-chevron" aria-hidden="true"></span>
    </summary>

    <div ref="traceBodyRef" class="trace-body" aria-live="polite">
      <ol class="trace-list">
        <li v-for="entry in entries" :key="entry.key" class="trace-step" :class="entry.phase">
          <div class="timeline-rail" aria-hidden="true">
            <span class="step-marker"></span>
          </div>
          <div class="step-body">
            <div class="step-heading">
              <span class="phase-label">{{ phaseLabel(entry.phase) }}</span>
              <span class="step-title">{{ entry.title }}</span>
            </div>
            <p v-if="entry.content" class="step-content">{{ entry.content }}</p>

            <div v-if="entry.sources?.length" class="source-list">
              <div v-for="(source, index) in entry.sources" :key="`${entry.key}-${index}`" class="source-item">
                <div class="source-heading">
                  <strong>{{ source.guide || '未知指南' }}</strong>
                  <span v-if="source.page && source.page !== '?'">第 {{ source.page }} 页</span>
                  <span v-if="source.score && source.score !== 'N/A'">相关度 {{ source.score }}</span>
                </div>
                <div v-if="source.query" class="source-query">检索问题：{{ source.query }}</div>
                <blockquote v-if="source.excerpt">{{ source.excerpt }}</blockquote>
              </div>
            </div>
          </div>
        </li>
      </ol>
    </div>
  </details>
</template>

<style scoped>
.reasoning-trace {
  width: 100%;
  margin: 4px 0 14px;
  overflow: hidden;
  border: 1px solid #dce5e8;
  border-radius: 8px;
  background: #f8fafb;
  color: var(--color-text-medium);
}

.trace-header {
  display: grid;
  grid-template-columns: 30px minmax(0, 1fr) auto 18px;
  align-items: center;
  gap: 10px;
  min-height: 52px;
  padding: 0 14px;
  border-bottom: 1px solid transparent;
  background: #ffffff;
  cursor: pointer;
  list-style: none;
  user-select: none;
}

.trace-header::-webkit-details-marker { display: none; }

details[open] .trace-header { border-bottom-color: #e4eaed; }

.trace-mark {
  display: grid;
  width: 28px;
  height: 28px;
  place-items: center;
  border-radius: 6px;
  background: #0f766e;
  color: #ffffff;
  font-size: 10px;
  font-weight: 800;
}

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
}

.trace-meta {
  overflow: hidden;
  color: #718096;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.trace-status {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: #64748b;
  font-size: 11px;
  font-weight: 650;
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #94a3b8;
}

.trace-status.active { color: #08745e; }
.trace-status.active .status-dot {
  background: #10b981;
  box-shadow: 0 0 0 3px rgba(16, 185, 129, 0.13);
}

.trace-chevron {
  width: 7px;
  height: 7px;
  border-right: 1.5px solid currentColor;
  border-bottom: 1.5px solid currentColor;
  transform: rotate(45deg) translateY(-2px);
  transition: transform 0.18s ease;
}

details[open] .trace-chevron { transform: rotate(225deg) translate(-1px, -1px); }

.trace-body {
  max-height: min(42vh, 420px);
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-width: thin;
  scrollbar-color: #cbd5e1 transparent;
}

.trace-list {
  margin: 0;
  padding: 10px 14px 12px;
  list-style: none;
}

.trace-step {
  display: grid;
  grid-template-columns: 16px minmax(0, 1fr);
  gap: 9px;
  min-width: 0;
}

.timeline-rail {
  position: relative;
  display: flex;
  justify-content: center;
}

.trace-step:not(:last-child) .timeline-rail::after {
  position: absolute;
  top: 15px;
  bottom: -2px;
  width: 1px;
  background: #d9e2e5;
  content: '';
}

.step-marker {
  position: relative;
  z-index: 1;
  width: 7px;
  height: 7px;
  margin-top: 7px;
  border-radius: 50%;
  border: 2px solid #f8fafb;
  box-sizing: content-box;
  background: #94a3b8;
}

.trace-step.progress .step-marker {
  background: #0f9d7a;
  box-shadow: 0 0 0 3px rgba(15, 157, 122, 0.12);
}

.trace-step.done .step-marker { background: #2563eb; }

.step-heading {
  display: flex;
  align-items: baseline;
  gap: 7px;
}

.step-body {
  min-width: 0;
  padding: 2px 0 12px;
}

.phase-label {
  flex: 0 0 auto;
  color: #718096;
  font-size: 10px;
  font-weight: 700;
}

.step-title {
  color: var(--color-text-strong);
  font-size: 13px;
  font-weight: 700;
  overflow-wrap: anywhere;
}

.step-content {
  margin: 4px 0 0;
  color: #52616b;
  font-size: 12px;
  line-height: 1.65;
  overflow-wrap: anywhere;
}

.source-list {
  margin-top: 10px;
  border-top: 1px solid #dfe8e6;
}

.source-item {
  padding: 10px 0;
}

.source-item + .source-item {
  border-top: 1px dashed #d7e0e3;
}

.source-heading {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 4px 10px;
  font-size: 11px;
}

.source-heading strong {
  color: #08745e;
  font-size: 12px;
  overflow-wrap: anywhere;
}

.source-query {
  margin-top: 4px;
  color: var(--color-text-medium);
  font-size: 11px;
}

blockquote {
  margin: 7px 0 0;
  padding: 8px 10px;
  border: 0;
  border-left: 2px solid #67b9a7;
  background: #ffffff;
  color: #334155;
  font-size: 12px;
  line-height: 1.65;
  overflow-wrap: anywhere;
}

@media (max-width: 640px) {
  .trace-header {
    grid-template-columns: 28px minmax(0, 1fr) 16px;
    gap: 8px;
    padding: 0 10px;
  }
  .trace-status { display: none; }
  .trace-chevron { grid-column: 3; }
  .trace-list { padding-inline: 10px; }
  .trace-body { max-height: 360px; }
}
</style>
