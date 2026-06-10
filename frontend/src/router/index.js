import { createRouter, createWebHistory } from 'vue-router'
import login from '@/views/login.vue'
import home from '@/views/home.vue'
import profile from '@/views/profile.vue'
import resources from '@/views/resources.vue'
import learningPath from '@/views/learning-path.vue'
import tutor from '@/views/tutor.vue'
import assessment from '@/views/assessment.vue'

import { useUserStore } from '@/stores/user'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: login },
    {
      path: '/',
      component: home,
      children: [
        { path: '', redirect: '/profile' },
        { path: 'profile', component: profile },
        { path: 'resources', component: resources },
        { path: 'learning-path', component: learningPath },
        { path: 'tutor', component: tutor },
        { path: 'assessment', component: assessment },
      ],
    },
  ],
})

router.beforeEach((to, from, next) => {
  const userStore = useUserStore()
  if (to.path !== '/login' && !userStore.hasToken) {
    next('/login')
  } else if (to.path === '/login' && userStore.hasToken) {
    next('/profile')
  } else {
    next()
  }
})

export default router
