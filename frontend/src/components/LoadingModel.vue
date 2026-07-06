<template>
  <transition name="fade">
    <div v-if="show" class="lm-overlay" role="dialog" aria-modal="true" aria-label="加载中对话框">
      <!-- 背景光球 -->
      <div class="lm-orb lm-orb-1"></div>
      <div class="lm-orb lm-orb-2"></div>

      <div class="lm-container prism-border">
        <!-- 梦幻旋转环 -->
        <div class="lm-spinner-wrap">
          <div class="lm-ring"></div>
          <div class="lm-ring-inner"></div>
          <div class="lm-core"></div>
        </div>

        <div class="lm-message">
          <div class="lm-main">学习助手正在认真思考中 ⏳</div>
          <div class="lm-sub">模型回答大约需要 3 分钟，请耐心等待</div>
          <div class="lm-tip">{{ currentTip }}</div>
        </div>

        <!-- 底部光点 -->
        <div class="lm-dots">
          <span></span><span></span><span></span>
        </div>
      </div>
    </div>
  </transition>
</template>


<script setup>
import { watch, onMounted, onBeforeUnmount, computed, ref } from 'vue'

const props = defineProps({
  modelValue: { type: Boolean, required: true },
  disableClose: { type: Boolean, default: true },
})

const emit = defineEmits(['update:modelValue'])

const show = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

// 脑卒中医学常识
const tips = [
  '脑卒中（中风）发作后越早送医，恢复可能性越大。',
  '出现口角歪斜、言语不清、肢体无力应立即就医。',
  '高血压是脑卒中的重要危险因素，要定期监测。',
  '突然单侧肢体麻木或无力是危险信号。',
  '中风抢救有"黄金4.5小时"原则。',
  '长期吸烟和饮酒会增加脑卒中风险。',
  '糖尿病患者更容易发生脑血管意外。',
  '发现异常症状，千万不要等待自行恢复。',
]

const currentTip = ref('')
let timer = null

function changeTip() {
  const index = Math.floor(Math.random() * tips.length)
  currentTip.value = tips[index]
}

// 防止背景滚动
watch(
  () => show.value,
  (val) => {
    if (val) {
      document.body.style.overflow = 'hidden'
      changeTip()
      timer = setInterval(changeTip, 7000)
    } else {
      document.body.style.overflow = ''
      clearInterval(timer)
    }
  },
  { immediate: true }
)

function onKeydown(e) {
  if (e.key === 'Escape' || e.key === 'Esc') {
    if (!props.disableClose) show.value = false
  }
}

onMounted(() => {
  window.addEventListener('keydown', onKeydown)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeydown)
  document.body.style.overflow = ''
  clearInterval(timer)
})
</script>


<style scoped>
/* 遮罩 */
.lm-overlay {
  position: fixed;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-overlay-bg);
  backdrop-filter: blur(4px);
  -webkit-backdrop-filter: blur(4px);
  z-index: 10000;
  -webkit-tap-highlight-color: transparent;
}

/* 背景光球 */
.lm-orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(80px);
  pointer-events: none;
  animation: float-wide 12s ease-in-out infinite;
}
.lm-orb-1 {
  width: 300px; height: 300px;
  background: radial-gradient(circle, rgba(139, 92, 246, 0.25), transparent);
  top: 20%; left: -5%;
}
.lm-orb-2 {
  width: 250px; height: 250px;
  background: radial-gradient(circle, rgba(14, 165, 233, 0.2), transparent);
  bottom: 15%; right: -3%;
  animation-delay: -6s;
}

@keyframes float-wide {
  0%, 100% { transform: translate(0, 0) scale(1); }
  25% { transform: translate(20px, -25px) scale(1.05); }
  50% { transform: translate(-12px, -5px) scale(0.95); }
  75% { transform: translate(8px, 15px) scale(1.03); }
}

/* 容器 */
.lm-container {
  position: relative;
  min-width: 240px;
  max-width: 90%;
  padding: 32px 32px 24px;
  border-radius: var(--radius-xl);
  background: var(--color-dialog-bg);
  box-shadow: var(--shadow-dialog), var(--glow-dreamy);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  pointer-events: auto;
  z-index: 1;
}

/* 梦幻旋转加载器 */
.lm-spinner-wrap {
  position: relative;
  width: 72px;
  height: 72px;
}

.lm-ring {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  border: 3px solid transparent;
  border-top-color: #8b5cf6;
  border-right-color: rgba(14, 165, 233, 0.4);
  animation: dreamy-spin 1.5s linear infinite;
}

.lm-ring-inner {
  position: absolute;
  inset: 8px;
  border-radius: 50%;
  border: 3px solid transparent;
  border-bottom-color: #11967f;
  border-left-color: rgba(139, 92, 246, 0.4);
  animation: dreamy-spin 2s linear infinite reverse;
}

.lm-core {
  position: absolute;
  inset: 20px;
  border-radius: 50%;
  background: var(--gradient-aurora);
  animation: soft-breathe 2s ease-in-out infinite;
  box-shadow: 0 0 16px rgba(139, 92, 246, 0.4);
}

@keyframes dreamy-spin {
  to { transform: rotate(360deg); }
}

@keyframes soft-breathe {
  0%, 100% { box-shadow: 0 0 12px rgba(139, 92, 246, 0.3); transform: scale(1); }
  50% { box-shadow: 0 0 28px rgba(17, 150, 127, 0.5); transform: scale(1.1); }
}

.lm-message {
  text-align: center;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.lm-main {
  font-size: 15px;
  font-weight: 700;
  color: var(--color-text-strong);
  background: var(--gradient-aurora);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.lm-sub {
  font-size: 13px;
  color: var(--color-text-medium);
}

.lm-tip {
  margin-top: 8px;
  padding: 8px 16px;
  font-size: 12px;
  color: var(--color-primary-dark);
  background: rgba(17, 150, 127, 0.06);
  border-radius: var(--radius-pill);
  border: 1px solid rgba(17, 150, 127, 0.1);
  max-width: 300px;
  line-height: 1.5;
}

/* 底部跳动光点 */
.lm-dots {
  display: flex;
  gap: 8px;
  margin-top: 4px;
}

.lm-dots span {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--gradient-aurora);
  animation: dot-bounce 1.4s infinite ease-in-out;
  box-shadow: 0 0 8px rgba(139, 92, 246, 0.4);
}

.lm-dots span:nth-child(1) { animation-delay: 0s; }
.lm-dots span:nth-child(2) { animation-delay: 0.2s; }
.lm-dots span:nth-child(3) { animation-delay: 0.4s; }

@keyframes dot-bounce {
  0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
  40% { transform: scale(1.3); opacity: 1; }
}
</style>
