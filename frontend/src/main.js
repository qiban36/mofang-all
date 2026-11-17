// 应用入口：挂载 Vue 实例，并引入全局样式
import { createApp } from 'vue'

// Bootstrap 5 的 CSS（只用到栅格 / 卡片 / 按钮 / 表单控件这些样式，不需要它的 JS）
import 'bootstrap/dist/css/bootstrap.min.css'

// 项目自己的全局样式（页面撑满、去掉默认边距等）
import './style.css'

import App from './App.vue'

createApp(App).mount('#app')