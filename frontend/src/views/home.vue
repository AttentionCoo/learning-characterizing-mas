<script setup>
import { computed, ref, onMounted, onUnmounted } from 'vue'
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

const sidebarCollapsed = ref(false)
const showUserDialog = ref(false)

const navItems = [
  { path: '/profile',       label: '学习画像', icon: 'profile',    desc: '脑卒中画像构建' },
  { path: '/resources',     label: '资源生成', icon: 'resources',  desc: '脑卒中资源生成' },
  { path: '/learning-path', label: '学习路径', icon: 'path',       desc: '脑卒中路径规划' },
  { path: '/tutor',         label: '智能辅导', icon: 'tutor',      desc: '脑卒中答疑解惑' },
  { path: '/assessment',    label: '学习评估', icon: 'assessment', desc: '脑卒中效果评估' },
  { path: '/code-assist',   label: '代码辅助', icon: 'code',       desc: '医学数据分析编程' },
]

const activeNav = computed(() =>
  navItems.find((item) => route.path.startsWith(item.path))?.path || '/profile'
)

function onResize() {
  if (window.innerWidth <= 768) {
    sidebarCollapsed.value = true
  }
}

onMounted(() => {
  if (window.innerWidth <= 768) sidebarCollapsed.value = true
  window.addEventListener('resize', onResize)
})

onUnmounted(() => window.removeEventListener('resize', onResize))

async function handleLogout() {
  try { await logoutAPI() } catch {}
  userStore.reset()
  router.push('/login')
}

function toggleSidebar() {
  sidebarCollapsed.value = !sidebarCollapsed.value
}
</script>

<template>
  <div class="app-layout" :class="{ collapsed: sidebarCollapsed }">

    <!-- 移动端遮罩 -->
    <div v-if="!sidebarCollapsed" class="mobile-overlay" @click="sidebarCollapsed = true"></div>

    <!-- 移动端展开按钮（sidebar 完全隐藏时显示） -->
    <button v-if="sidebarCollapsed" class="mobile-toggle" @click="toggleSidebar" title="展开菜单">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <line x1="3" y1="6" x2="21" y2="6"/>
        <line x1="3" y1="12" x2="21" y2="12"/>
        <line x1="3" y1="18" x2="21" y2="18"/>
      </svg>
    </button>

    <aside class="sidebar" :class="{ 'mobile-open': !sidebarCollapsed }">
      <div class="sidebar-header">
        <div v-if="!sidebarCollapsed" class="logo">
          <transition name="fade-text">
            <span class="logo-text">辅助学习系统</span>
          </transition>
        </div>
        <button class="toggle-btn" @click.stop="toggleSidebar" :title="sidebarCollapsed ? '展开菜单' : '收起菜单'">
          <svg :class="{ rotated: sidebarCollapsed }" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="15 18 9 12 15 6"/>
          </svg>
        </button>
      </div>

      <nav class="sidebar-nav">
        <router-link
          v-for="item in navItems"
          :key="item.path"
          :to="item.path"
          class="nav-item"
          :class="{ active: activeNav === item.path }"
          :title="sidebarCollapsed ? item.label : ''"
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
            <svg v-else-if="item.icon === 'code'" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="16 18 22 12 16 6"/>
              <polyline points="8 6 2 12 8 18"/>
            </svg>
          </div>
          <transition name="fade-text">
            <div v-if="!sidebarCollapsed" class="nav-text">
              <span class="nav-label">{{ item.label }}</span>
              <span class="nav-desc">{{ item.desc }}</span>
            </div>
          </transition>
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
        <transition name="page-fade" mode="out-in">
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
  height: 100dvh;
  min-height: 0;
  overflow: hidden;
  background: var(--color-bg-base);
  position: relative;
  z-index: 1;
}

// ── 侧边栏 ──
.sidebar {
  position: absolute;
  left: 0;
  top: 0;
  height: 100%;
  width: 260px;
  display: flex;
  flex-direction: column;
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
  border-right: 1px solid var(--color-border-light);
  transition: width 0.25s ease;
  overflow: hidden;
  z-index: 20;

  .collapsed & {
    width: 72px;
  }
}

