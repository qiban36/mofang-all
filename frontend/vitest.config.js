import { fileURLToPath } from 'node:url'
import { configDefaults, defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

// Vitest 配置：与 vite.config.js 对齐（Vue 插件 + @ 别名），测试跑在 jsdom 里。
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./tests/setup.js'],
    include: ['src/**/*.{test,spec}.js', 'tests/**/*.{test,spec}.js'],
    // e2e 是 Playwright 用例，不能被 Vitest 捡去跑
    exclude: [...configDefaults.exclude, 'e2e/**', 'node_modules/**'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html', 'lcov'],
      include: ['src/**/*.js'],
      exclude: ['src/main.js']
    }
  }
})
