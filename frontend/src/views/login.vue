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
let stars = []

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
  stars = []

  // 主粒子（连接网络）
  const count = Math.min(30, Math.floor((w * h) / 25000))
  for (let i = 0; i < count; i++) {
    particles.push({
      x: Math.random() * w,
      y: Math.random() * h,
      vx: (Math.random() - 0.5) * 0.3,
      vy: (Math.random() - 0.5) * 0.3,
      r: Math.random() * 1.5 + 0.5,
      opacity: Math.random() * 0.3 + 0.1,
      pulse: Math.random() * Math.PI * 2,
    })
  }

  // 星尘粒子（闪烁的小点）
  const starCount = Math.min(40, Math.floor((w * h) / 18000))
  for (let i = 0; i < starCount; i++) {
    stars.push({
      x: Math.random() * w,
      y: Math.random() * h,
      r: Math.random() * 1 + 0.3,
      opacity: Math.random() * 0.5 + 0.1,
      twinkleSpeed: Math.random() * 0.02 + 0.01,
      twinkleOffset: Math.random() * Math.PI * 2,
    })
  }

  let frame = 0
  function draw() {
    frame++
    ctx.clearRect(0, 0, w, h)
    const isDark = themeStore.dark
    const lineColor = isDark ? '45, 212, 191' : '17, 150, 127'
    const starColor1 = isDark ? '167, 139, 250' : '139, 92, 246'
    const starColor2 = isDark ? '45, 212, 191' : '14, 165, 233'
    const starColor3 = isDark ? '251, 191, 36' : '245, 158, 11'

    // 绘制星尘
    for (const s of stars) {
      const twinkle = Math.sin(frame * s.twinkleSpeed + s.twinkleOffset) * 0.5 + 0.5
      const alpha = s.opacity * (0.4 + twinkle * 0.6)
      const colors = [starColor1, starColor2, starColor3]
      const colorIdx = Math.floor((s.twinkleOffset / (Math.PI * 2)) * colors.length)
      const color = colors[colorIdx % colors.length]

      ctx.beginPath()
      ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2)
      ctx.fillStyle = `rgba(${color}, ${alpha})`
      ctx.fill()

      // 星尘光晕
      if (twinkle > 0.85) {
        ctx.beginPath()
        ctx.arc(s.x, s.y, s.r * 2, 0, Math.PI * 2)
        ctx.fillStyle = `rgba(${color}, ${alpha * 0.1})`
        ctx.fill()
      }
    }

    // 绘制主粒子及其连线
    for (let i = 0; i < particles.length; i++) {
      const p = particles[i]
      p.x += p.vx
      p.y += p.vy
      if (p.x < 0 || p.x > w) p.vx *= -1
      if (p.y < 0 || p.y > h) p.vy *= -1

      // 脉冲光晕
      const pulse = Math.sin(frame * 0.03 + p.pulse) * 0.3 + 0.7
      const alpha = p.opacity * pulse

      ctx.beginPath()
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2)
      ctx.fillStyle = `rgba(${lineColor}, ${alpha})`
      ctx.fill()

      // 光晕
      ctx.beginPath()
      ctx.arc(p.x, p.y, p.r * 2, 0, Math.PI * 2)
      ctx.fillStyle = `rgba(${lineColor}, ${alpha * 0.08})`
      ctx.fill()

      // 连线
      for (let j = i + 1; j < particles.length; j++) {
        const q = particles[j]
        const dx = p.x - q.x
        const dy = p.y - q.y
        const dist = Math.sqrt(dx * dx + dy * dy)
        if (dist < 100) {
          ctx.beginPath()
          ctx.moveTo(p.x, p.y)
          ctx.lineTo(q.x, q.y)
          const lineAlpha = 0.08 * (1 - dist / 100) * pulse
          ctx.strokeStyle = `rgba(${starColor1}, ${lineAlpha})`
          ctx.lineWidth = 0.4
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
    <!-- 背景视频 -->
    <div class="video-background">
      <video
        autoplay
        muted
        loop
        playsinline
        preload="auto"
      >
        <!-- 请将视频文件放入 frontend/public/videos/ 目录，然后修改 src 路径 -->
        <source src="/videos/login-bg.mp4" type="video/mp4" />

      </video>
      <div class="video-overlay"></div>
    </div>

    <canvas ref="canvasRef" class="particle-canvas"></canvas>

    <!-- 极光光球 -->
    <div class="login-orb login-orb-1"></div>
    <div class="login-orb login-orb-2"></div>
    <div class="login-orb login-orb-3"></div>
    <div class="login-orb login-orb-4"></div>

    <!-- 飘散星尘 -->
    <div class="stardust-container">
      <span v-for="n in 6" :key="n" class="stardust" :style="{
        left: `${(n * 37 + 13) % 100}%`,
        top: `${(n * 53 + 7) % 100}%`,
        animationDelay: `${n * 0.8}s`,
        animationDuration: `${3 + (n % 4)}s`,
      }"></span>
    </div>

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
  isolation: isolate;
}