.sidebar-header {
  padding: 18px 14px 14px;
  border-bottom: 1px solid var(--color-border-light);
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.collapsed .sidebar-header {
  .toggle-btn {
    margin: 0 auto;
  }
}

.toggle-btn {
  flex-shrink: 0;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--color-text-medium);
  cursor: pointer;
  transition: background var(--transition-fast), color var(--transition-fast);  svg {
    transition: transform 0.25s ease;
    &.rotated { transform: rotate(180deg); }
  }

  &:hover {
    background: var(--color-hover-bg);
    color: var(--color-text-strong);
  }
}

.logo {
  display: flex;
  align-items: center;
  gap: 10px;
  user-select: none;
  min-width: 0;
}

.logo-icon {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.logo-text {
  font-size: 1.1rem;
  font-weight: 700;
  color: var(--color-text-strong);
  white-space: nowrap;
  overflow: hidden;
}

.sidebar-nav {
  flex: 1;
  padding: 10px 8px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 10px;
  border-radius: var(--radius-md);
  text-decoration: none;
  color: var(--color-text-medium);
  transition: background var(--transition-fast), color var(--transition-fast);

  &:hover {
    background: var(--color-hover-bg);
    color: var(--color-text-strong);
  }

  &.active {
    background: var(--color-active-bg);
    color: var(--color-primary-dark);

    .nav-label { font-weight: 700; }
    .nav-icon { color: var(--color-primary); }
  }

  .collapsed & {
    justify-content: center;
    padding: 9px;
  }
}

.nav-icon {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: var(--radius-md);
}

.nav-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
  white-space: nowrap;
}

.nav-label {
  font-size: 13px;
  font-weight: 500;
  line-height: 1.3;
}

.nav-desc {
  font-size: 11px;
  color: var(--color-text-weak);
  line-height: 1.3;
  margin-top: 1px;
}

.sidebar-footer {
  padding: 10px 8px;
  border-top: 1px solid var(--color-border-light);
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;

  .collapsed & {
    align-items: center;
    padding: 10px 4px;
  }
}

.theme-toggle {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border: none;
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--color-text-medium);
  cursor: pointer;
  font: inherit;
  font-size: 13px;
  white-space: nowrap;
  transition: background var(--transition-fast), color var(--transition-fast);

  &:hover {
    background: var(--color-hover-bg);
    color: var(--color-text-strong);
  }

  .collapsed & {
    justify-content: center;
    padding: 8px;
    span { display: none !important; }
  }
}

.user-section {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: background var(--transition-fast);

  &:hover { background: var(--color-hover-bg); }

  .collapsed & {
    justify-content: center;
    padding: 8px;
    .user-info { display: none !important; }
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
  &:hover { color: var(--color-red); }
}

// ── 主内容区 ──
.main-content {
  flex: 1;
  min-height: 0;
  min-width: 0;
  margin-left: 260px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  position: relative;
  z-index: 1;
  transition: margin-left 0.25s ease;

  .collapsed & { margin-left: 72px; }
}

// ── 文字淡入淡出 ──
.fade-text-enter-active,
.fade-text-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}
.fade-text-enter-from,
.fade-text-leave-to {
  opacity: 0;
  transform: translateX(-6px);
}

// ── 页面切换 ──
.page-fade-enter-active { transition: opacity 0.2s ease; }
.page-fade-leave-active { transition: opacity 0.15s ease; }
.page-fade-enter-from,
.page-fade-leave-to { opacity: 0; }

// ── 移动端 ──
@media (max-width: 768px) {
  .sidebar {
    width: 260px;
    transform: translateX(-100%);
    transition: transform 0.25s ease;
    box-shadow: none;

    &.mobile-open {
      transform: translateX(0);
      box-shadow: 4px 0 20px rgba(0, 0, 0, 0.12);
    }

    // 移动端下 collapsed class 不改变宽度
    .collapsed & { width: 260px; }
  }

  .main-content {
    margin-left: 0 !important;
    transition: none;
  }

  .mobile-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.3);
    z-index: 19;
  }

  .mobile-toggle {
    position: fixed;
    top: 12px;
    left: 12px;
    z-index: 18;
    width: 36px;
    height: 36px;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-md);
    background: var(--color-bg-light);
    color: var(--color-text-medium);
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
  }
}

// 桌面端隐藏移动端按钮
@media (min-width: 769px) {
  .mobile-overlay,
  .mobile-toggle { display: none; }
}
</style>
