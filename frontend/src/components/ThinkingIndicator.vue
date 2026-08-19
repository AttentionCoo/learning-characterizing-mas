<script setup>
import { computed } from 'vue'

const props = defineProps({
  hint: { type: String, default: 'AI 正在思考...' },
})

// 多智能体协作等候指示器：旋转光环 + 环绕头像点 + 状态文案
// 头像点代表并行工作的专家智能体（画像/需求/文档/题目/激励…）
const AGENTS = [
  { label: '画像', color: '#3b82f6' },
  { label: '需求', color: '#f59e0b' },
  { label: '内容', color: '#10b981' },
  { label: '评测', color: '#8b5cf6' },
  { label: '激励', color: '#ef4444' },
  { label: '仲裁', color: '#14b8a6' },
]

const orbitStyle = computed(() => AGENTS.map((a, i) => ({
  '--agent-color': a.color,
  '--agent-angle': `${i * 60}deg`,
  '--agent-delay': `${-i * 0.35}s`,
})))

const statusText = computed(() => {
  const h = props.hint || ''
  if (h.includes('专家') || h.includes('会诊') || h.includes('推理') || h.includes('生成')) return h
  return `${h} 正在调度专家智能体协作中…`
})
</script>

<template>
  <div class="thinking-indicator" role="status" aria-live="polite">
    <div class="agent-orbit" aria-hidden="true">
      <div class="orbit-ring"></div>
      <div
        v-for="(agent, i) in AGENTS"
        :key="agent.label"
        class="orbit-agent"
        :style="orbitStyle[i]"
      >
        <span class="agent-dot"></span>
      </div>
      <div class="orbit-core">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 2a7 7 0 0 1 7 7c0 2.4-1.2 4.4-3 5.6V17H8v-2.4C6.2 13.4 5 11.4 5 9a7 7 0 0 1 7-7z"/>
          <path d="M9 21h6M10 17.5h4"/>
        </svg>
      </div>
    </div>
    <div class="thinking-body">
      <div class="thinking-label">
        <span class="thinking-pulse-dot"></span>
        多智能体协作中
      </div>
      <div class="thinking-text">{{ statusText }}</div>
    </div>
  </div>
</template>

<style scoped>
.thinking-indicator {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 14px 18px;
  background: linear-gradient(135deg, rgba(139, 92, 246, 0.04), rgba(17, 150, 127, 0.05));
  border: 1px solid rgba(139, 92, 246, 0.14);
  border-radius: 16px 16px 16px 4px;
  box-shadow:
    0 2px 10px rgba(139, 92, 246, 0.08),
    inset 0 1px 0 rgba(255, 255, 255, 0.8);
}

/* ── 旋转光环 ── */
.agent-orbit {
  position: relative;
  flex: none;
  width: 46px;
  height: 46px;
}

.orbit-ring {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  border: 2px dashed rgba(17, 150, 127, 0.35);
  animation: orbit-spin 6s linear infinite;
}

.orbit-core {
  position: absolute;
  inset: 11px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: linear-gradient(135deg, #11967f, #0ea5e9);
  color: #ffffff;
  box-shadow: 0 3px 10px rgba(17, 150, 127, 0.4);
  animation: core-pulse 2s ease-in-out infinite;
}

.orbit-agent {
  position: absolute;
  top: 50%;
  left: 50%;
  width: 10px;
  height: 10px;
  margin: -5px 0 0 -5px;
  transform: rotate(var(--agent-angle)) translateX(23px);
}

.orbit-agent .agent-dot {
  display: block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--agent-color);
  border: 2px solid #ffffff;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.2);
  animation: dot-pop 2.4s ease-in-out infinite;
  animation-delay: var(--agent-delay);
}

/* ── 文案区 ── */
.thinking-body {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.thinking-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  font-weight: 700;
  color: var(--color-primary-dark);
  letter-spacing: 0.04em;
}

.thinking-pulse-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--gradient-aurora);
  animation: pulse 1.4s ease-in-out infinite;
}

.thinking-text {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-medium);
  line-height: 1.5;
}

@keyframes orbit-spin {
  to { transform: rotate(360deg); }
}

@keyframes dot-pop {
  0%, 100% { transform: scale(1); opacity: 0.9; }
  50% { transform: scale(1.35); opacity: 1; }
}

@keyframes core-pulse {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.08); }
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.35; }
}

@media (max-width: 640px) {
  .thinking-indicator { padding: 12px 14px; gap: 12px; }
  .agent-orbit { width: 40px; height: 40px; }
  .orbit-agent { transform: rotate(var(--agent-angle)) translateX(20px); }
}
</style>
