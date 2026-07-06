<script setup>
import { computed, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { useThemeStore } from '@/stores/theme'
import { logoutAPI } from '@/api/user'
import AppAvatar from '@/components/AppAvatar.vue'
import UserDialog from '@/components/UserDialog.vue'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()
const themeStore = useThemeStore()

const sidebarCollapsed = ref(true)
const showUserDialog = ref(false)
let hoverTimer = null

const navItems = [
  {
    path: '/profile',
    label: '学习画像',
    icon: 'profile',
    desc: '脑卒中画像构建',
  },
  {
    path: '/resources',
    label: '资源生成',
    icon: 'resources',
    desc: '脑卒中资源生成',
  },
  {
    path: '/learning-path',
    label: '学习路径',
    icon: 'path',
    desc: '脑卒中路径规划',
  },
  {
    path: '/tutor',
    label: '智能辅导',
    icon: 'tutor',
    desc: '脑卒中答疑解惑',
  },
  {
    path: '/assessment',
    label: '学习评估',
    icon: 'assessment',
    desc: '脑卒中效果评估',
  },
]

const activeNav = computed(() => {
  return navItems.find((item) => route.path.startsWith(item.path))?.path || '/profile'
})

async function handleLogout() {
  try {
    await logoutAPI()
  } catch {
    // ignore
  }
  userStore.reset()
  router.push('/login')
}

function toggleSidebar() {
  sidebarCollapsed.value = !sidebarCollapsed.value
}

function handleMouseEnter() {
  if (hoverTimer) {
    clearTimeout(hoverTimer)
    hoverTimer = null
  }
  if (sidebarCollapsed.value) {
    sidebarCollapsed.value = false
  }
}

function handleMouseLeave() {
  if (!sidebarCollapsed.value) {
    hoverTimer = setTimeout(() => {
      sidebarCollapsed.value = true
    }, 300)
  }
}
</script>

<template>
  <div class="app-layout" :class="{ collapsed: sidebarCollapsed }">
    <aside class="sidebar" @mouseenter="handleMouseEnter" @mouseleave="handleMouseLeave">
      <!-- 侧边栏顶部渐变装饰线 -->
      <div class="sidebar-glow-line"></div>

      <div class="sidebar-header">
        <div class="logo" @click="toggleSidebar">
          <div class="logo-icon">
            <svg width="28" height="28" viewBox="0 0 32 32" fill="none">
              <rect width="32" height="32" rx="8" fill="url(#logo-grad)" />
              <path d="M8 16L14 22L24 10" stroke="white" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
              <defs>
                <linearGradient id="logo-grad" x1="0" y1="0" x2="32" y2="32">
                  <stop stop-color="#11967f"/>
                  <stop offset="0.5" stop-color="#0ea5e9"/>
                  <stop offset="1" stop-color="#8b5cf6"/>
                </linearGradient>
              </defs>
            </svg>
          </div>
          <transition name="fade-text">
            <span v-if="!sidebarCollapsed" class="logo-text">辅助学习系统</span>
          </transition>
        </div>
        <button class="toggle-btn" @click.stop="toggleSidebar" :title="sidebarCollapsed ? '展开菜单' : '收起菜单'">
          <svg :class="{ rotated: !sidebarCollapsed }" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="15 18 9 12 15 6"/>
          </svg>
        </button>
      </div>

      <nav class="sidebar-nav">
        <router-link
          v-for="(item, idx) in navItems"
          :key="item.path"
          :to="item.path"
          class="nav-item"
          :class="{ active: activeNav === item.path }"
          :title="sidebarCollapsed ? item.label : ''"
          :style="{ animationDelay: `${idx * 0.05}s` }"
        >
          <div class="nav-icon">
            <svg v-if="item.icon === 'profile'" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
              <circle cx="12" cy="7" r="4"/>
            </svg>
            <svg v-else-if="item.icon === 'resources'" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
              <polyline points="14 2 14 8 20 8"/>
              <line x1="16" y1="13" x2="8" y2="13"/>
              <line x1="16" y1="17" x2="8" y2="17"/>
              <polyline points="10 9 9 9 8 9"/>
            </svg>
            <svg v-else-if="item.icon === 'path'" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="10"/>
              <polyline points="12 6 12 12 16 14"/>
            </svg>
            <svg v-else-if="item.icon === 'tutor'" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
            </svg>
            <svg v-else-if="item.icon === 'assessment'" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="18" y1="20" x2="18" y2="10"/>
              <line x1="12" y1="20" x2="12" y2="4"/>
              <line x1="6" y1="20" x2="6" y2="14"/>
            </svg>
          </div>
          <transition name="fade-text">
            <div v-if="!sidebarCollapsed" class="nav-text">
              <span class="nav-label">{{ item.label }}</span>
              <span class="nav-desc">{{ item.desc }}</span>
            </div>
          </transition>
          <!-- 活跃态光轨 -->
          <div v-if="activeNav === item.path" class="nav-active-glow"></div>
        </router-link>
      </nav>

      <div class="sidebar-footer">
        <button class="theme-toggle" @click="themeStore.toggle()" :title="themeStore.dark ? '浅色模式' : '深色模式'">
          <svg v-if="themeStore.dark" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="5"/>
            <line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/>
            <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>
            <line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/>
            <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
          </svg>
          <svg v-else width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
          </svg>
          <transition name="fade-text">
            <span v-if="!sidebarCollapsed">{{ themeStore.dark ? '浅色模式' : '深色模式' }}</span>
          </transition>
        </button>

        <div class="user-section" @click="showUserDialog = true">
          <AppAvatar :src="userStore.image" :name="userStore.name" :size="36" />
          <transition name="fade-text">
            <div v-if="!sidebarCollapsed" class="user-info">
              <span class="user-name">{{ userStore.name || '用户' }}</span>
              <span class="user-logout" @click.stop="handleLogout">退出登录</span>
            </div>
          </transition>
        </div>

        <UserDialog v-if="showUserDialog" :visible="showUserDialog" @close="showUserDialog = false" @logout="handleLogout" />
      </div>
    </aside>

    <main class="main-content">
      <router-view v-slot="{ Component }">
        <transition name="page-dreamy" mode="out-in">
          <keep-alive>
            <component :is="Component" />
          </keep-alive>
        </transition>
      </router-view>
    </main>
  </div>
</template>

<style scoped lang="scss">
.app-layout {
  display: flex;
  height: 100vh;
  overflow: hidden;
  background: var(--color-bg-base);
  position: relative;
  z-index: 1;
}

// ── 侧边栏 ──
.sidebar {
  width: 260px;
  min-width: 260px;
  display: flex;
  flex-direction: column;
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
  border-right: 1px solid var(--glass-border);
  transition: width 0.3s cubic-bezier(0.4, 0, 0.2, 1), min-width 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  overflow: hidden;
  position: relative;
  z-index: 20;

  .collapsed & {
    width: 72px;
    min-width: 72px;
  }
}

// 顶部渐变装饰线
.sidebar-glow-line {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 2px;
  background: var(--gradient-aurora-flow);
  background-size: 300% 100%;
  animation: aurora-flow 6s ease infinite;
  z-index: 1;
  opacity: 0.7;
}

@keyframes aurora-flow {
  0% { background-position: 0% 50%; }
  50% { background-position: 100% 50%; }
  100% { background-position: 0% 50%; }
}

.sidebar-header {
  padding: 20px 16px 16px;
  border-bottom: 1px solid var(--color-border-light);
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.toggle-btn {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: var(--radius-md);
  background: var(--color-ghost-hover);
  color: var(--color-text-medium);
  cursor: pointer;
  transition: all var(--transition-fast);

  svg {
    transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);

    &.rotated {
      transform: rotate(180deg);
    }
  }

  &:hover {
    background: var(--color-hover-bg);
    color: var(--color-text-strong);
    transform: scale(1.05);
    box-shadow: var(--glow-dreamy);
  }

  &:active {
    transform: scale(0.95);
  }
}

.logo {
  display: flex;
  align-items: center;
  gap: 12px;
  cursor: pointer;
  user-select: none;
  padding: 4px;
  border-radius: var(--radius-md);
  transition: background var(--transition-fast);

  &:hover {
    background: var(--color-ghost-hover);
  }
}

.logo-icon {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: transform var(--transition-bounce);

  .logo:hover & {
    transform: scale(1.08) rotate(-5deg);
  }
}

.logo-text {
  font-size: 1.35rem;
  font-weight: 800;
  background: var(--gradient-aurora);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  letter-spacing: -0.02em;
  white-space: nowrap;
}

.sidebar-nav {
  flex: 1;
  padding: 12px 8px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border-radius: var(--radius-md);
  text-decoration: none;
  color: var(--color-text-medium);
  transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
  position: relative;
  overflow: hidden;
  animation: fade-in-up 0.4s cubic-bezier(0.16, 1, 0.3, 1) both;

  &::before {
    content: '';
    position: absolute;
    inset: 0;
    border-radius: inherit;
    background: linear-gradient(135deg, rgba(139, 92, 246, 0.08), rgba(17, 150, 127, 0.06));
    opacity: 0;
    transition: opacity 0.35s ease;
  }

  &:hover {
    background: var(--color-hover-bg);
    color: var(--color-text-strong);
    transform: translateX(4px);

    &::before { opacity: 1; }

    .nav-icon {
      transform: scale(1.08);
    }
  }

  &.active {
    background: var(--color-active-bg);
    color: var(--color-primary-dark);
    box-shadow: var(--glow-dreamy);

    .nav-icon {
      color: var(--color-primary);
      background: rgba(17, 150, 127, 0.1);
      box-shadow: 0 0 12px rgba(17, 150, 127, 0.2);
    }

    .nav-label {
      font-weight: 700;
      color: var(--color-primary-dark);
    }
  }

  .collapsed & {
    justify-content: center;
    padding: 10px;

    &:hover {
      transform: translateX(0);
    }
  }
}

// 活跃态光轨
.nav-active-glow {
  position: absolute;
  right: 0;
  top: 15%;
  bottom: 15%;
  width: 3px;
  border-radius: 3px 0 0 3px;
  background: var(--gradient-aurora);
  box-shadow: 0 0 12px rgba(139, 92, 246, 0.5), 0 0 24px rgba(17, 150, 127, 0.3);
  animation: glow-pulse 2s ease-in-out infinite;
}

@keyframes glow-pulse {
  0%, 100% { box-shadow: 0 0 8px rgba(139, 92, 246, 0.4), 0 0 16px rgba(17, 150, 127, 0.2); }
  50% { box-shadow: 0 0 16px rgba(139, 92, 246, 0.6), 0 0 32px rgba(14, 165, 233, 0.35); }
}

.nav-icon {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: var(--radius-md);
  transition: all var(--transition-bounce);

  .collapsed & {
    width: 40px;
    height: 40px;
  }
}

.nav-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
  white-space: nowrap;
}

