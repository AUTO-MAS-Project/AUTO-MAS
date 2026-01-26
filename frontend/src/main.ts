import { createApp } from 'vue'
import App from './App.vue'
import router from './router/index.ts'
import { OpenAPI } from '@/api'

import Antd from 'ant-design-vue'
import 'ant-design-vue/dist/reset.css'
import dayjs from 'dayjs'
import 'dayjs/locale/zh-cn'

// 导入日志系统
const logger = window.electronAPI.getLogger('前端主入口')

// 导入WebSocket消息监听组件
import WebSocketMessageListener from '@/components/WebSocketMessageListener.vue'

// 正常路由：执行完整初始化
// 配置dayjs中文本地化
dayjs.locale('zh-cn')

// 从 Electron 获取 API 端点并设置 OpenAPI.BASE
if (window.electronAPI?.getApiEndpoint) {
  window.electronAPI.getApiEndpoint('local')
    .then(endpoint => {
      OpenAPI.BASE = endpoint
      logger.info('前端应用开始初始化')
      logger.info(`API基础URL: ${OpenAPI.BASE}`)
    })
    .catch(error => {
      logger.error('获取 API 端点失败，使用默认值:', error)
      OpenAPI.BASE = 'http://localhost:36163'
      logger.info(`API基础URL (默认): ${OpenAPI.BASE}`)
    })
} else {
  // 非 Electron 环境，使用默认值
  OpenAPI.BASE = 'http://localhost:36163'
  logger.info('前端应用开始初始化')
  logger.info(`API基础URL (默认): ${OpenAPI.BASE}`)
}

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

// 注册WebSocket消息监听组件
app.component('WebSocketMessageListener', WebSocketMessageListener)

logger.info('前端应用初始化完成')
