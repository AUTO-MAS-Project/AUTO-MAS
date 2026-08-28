import '@/utils/browserDevElectronAPI'
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import '@/styles/inspira.css'
import App from './App.vue'
import router from './router/index.ts'
import { OpenAPI } from '@/api'
import { configureLocalMonaco } from '@/utils/monaco'
import { getConfig } from '@/utils/config'
import { configureSentry } from '@/utils/sentry'

import Antd, { message } from 'ant-design-vue'
import 'ant-design-vue/dist/reset.css'
import '@/styles/scrollbar.css'
import '@/styles/formSection.css'
import dayjs from 'dayjs'
import 'dayjs/locale/zh-cn'

const TITLE_BAR_HEIGHT = 32
const MESSAGE_TOP_GAP = 8

// 静态 message 默认从窗口顶部 8px 开始，会覆盖无边框窗口的标题栏。
message.config({ top: `${TITLE_BAR_HEIGHT + MESSAGE_TOP_GAP}px` })

// 导入日志系统
const logger = window.electronAPI.getLogger('前端主入口')

// Monaco 预加载推迟到浏览器空闲时段，避免与首屏渲染争抢主线程
const preloadMonaco = () => {
  void configureLocalMonaco().catch(error => {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.warn(`Monaco 预加载失败，将在下次使用时重试: ${errorMsg}`)
  })
}

if (typeof window.requestIdleCallback === 'function') {
  window.requestIdleCallback(preloadMonaco, { timeout: 5000 })
} else {
  window.setTimeout(preloadMonaco, 2000)
}

if (
  (window as Window & { __AUTO_MAS_BROWSER_DEV_MODE__?: boolean }).__AUTO_MAS_BROWSER_DEV_MODE__
) {
  OpenAPI.BASE = 'http://127.0.0.1:36163'
}

// 导入WebSocket消息监听组件
import WebSocketMessageListener from '@/components/WebSocketMessageListener.vue'
import { bootstrapRealtimeResidents } from '@/bootstrap/realtimeResidents'
import { initializeAppLifecycle } from '@/composables/useAppLifecycle'

// 正常路由：执行完整初始化
// 配置dayjs中文本地化
dayjs.locale('zh-cn')

// 应用级常驻订阅与生命周期协调器必须早于首个主 WebSocket 连接注册（幂等）
bootstrapRealtimeResidents()
initializeAppLifecycle()

// 从 Electron 获取 API 端点并设置 OpenAPI.BASE
if (window.electronAPI?.getApiEndpoint) {
  window.electronAPI
    .getApiEndpoint('local')
    .then(endpoint => {
      OpenAPI.BASE = endpoint
      logger.info('前端应用开始初始化')
      logger.info(`API基础URL: ${OpenAPI.BASE}`)
    })
    .catch(error => {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`获取 API 端点失败，使用默认值: ${errorMsg}`)
      OpenAPI.BASE = 'http://127.0.0.1:36163'
      logger.info(`API基础URL (默认): ${OpenAPI.BASE}`)
    })
} else {
  // 非 Electron 环境，使用默认值
  OpenAPI.BASE = 'http://127.0.0.1:36163'
  logger.info('前端应用开始初始化')
  logger.info(`API基础URL (默认): ${OpenAPI.BASE}`)
}

// 创建应用实例
const app = createApp(App)

// 注册插件
app.use(createPinia())
app.use(Antd)
app.use(router)

// 全局错误处理
app.config.errorHandler = (err, instance, info) => {
  const errorMsg = err instanceof Error ? err.message : String(err)
  logger.error(`Vue应用错误: ${errorMsg}, 组件信息: ${info}`)
}

const bootstrap = async () => {
  const frontendConfig = await getConfig()
  configureSentry(app, router, frontendConfig.Function?.IfEnableTelemetry !== false)

  // 挂载应用
  app.mount('#app')

  // 注册WebSocket消息监听组件
  app.component('WebSocketMessageListener', WebSocketMessageListener)

  logger.info('前端应用初始化完成')
}

void bootstrap()