.nav-label {
  font-size: 14px;
  font-weight: 600;
  line-height: 1.3;
  transition: color var(--transition-fast);
}

.nav-desc {
  font-size: 11px;
  color: var(--color-text-weak);
  line-height: 1.3;
  margin-top: 1px;
}

.sidebar-footer {
  padding: 12px 8px;
  border-top: 1px solid var(--color-border-light);
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;

  .collapsed & {
    align-items: center;
    padding: 12px 4px;
  }
}

.theme-toggle {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border: none;
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--color-text-medium);
  cursor: pointer;
  font: inherit;
  font-size: 13px;
  transition: all var(--transition-fast);
  white-space: nowrap;

  &:hover {
    background: var(--color-ghost-hover);
    color: var(--color-text-strong);
  }

  .collapsed & {
    justify-content: center;
    padding: 8px;

    span {
      display: none !important;
    }
  }
}

.user-section {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--transition-fast);

  &:hover {
    background: var(--color-ghost-hover);
  }

  .collapsed & {
    justify-content: center;
    padding: 8px;

    .user-info {
      display: none !important;
    }
  }
}

.user-info {
  display: flex;
  flex-direction: column;
  min-width: 0;
  white-space: nowrap;
}

.user-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-strong);
}

.user-logout {
  font-size: 11px;
  color: var(--color-text-weak);
  cursor: pointer;
  transition: color var(--transition-fast);

  &:hover {
    color: var(--color-red);
  }

  .user-section:hover & {
    color: var(--color-red);
  }
}

