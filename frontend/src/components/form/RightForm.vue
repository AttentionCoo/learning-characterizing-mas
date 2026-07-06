<script setup>
import { ref } from 'vue'
import LoginForm from './LoginForm.vue'
import RegisterForm from './RegisterForm.vue'

const isLogin = ref(true)
</script>

<template>
  <div class="content">
    <transition name="flip" mode="out-in">
      <div :key="isLogin ? 'login' : 'register'" class="form-wrapper glass prism-border">
        <LoginForm v-if="isLogin" />
        <RegisterForm v-else />
        <div class="switch-text" @click="isLogin = !isLogin">
          <span v-if="isLogin">新用户？<span class="switch-highlight">去注册</span></span>
          <span v-else>已有帐号？<span class="switch-highlight">去登录</span></span>
        </div>
      </div>
    </transition>
  </div>
</template>

<style scoped lang="scss">
.flip-enter-from {
  opacity: 0;
  transform: perspective(600px) rotateY(-30deg) scale(0.95);
}

.flip-leave-to {
  opacity: 0;
  transform: perspective(600px) rotateY(30deg) scale(0.95);
}

.flip-enter-active,
.flip-leave-active {
  transition: all 0.35s cubic-bezier(0.16, 1, 0.3, 1);
}

.content {
  width: min(100%, 420px);
  padding: 0;
}

.form-wrapper {
  padding: 28px 24px;
  border-radius: var(--radius-xl);
}

.switch-text {
  margin-top: 1rem;
  text-align: center;
  color: var(--color-text-medium);
  cursor: pointer;
  font-size: 14px;
  transition: all 0.25s ease;

  &:hover {
    color: var(--color-text-strong);
  }
}

.switch-highlight {
  color: var(--color-primary);
  font-weight: 700;
  position: relative;

  &::after {
    content: '';
    position: absolute;
    bottom: -2px;
    left: 0;
    width: 0;
    height: 2px;
    background: var(--gradient-aurora);
    border-radius: 1px;
    transition: width 0.3s cubic-bezier(0.16, 1, 0.3, 1);
  }

  .switch-text:hover &::after {
    width: 100%;
  }
}

@media (max-width: 960px) {
  .content {
    width: min(100%, 460px);
  }
}

@media (max-width: 640px) {
  .content {
    width: 100%;
  }
}
</style>