import { createRouter, createWebHistory } from 'vue-router'
import login from '@/views/login.vue'
import home from '@/views/home.vue'

// 路由级代码分割：业务视图按需加载，显著减小首屏 JS 体积
const overview = () => import('@/views/overview.vue')
const profile = () => import('@/views/profile.vue')
const resources = () => import('@/views/resources.vue')
const learningPath = () => import('@/views/learning-path.vue')
const tutor = () => import('@/views/tutor.vue')
const assessment = () => import('@/views/assessment.vue')
const codeAssist = () => import('@/views/code-assist.vue')

import { useUserStore } from '@/stores/user'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: login },
    {
      path: '/',
      component: home,
      children: [
        { path: '', redirect: '/overview' },
        { path: 'overview', component: overview },
        { path: 'profile', component: profile },
        { path: 'resources', component: resources },
        { path: 'learning-path', component: learningPath },
        { path: 'tutor', component: tutor },
        { path: 'assessment', component: assessment },
        { path: 'code-assist', component: codeAssist },
      ],
    },
  ],
})

router.beforeEach((to, from, next) => {
  const userStore = useUserStore()
  if (to.path !== '/login' && !userStore.hasToken) {
    next('/login')
  } else if (to.path === '/login' && userStore.hasToken) {
    next('/overview')
  } else {
    next()
  }
})

export default router
