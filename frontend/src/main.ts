import { createApp } from 'vue'
import App from './App.vue'
import router from './router/index.ts'
import { OpenAPI } from '@/api'

import Antd from 'ant-design-vue'
import 'ant-design-vue/dist/reset.css'

// 配置API基础URL
OpenAPI.BASE = 'http://localhost:8000'

createApp(App).use(Antd).use(router).mount('#app')
