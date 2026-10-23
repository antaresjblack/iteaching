import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    host: true, // 同时监听 IPv4(0.0.0.0) 和 IPv6，避免 localhost/127.0.0.1 解析差异导致访问失败
    port: 5173,
    strictPort: true,
    // 代理 /api/v1 到后端，前端用相对路径请求即可，无 CORS 问题
    proxy: {
      '/api/v1': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/__tests__/setup.ts'],
    css: false,
  },
})
