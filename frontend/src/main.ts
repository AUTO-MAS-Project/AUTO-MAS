import { OpenAPI } from '@/api'

// 导入WebSocket消息监听组件
import WebSocketMessageListener from '@/components/WebSocketMessageListener.vue'
import { API_ENDPOINTS } from '@/config/mirrors'

// 导入日志系统
import { logger } from '@/utils/logger'

// 导入镜像管理器
import { mirrorManager } from '@/utils/mirrorManager'

import Antd from 'ant-design-vue'
import 'ant-design-vue/dist/reset.css'
import dayjs from 'dayjs'
import 'dayjs/locale/zh-cn'
import TDesign from 'tdesign-vue-next'
import { createApp } from 'vue'
import App from './App.vue'
import router from './router/index.ts'

// 引入组件库的少量全局样式变量
import 'tdesign-vue-next/es/style/index.css'

// 配置dayjs中文本地化
dayjs.locale('zh-cn')

// 配置API基础URL
OpenAPI.BASE = API_ENDPOINTS.local

// 记录应用启动
logger.info('前端应用开始初始化')
logger.info(`API基础URL: ${OpenAPI.BASE}`)

// 初始化镜像管理器（异步）
mirrorManager
  .initialize()
  .then(() => {
    logger.info('镜像管理器初始化完成')
  })
  .catch(error => {
    logger.error('镜像管理器初始化失败:', error)
  })

// 创建应用实例
const app = createApp(App)

// 提前初始化调度中心逻辑（使 handler 在前端初始化阶段就被注册）
try {
  // 动态导入以避免循环引用问题
  const { useSchedulerLogic } = await import('./views/scheduler/useSchedulerLogic')
  try {
    const scheduler = useSchedulerLogic()
    // 初始化并加载任务选项（不阻塞主流程，但希望尽早完成）
    scheduler.initialize()
    logger.info('Scheduler logic initialized at app startup')
  } catch (e) {
    logger.warn('Scheduler logic init failed at startup:', e)
  }
} catch (e) {
  // 如果导入失败（例如构建/路径问题），记录并继续，避免阻塞应用启动
  logger.warn('Failed to pre-import scheduler logic:', e)
}

// 注册插件
app.use(Antd)
app.use(router)
app.use(TDesign)

// 全局错误处理
app.config.errorHandler = (err, instance, info) => {
  logger.error('Vue应用错误:', err, '组件信息:', info)
}

// 挂载应用
app.mount('#app')

// 注册WebSocket消息监听组件
app.component('WebSocketMessageListener', WebSocketMessageListener)

logger.info('前端应用初始化完成')
