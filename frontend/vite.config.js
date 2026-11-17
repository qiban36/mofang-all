import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// Vite 配置：只需要 Vue 插件 + 固定开发端口
// 说明：前端直接跨域访问 http://127.0.0.1:8000（后端已用 CORS 放行 localhost:5173），
// 所以这里不需要配置 proxy，后端地址集中在 src/api.js 里改。
export default defineConfig({
  plugins: [vue()],
  resolve: {
    // 与 vitest.config.js 保持一致：@ 指向 src
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  server: {
    port: 5173,
    strictPort: true
  },
  build: {
    // three 体积大且很少变，单独拆一个 chunk，浏览器可以长期缓存；
    // 业务代码改动时只需要重新下载很小的 entry chunk。
    chunkSizeWarningLimit: 900,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined
          if (id.includes('three')) return 'three'
          if (id.includes('@vue') || id.includes('/vue/')) return 'vue'
          return 'vendor'
        }
      }
    }
  }
})