.main-content {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  position: relative;
  z-index: 1;
}

// ── 过渡动画 ──
.fade-text-enter-active,
.fade-text-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}

.fade-text-enter-from,
.fade-text-leave-to {
  opacity: 0;
  transform: translateX(-8px);
}

// 梦幻页面切换
.page-dreamy-enter-active {
  transition: opacity 0.35s cubic-bezier(0.16, 1, 0.3, 1),
              transform 0.35s cubic-bezier(0.16, 1, 0.3, 1);
}

.page-dreamy-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.page-dreamy-enter-from {
  opacity: 0;
  transform: translateY(16px) scale(0.98);
}

.page-dreamy-leave-to {
  opacity: 0;
  transform: translateY(-6px) scale(0.99);
}

@media (max-width: 768px) {
  .sidebar {
    width: 72px;
    min-width: 72px;
  }

  .nav-text,
  .logo-text,
  .user-info,
  .theme-toggle span {
    display: none !important;
  }

  .toggle-btn {
    display: none;
  }

  .sidebar-header {
    justify-content: center;
    padding: 16px 8px;
  }

  .sidebar-nav {
    padding: 8px 4px;
  }

  .nav-item {
    justify-content: center;
    padding: 10px;

    &:hover {
      transform: translateX(0);
    }
  }

  .sidebar-footer {
    align-items: center;
    padding: 12px 4px;
  }

  .theme-toggle,
  .user-section {
    justify-content: center;
    padding: 8px;

    span {
      display: none !important;
    }
  }
}
</style>
