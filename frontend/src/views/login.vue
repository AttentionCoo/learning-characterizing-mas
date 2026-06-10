<script setup>
defineOptions({
  name: 'LoginIndex',
})
import { ref, onMounted, onBeforeUnmount } from 'vue'
import LeftIntro from '@/components/LeftIntro.vue'
import RightForm from '@/components/form/RightForm.vue'
import { useThemeStore } from '@/stores/theme'

const themeStore = useThemeStore()

const canvasRef = ref(null)
let animId = null
let particles = []

function initParticles() {
  const canvas = canvasRef.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  const dpr = window.devicePixelRatio || 1
  canvas.width = canvas.offsetWidth * dpr
  canvas.height = canvas.offsetHeight * dpr
  ctx.scale(dpr, dpr)
  const w = canvas.offsetWidth
  const h = canvas.offsetHeight
  particles = []
  const count = Math.min(60, Math.floor((w * h) / 12000))
  for (let i = 0; i < count; i++) {
    particles.push({
      x: Math.random() * w,
      y: Math.random() * h,
      vx: (Math.random() - 0.5) * 0.4,
      vy: (Math.random() - 0.5) * 0.4,
      r: Math.random() * 2 + 1,
      opacity: Math.random() * 0.5 + 0.2,
    })
  }
  function draw() {
    ctx.clearRect(0, 0, w, h)
    const isDark = themeStore.dark
    const lineColor = isDark ? '45, 212, 191' : '17, 150, 127'
    for (let i = 0; i < particles.length; i++) {
      const p = particles[i]
      p.x += p.vx
      p.y += p.vy
      if (p.x < 0 || p.x > w) p.vx *= -1
      if (p.y < 0 || p.y > h) p.vy *= -1
      ctx.beginPath()
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2)
      ctx.fillStyle = `rgba(${lineColor}, ${p.opacity})`
      ctx.fill()
      for (let j = i + 1; j < particles.length; j++) {
        const q = particles[j]
        const dx = p.x - q.x
        const dy = p.y - q.y
        const dist = Math.sqrt(dx * dx + dy * dy)
        if (dist < 120) {
          ctx.beginPath()
          ctx.moveTo(p.x, p.y)
          ctx.lineTo(q.x, q.y)
          ctx.strokeStyle = `rgba(${lineColor}, ${0.15 * (1 - dist / 120)})`
          ctx.lineWidth = 0.6
          ctx.stroke()
        }
      }
    }
    animId = requestAnimationFrame(draw)
  }
  draw()
}

onMounted(() => { initParticles() })
onBeforeUnmount(() => { if (animId) cancelAnimationFrame(animId) })
</script>

<template>
  <div class="login-page">
    <canvas ref="canvasRef" class="particle-canvas"></canvas>
    <div class="login-orb login-orb-1"></div>
    <div class="login-orb login-orb-2"></div>
    <button type="button" class="login-theme-toggle" :title="themeStore.dark ? '切换到浅色模式' : '切换到深色模式'"
      @click="themeStore.toggle()">
      <svg v-if="themeStore.dark" xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24"
        fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="5" />
        <line x1="12" y1="1" x2="12" y2="3" />
        <line x1="12" y1="21" x2="12" y2="23" />
        <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
        <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
        <line x1="1" y1="12" x2="3" y2="12" />
        <line x1="21" y1="12" x2="23" y2="12" />
        <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
        <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
      </svg>
      <svg v-else xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none"
        stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
      </svg>
    </button>
    <div class="login-left glass">
      <LeftIntro></LeftIntro>
    </div>
    <div class="login-right">
      <RightForm></RightForm>
    </div>
  </div>
</template>

<style scoped lang="scss">
.login-page {
  position: relative;
  display: flex;
  width: 100%;
  height: 100vh;
  background: var(--color-bg-base);
  overflow: hidden;
}

.particle-canvas {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  z-index: 0;
  pointer-events: none;
}

.login-orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(80px);
  opacity: 0.35;
  z-index: 0;
  pointer-events: none;
  animation: float 8s ease-in-out infinite;
}

.login-orb-1 {
  width: 400px;
  height: 400px;
  background: var(--gradient-aurora);
  top: -120px;
  left: -80px;
  animation-delay: 0s;
}

.login-orb-2 {
  width: 350px;
  height: 350px;
  background: var(--gradient-cool);
  bottom: -100px;
  right: -60px;
  animation-delay: -4s;
}

@keyframes float {
  0%, 100% { transform: translateY(0) scale(1); }
  50% { transform: translateY(-30px) scale(1.05); }
}

.login-theme-toggle {
  position: absolute;
  top: 16px;
  right: 16px;
  z-index: 10;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-lg);
  background: var(--glass-bg);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  color: var(--color-text-medium);
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);

  &:hover {
    background: var(--color-ghost-hover);
    color: var(--color-text-strong);
    transform: scale(1.08);
    box-shadow: var(--glow-primary);
  }

  &:active {
    transform: scale(0.95);
  }
}

.login-left {
  flex: 6;
  min-width: 0;
  color: var(--color-text-strong);
  display: flex;
  flex-direction: column;
  justify-content: flex-start;
  padding: 2rem;
  border-right: 1px solid var(--glass-border);
  border-radius: 0;
  z-index: 1;
  position: relative;
}

.login-right {
  flex: 4;
  min-width: 0;
  background:
    radial-gradient(circle at top, rgba(17, 150, 127, 0.08), transparent 42%),
    linear-gradient(180deg, var(--color-bg-base), var(--color-bg-light));
  color: var(--color-text-strong);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 2rem;
  z-index: 1;
  position: relative;
}

@media (max-width: 960px) {
  .login-page {
    flex-direction: column;
  }

  .login-left {
    flex: none;
    display: none;
    min-height: 280px;
    border-right: none;
    border-bottom: 1px solid var(--glass-border);
  }

  .login-right {
    flex: 1;
    padding: 2rem 1rem;
  }

  .login-orb { display: none; }
}
</style>