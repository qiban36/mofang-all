// ESLint 9 扁平配置（ESM）
// 目标：在不改写业务代码的前提下，把项目现有风格固化下来。
import js from '@eslint/js'
import pluginVue from 'eslint-plugin-vue'
import stylistic from '@stylistic/eslint-plugin'
import globals from 'globals'

export default [
  {
    // 构建产物、依赖、工具链、覆盖率报告都不检查
    ignores: ['dist/**', 'node_modules/**', '.tools/**', 'coverage/**']
  },

  js.configs.recommended,
  ...pluginVue.configs['flat/recommended'],

  {
    plugins: {
      '@stylistic': stylistic
    },
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module'
    },
    rules: {
      // ---------------- 最佳实践 ----------------
      eqeqeq: ['error', 'smart'],
      'no-var': 'error',
      'prefer-const': 'error',
      'no-unused-vars': ['error', { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }],
      'no-console': ['warn', { allow: ['warn', 'error'] }],
      'no-debugger': 'error',

      // ---------------- 代码风格（贴合现有代码：单引号 / 无分号 / 2 空格） ----------------
      '@stylistic/quotes': ['error', 'single', { avoidEscape: true }],
      '@stylistic/semi': ['error', 'never'],
      '@stylistic/indent': ['error', 2, { SwitchCase: 1 }],
      '@stylistic/comma-dangle': ['error', 'never'],
      '@stylistic/object-curly-spacing': ['error', 'always'],
      '@stylistic/arrow-parens': ['error', 'as-needed'],

      // App.vue 是单字组件名，且模板为人工排版，交由 vue/recommended 里与正确性相关的规则把关
      'vue/multi-word-component-names': 'off'
    }
  },

  {
    // App.vue 的模板是人工排版（单行写多个属性、单行文本），关闭纯模板排版规则，
    // 避免 --fix 把整份模板重排成大 diff；与正确性相关的 vue 规则保持开启。
    files: ['**/*.vue'],
    rules: {
      'vue/max-attributes-per-line': 'off',
      'vue/singleline-html-element-content-newline': 'off',
      'vue/html-self-closing': 'off'
    }
  },

  {
    // 浏览器全局：只在 src 下
    files: ['src/**/*.{js,vue}'],
    languageOptions: {
      globals: { ...globals.browser }
    }
  },

  {
    // 调试日志模块：按设计在开发模式打印请求 / 几何中间量，这里允许 console
    files: ['src/api.js', 'src/three/**/*.js'],
    rules: {
      'no-console': 'off'
    }
  },

  {
    // Node 全局：构建 / 测试配置文件
    files: ['*.config.js', 'eslint.config.js'],
    languageOptions: {
      globals: { ...globals.node }
    }
  },

  {
    // 测试跑在 jsdom（浏览器 + Node 全局都有）
    files: ['tests/**/*.js'],
    languageOptions: {
      globals: { ...globals.node, ...globals.browser }
    }
  }
]
