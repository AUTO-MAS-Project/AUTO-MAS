import '@/utils/browserDevElectronAPI'
import { createApp } from 'vue'
import dayjs from 'dayjs'
import 'dayjs/locale/zh-cn'
import Antd from 'ant-design-vue'
import 'ant-design-vue/dist/reset.css'
import '@/styles/inspira.css'
import '@/styles/scrollbar.css'

import App from './App.vue'
import router from './router/index.ts'
import { OpenAPI } from '@/api'
import WebSocketMessageListener from '@/components/WebSocketMessageListener.vue'
import { installPluginAPI } from '@/plugin/pluginAPI'
import { configureLocalMonaco } from '@/utils/monaco'
import { prefetchInitializationDecision } from '@/utils/initializationDecision'
import { bootstrapRealtimeResidents } from '@/bootstrap/realtimeResidents'
import { initializeAppLifecycle } from '@/composables/useAppLifecycle'

void prefetchInitializationDecision()

const logger = window.electronAPI.getLogger('前端主入口')
const preloadMonaco = () => {
  void configureLocalMonaco().catch(error => {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.warn(`Monaco 预加载失败，将在下次使用时重试: ${errorMsg}`)
  })
}

if ('requestIdleCallback' in window) {
  window.requestIdleCallback(preloadMonaco, { timeout: 5000 })
} else {
  window.setTimeout(preloadMonaco, 2000)
}
if (
  (window as Window & { __AUTO_MAS_BROWSER_DEV_MODE__?: boolean }).__AUTO_MAS_BROWSER_DEV_MODE__
) {
  OpenAPI.BASE = 'http://localhost:36163'
}

dayjs.locale('zh-cn')
installPluginAPI()
bootstrapRealtimeResidents()
initializeAppLifecycle()

if (window.electronAPI?.getApiEndpoint) {
  window.electronAPI
    .getApiEndpoint('local')
    .then(endpoint => {
      OpenAPI.BASE = endpoint
      logger.info(`API 基础地址: ${OpenAPI.BASE}`)
    })
    .catch(error => {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`获取 API 端点失败，使用默认地址: ${errorMsg}`)
      OpenAPI.BASE = 'http://localhost:36163'
    })
} else {
  OpenAPI.BASE = 'http://localhost:36163'
}

const app = createApp(App)

app.use(Antd)
app.use(router)

app.config.errorHandler = (err, _instance, info) => {
  const errorMsg = err instanceof Error ? err.message : String(err)
  logger.error(`Vue 应用错误: ${errorMsg}, 组件信息: ${info}`)
}

app.component('WebSocketMessageListener', WebSocketMessageListener)
app.mount('#app')

logger.info('前端应用初始化完成')
