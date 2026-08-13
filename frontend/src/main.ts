import '@/utils/browserDevElectronAPI'
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import * as Sentry from '@sentry/vue'
import '@/styles/inspira.css'
import App from './App.vue'
import router from './router/index.ts'
import { OpenAPI } from '@/api'
import { configureLocalMonaco } from '@/utils/monaco'
import { sanitizeSentryEvent } from '@/utils/sentry'

configureLocalMonaco()

import Antd, { message } from 'ant-design-vue'
import 'ant-design-vue/dist/reset.css'
import '@/styles/scrollbar.css'
import dayjs from 'dayjs'
import 'dayjs/locale/zh-cn'

const TITLE_BAR_HEIGHT = 32
const MESSAGE_TOP_GAP = 8

// 静态 message 默认从窗口顶部 8px 开始，会覆盖无边框窗口的标题栏。
message.config({ top: `${TITLE_BAR_HEIGHT + MESSAGE_TOP_GAP}px` })

// 导入日志系统
const logger = window.electronAPI.getLogger('前端主入口')
if (
  (window as Window & { __AUTO_MAS_BROWSER_DEV_MODE__?: boolean }).__AUTO_MAS_BROWSER_DEV_MODE__
) {
  OpenAPI.BASE = 'http://localhost:36163'
}

// 导入WebSocket消息监听组件
import WebSocketMessageListener from '@/components/WebSocketMessageListener.vue'

// 正常路由：执行完整初始化
// 配置dayjs中文本地化
dayjs.locale('zh-cn')

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
app.use(createPinia())
app.use(Antd)
app.use(router)

// 全局错误处理
app.config.errorHandler = (err, instance, info) => {
  const errorMsg = err instanceof Error ? err.message : String(err)
  logger.error(`Vue应用错误: ${errorMsg}, 组件信息: ${info}`)
}

Sentry.init({
  app,
  dsn: 'https://6ad15803ac77e44f24f46f2dfa599def@o4511881138733056.ingest.us.sentry.io/4511902510678016',
  release: `auto-mas@${import.meta.env.VITE_APP_VERSION}`,
  environment: import.meta.env.DEV ? 'development' : 'production',
  sendDefaultPii: false,
  dataCollection: {
    userInfo: false,
    cookies: false,
    httpHeaders: {
      request: false,
      response: false,
    },
    httpBodies: [],
    urlQueryParams: false,
    graphQL: {
      document: false,
      variables: false,
    },
    genAI: {
      inputs: false,
      outputs: false,
    },
    databaseQueryData: false,
    stackFrameVariables: false,
    frameContextLines: 0,
  },
  attachProps: false,
  integrations: [
    Sentry.browserTracingIntegration({ router }),
    Sentry.breadcrumbsIntegration({
      console: false,
      dom: false,
      history: false,
    }),
  ],
  tracesSampleRate: 0.1,
  tracePropagationTargets: [/^http:\/\/(?:localhost|127\.0\.0\.1):36163\//],
  beforeSend: sanitizeSentryEvent,
  beforeSendTransaction: sanitizeSentryEvent,
})

// 挂载应用
app.mount('#app')

// 注册WebSocket消息监听组件
app.component('WebSocketMessageListener', WebSocketMessageListener)

logger.info('前端应用初始化完成')
