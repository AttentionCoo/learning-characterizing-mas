<script setup>
import { computed } from 'vue'

const props = defineProps({
  entries: { type: Array, default: () => [] },
  running: { type: Boolean, default: false },
})

const sourceCount = computed(() => props.entries.reduce(
  (total, entry) => total + (entry.sources?.length || 0),
  0,
))
</script>

<template>
  <details v-if="entries.length" class="reasoning-trace" :open="running">
    <summary>
      <span class="trace-title">AI 推理与检索依据</span>
      <span class="trace-meta">{{ entries.length }} 个步骤<span v-if="sourceCount"> · {{ sourceCount }} 条指南证据</span></span>
      <span class="trace-chevron" aria-hidden="true"></span>
    </summary>

    <ol class="trace-list">
      <li v-for="entry in entries" :key="entry.key" class="trace-step" :class="entry.status">
        <div class="step-marker" aria-hidden="true"></div>
        <div class="step-body">
          <div class="step-title">{{ entry.title }}</div>
          <p v-if="entry.content" class="step-content">{{ entry.content }}</p>

          <div v-if="entry.sources?.length" class="source-list">
            <div v-for="(source, index) in entry.sources" :key="`${entry.key}-${index}`" class="source-item">
              <div class="source-heading">
                <strong>指南：{{ source.guide || '未知指南' }}</strong>
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
  </details>
</template>

<style scoped>
.reasoning-trace {
  width: 100%;
  margin: 10px 0 12px;
  border-top: 1px solid var(--color-border-light);
  border-bottom: 1px solid var(--color-border-light);
  color: var(--color-text-medium);
}

summary {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto 18px;
  align-items: center;
  gap: 8px;
  min-height: 38px;
  cursor: pointer;
  list-style: none;
  user-select: none;
}

summary::-webkit-details-marker { display: none; }

.trace-title {
  color: var(--color-text-strong);
  font-size: 13px;
  font-weight: 700;
}

.trace-meta { font-size: 12px; }

.trace-chevron {
  width: 7px;
  height: 7px;
  border-right: 1.5px solid currentColor;
  border-bottom: 1.5px solid currentColor;
  transform: rotate(45deg) translateY(-2px);
  transition: transform 0.18s ease;
}

details[open] .trace-chevron { transform: rotate(225deg) translate(-1px, -1px); }

.trace-list {
  margin: 0;
  padding: 2px 0 10px;
  list-style: none;
}

.trace-step {
  display: grid;
  grid-template-columns: 12px minmax(0, 1fr);
  gap: 8px;
  padding: 6px 0;
}

.step-marker {
  width: 7px;
  height: 7px;
  margin-top: 6px;
  border-radius: 50%;
  background: #94a3b8;
}

.trace-step.running .step-marker {
  background: #0f9d7a;
  box-shadow: 0 0 0 3px rgba(15, 157, 122, 0.12);
}

.step-title {
  color: var(--color-text-strong);
  font-size: 13px;
  font-weight: 650;
}

.step-content {
  margin: 3px 0 0;
  font-size: 12px;
  line-height: 1.6;
}

.source-list {
  margin-top: 8px;
  border-left: 2px solid rgba(15, 157, 122, 0.28);
  padding-left: 10px;
}

.source-item + .source-item {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed var(--color-border-light);
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
  margin: 5px 0 0;
  padding: 0;
  border: 0;
  color: var(--color-text-strong);
  font-size: 12px;
  line-height: 1.55;
}

@media (max-width: 640px) {
  summary { grid-template-columns: minmax(0, 1fr) 18px; }
  .trace-meta { grid-column: 1 / -1; grid-row: 2; padding-bottom: 7px; }
  .trace-chevron { grid-column: 2; grid-row: 1; }
}
</style>