// ── 背景视频 ──
.video-background {
  position: absolute;
  inset: 0;
  z-index: 0;
  overflow: hidden;

  video {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    object-fit: cover;
    filter: brightness(1.2) contrast(1.1) saturate(1.15);
  }

  .video-overlay {
    position: absolute;
    inset: 0;
    background: transparent;
  }
}

.particle-canvas {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  z-index: 1;
  pointer-events: none;
}

// ── 极光光球 ──
.login-orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(100px);
  z-index: 0;
  pointer-events: none;
  animation: float-wide 14s ease-in-out infinite;
}

.login-orb-1 {
  width: 500px; height: 500px;
  background: radial-gradient(circle, rgba(139, 92, 246, 0.15), rgba(14, 165, 233, 0.06), transparent);
  top: -18%; left: -10%;
  animation-delay: 0s;
}

.login-orb-2 {
  width: 420px; height: 420px;
  background: radial-gradient(circle, rgba(16, 185, 129, 0.12), rgba(6, 182, 212, 0.05), transparent);
  bottom: -15%; right: -8%;
  animation-delay: -5s;
}

.login-orb-3 {
  width: 300px; height: 300px;
  background: radial-gradient(circle, rgba(236, 72, 153, 0.07), rgba(139, 92, 246, 0.05), transparent);
  top: 40%; left: 55%;
  animation-delay: -9s;
}

.login-orb-4 {
  width: 250px; height: 250px;
  background: radial-gradient(circle, rgba(251, 191, 36, 0.05), rgba(245, 158, 11, 0.03), transparent);
  top: 15%; right: 25%;
  animation-delay: -12s;
}

@keyframes float-wide {
  0%, 100% { transform: translate(0, 0) scale(1); }
  25% { transform: translate(25px, -30px) scale(1.08); }
  50% { transform: translate(-15px, -10px) scale(0.94); }
  75% { transform: translate(10px, 20px) scale(1.04); }
}

// ── 飘散星尘 ──
.stardust-container {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 0;
  overflow: hidden;
}

.stardust {
  position: absolute;
  width: 3px;
  height: 3px;
  border-radius: 50%;
  background: var(--color-stardust-1);
  box-shadow: var(--glow-starlight);
  animation: particle-rise ease-out infinite;

  &:nth-child(3n) {
    width: 2px; height: 2px;
    background: var(--color-stardust-2);
  }
  &:nth-child(3n+1) {
    width: 4px; height: 4px;
    background: var(--color-stardust-3);
  }
  &:nth-child(5n) {
    width: 2px; height: 2px;
    background: var(--color-stardust-4);
  }
}

@keyframes particle-rise {
  0% { transform: translateY(0) scale(1); opacity: 0; }
  20% { opacity: 0.5; }
  100% { transform: translateY(-140px) scale(0); opacity: 0; }
}

// ── 主题切换 ──
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
    box-shadow: var(--glow-dreamy);
  }

  &:active {
    transform: scale(0.95);
  }
}

// ── 左右布局 ──
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
  z-index: 2;
  position: relative;
}

.login-right {
  flex: 4;
  min-width: 0;
  background:
    radial-gradient(circle at top, rgba(139, 92, 246, 0.05), transparent 42%),
    radial-gradient(circle at bottom right, rgba(17, 150, 127, 0.06), transparent 40%),
    linear-gradient(180deg, var(--color-bg-base), var(--color-bg-light));
  color: var(--color-text-strong);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 2rem;
  z-index: 2;
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
