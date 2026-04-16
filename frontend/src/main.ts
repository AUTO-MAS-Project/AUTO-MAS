import { createApp } from 'vue'
import Antd from 'ant-design-vue'
import dayjs from 'dayjs'
import 'ant-design-vue/dist/reset.css'
import 'dayjs/locale/zh-cn'

import App from './App.vue'
import router from './router/index.ts'
import { apiRuntime } from '@/api'
import WebSocketMessageListener from '@/components/WebSocketMessageListener.vue'

const logger = window.electronAPI.getLogger('frontend-main')

dayjs.locale('zh-cn')

const defaultApiBaseUrl = 'http://localhost:36163'

if (window.electronAPI?.getApiEndpoint) {
  window.electronAPI
    .getApiEndpoint('local')
    .then(endpoint => {
      apiRuntime.baseUrl = endpoint
      logger.info(`API base URL: ${apiRuntime.baseUrl}`)
    })
    .catch(error => {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`Failed to get API endpoint, fallback to default: ${errorMsg}`)
      apiRuntime.baseUrl = defaultApiBaseUrl
      logger.info(`API base URL: ${apiRuntime.baseUrl}`)
    })
} else {
  apiRuntime.baseUrl = defaultApiBaseUrl
  logger.info(`API base URL: ${apiRuntime.baseUrl}`)
}

const app = createApp(App)

app.use(Antd)
app.use(router)

app.config.errorHandler = (err, instance, info) => {
  const errorMsg = err instanceof Error ? err.message : String(err)
  logger.error(`Vue error: ${errorMsg}, info: ${info}`)
}

app.mount('#app')
app.component('WebSocketMessageListener', WebSocketMessageListener)

logger.info('Frontend app initialized')
