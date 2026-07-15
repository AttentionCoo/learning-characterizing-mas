import { createApp } from 'vue'
import { createPinia } from 'pinia'
import piniaPersistedstate from 'pinia-plugin-persistedstate'

import App from './App.vue'
import router from './router'

// 全局注册图标组件
import UserSvg from './components/svg/UserSvg.vue'
import PasswordSvg from './components/svg/PasswordSvg.vue'
import SendSvg from './components/svg/SendSvg.vue'

import 'normalize.css'

const app = createApp(App)

const pinia = createPinia()
pinia.use(piniaPersistedstate)

app.use(pinia)
app.use(router)

// 初始化主题
import { useThemeStore } from './stores/theme'
const themeStore = useThemeStore()
themeStore.applyTheme()

app.component('UserSvg', UserSvg)
app.component('PasswordSvg', PasswordSvg)
app.component('SendSvg', SendSvg)

app.mount('#app')
