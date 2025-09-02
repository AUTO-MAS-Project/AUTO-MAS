import { createApp } from 'vue'
import App from './App.vue'
import router from './router/index.ts'
import { OpenAPI } from '@/api'

import Antd from 'ant-design-vue'
import 'ant-design-vue/dist/reset.css'
import zhCN from 'ant-design-vue/es/locale/zh_CN'
import dayjs from 'dayjs'
import 'dayjs/locale/zh-cn'

// 配置dayjs中文本地化
dayjs.locale('zh-cn')

import { API_ENDPOINTS } from '@/config/mirrors'

// 配置API基础URL
OpenAPI.BASE = API_ENDPOINTS.local

// 创建应用实例
const app = createApp(App)

// 注册插件
app.use(Antd)
app.use(router)

// 挂载应用
app.mount('#app')
