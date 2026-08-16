import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
export default defineConfig(async ({ mode }) => {
  const plugins = [vue()]
  if (mode === 'development') {
    const { default: vueDevTools } = await import('vite-plugin-vue-devtools')
    plugins.push(vueDevTools())
  }
  return {
  plugins,
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  build: {
    rollupOptions: {
      output: {
        // 稳定的 vendor 分包：框架/渲染/HTTP 各自独立 chunk，
        // 业务代码更新时框架部分保持缓存命中
        manualChunks: {
          'vue-vendor': ['vue', 'vue-router', 'pinia', 'pinia-plugin-persistedstate'],
          'markdown-vendor': ['marked', 'dompurify'],
          'http-vendor': ['axios', 'nprogress'],
        },
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/uploads': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
    },
  },
  }
})
