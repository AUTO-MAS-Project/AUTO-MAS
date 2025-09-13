import { createApp } from 'vue'
import App from './App.vue'
import router from './router/index.ts'
import { OpenAPI } from '@/api'

import Antd from 'ant-design-vue'
import 'ant-design-vue/dist/reset.css'
import zhCN from 'ant-design-vue/es/locale/zh_CN'
import dayjs from 'dayjs'
import 'dayjs/locale/zh-cn'

// 导入日志系统
import { logger } from '@/utils/logger'

// 导入镜像管理器
import { mirrorManager } from '@/utils/mirrorManager'

// 配置dayjs中文本地化
dayjs.locale('zh-cn')

import { API_ENDPOINTS } from '@/config/mirrors'

// 配置API基础URL
OpenAPI.BASE = API_ENDPOINTS.local

// 记录应用启动
logger.info('前端应用开始初始化')
logger.info(`API基础URL: ${OpenAPI.BASE}`)

// 初始化镜像管理器（异步）
mirrorManager.initialize().then(() => {
  logger.info('镜像管理器初始化完成')
}).catch((error) => {
  logger.error('镜像管理器初始化失败:', error)
})

// 创建应用实例
const app = createApp(App)

// 注册插件
app.use(Antd)
app.use(router)

// 全局错误处理
app.config.errorHandler = (err, instance, info) => {
  logger.error('Vue应用错误:', err, '组件信息:', info)
}

// 挂载应用
app.mount('#app')

logger.info('前端应用初始化完成')
