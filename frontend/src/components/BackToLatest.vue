<script setup>
defineProps({
  unread: { type: Number, default: 0 },
})
defineEmits(['click'])
</script>

<template>
  <transition name="back-latest">
    <button
      class="back-to-latest"
      :aria-label="unread > 0 ? `${unread} 条新消息，回到最新` : '回到最新'"
      @click="$emit('click')"
    >
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="6 9 12 15 18 9"/>
      </svg>
      <span v-if="unread > 0" class="back-latest-badge">{{ unread > 99 ? '99+' : unread }}</span>
    </button>
  </transition>
</template>

<style scoped>
.back-to-latest {
  position: absolute;
  right: 24px;
  bottom: 24px;
  z-index: 20;
  width: 40px;
  height: 40px;
  border: 1px solid var(--color-border);
  border-radius: 50%;
  background: var(--color-bg-base);
  color: var(--color-text-medium);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 4px 16px rgba(15, 23, 42, 0.12);
  transition: color 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease;
}

.back-to-latest:hover {
  color: var(--color-primary-dark);
  border-color: var(--color-primary);
  box-shadow: 0 6px 20px rgba(17, 150, 127, 0.25);
  transform: translateY(-1px);
}

.back-latest-badge {
  position: absolute;
  top: -6px;
  right: -6px;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border-radius: 999px;
  background: linear-gradient(135deg, #f43f5e, #e11d48);
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  line-height: 18px;
  text-align: center;
  box-shadow: 0 2px 6px rgba(225, 29, 72, 0.4);
}

.back-latest-enter-active { transition: opacity 0.25s ease, transform 0.25s ease; }
.back-latest-leave-active { transition: opacity 0.2s ease, transform 0.2s ease; }
.back-latest-enter-from,
.back-latest-leave-to { opacity: 0; transform: translateY(8px); }
</style>
