<script setup>

</script>

<template>
  <div class="app-shell">
    <div class="cosmic-bg"></div>
    <div class="floating-orbs">
      <div class="orb orb-1"></div>
      <div class="orb orb-2"></div>
      <div class="orb orb-3"></div>
    </div>
    <router-view></router-view>
  </div>
</template>

<style lang="scss">
@use '@/styles/variables.scss';
@use '@/styles/common.scss';
@use '@/styles/transitions.scss';

* {
  font-family:
    ui-sans-serif,
    -apple-system,
    system-ui,
    Segoe UI,
    Helvetica,
    Apple Color Emoji,
    Arial,
    sans-serif,
    Segoe UI Emoji,
    Segoe UI Symbol;
}

html,
body {
  transition: background-color 0.3s ease, color 0.3s ease;
}

html {
  color-scheme: light;
}

[data-theme='dark'] {
  color-scheme: dark;
}

html,
body,
#app {
  background: var(--color-bg-base);
}

* {
  scrollbar-width: thin;
  scrollbar-color: var(--color-scrollbar-thumb) var(--color-scrollbar-track);
}

*::-webkit-scrollbar {
  width: 10px;
  height: 10px;
}

*::-webkit-scrollbar-track {
  background: var(--color-scrollbar-track);
}

*::-webkit-scrollbar-thumb {
  background: var(--color-scrollbar-thumb);
  border-radius: 999px;
  border: 2px solid var(--color-scrollbar-track);
}

*::-webkit-scrollbar-thumb:hover {
  background: var(--color-scrollbar-thumb-hover);
}

*::-webkit-scrollbar-corner {
  background: var(--color-scrollbar-track);
}

.app-shell {
  position: relative;
  width: 100%;
  min-height: 100vh;
  min-height: 100dvh;
  overflow-x: hidden;
  overflow-y: auto;
}

// ── 梦幻宇宙背景 ──
.cosmic-bg {
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 0;
  background: var(--gradient-nebula);
  transition: opacity 0.8s ease;
}

// ── 梦幻浮动光球 ──
.floating-orbs {
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 0;
  overflow: hidden;
}

.orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(40px);
  opacity: 0.12;
  animation: float-wide 20s ease-in-out infinite;
  will-change: transform;

  &.orb-1 {
    width: 320px;
    height: 320px;
    background: radial-gradient(circle, rgba(139, 92, 246, 0.45), transparent);
    top: -8%;
    right: 10%;
    animation-delay: 0s;
  }

  &.orb-2 {
    width: 260px;
    height: 260px;
    background: radial-gradient(circle, rgba(14, 165, 233, 0.35), transparent);
    bottom: -5%;
    left: 5%;
    animation-delay: -7s;
  }

  &.orb-3 {
    width: 200px;
    height: 200px;
    background: radial-gradient(circle, rgba(16, 185, 129, 0.3), transparent);
    top: 45%;
    left: 55%;
    animation-delay: -13s;
  }
}
</style>
