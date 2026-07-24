import { OpenAPI } from '@/api'
import { subscribe, unsubscribe, type WebSocketBaseMessage } from '@/composables/useWebSocket'
import { authenticatedApiFetch } from '@/utils/httpSecurity'
import { getPluginPageContext } from './pluginPageContext'

const logger = window.electronAPI.getLogger('插件前端 API')

function toBackendUrl(path: string): string {
  if (/^https?:\/\//i.test(path)) {
    return path
  }

  const base = (OpenAPI.BASE || 'http://127.0.0.1:36163').replace(/\/+$/, '')
  const trimmed = String(path || '').trim()
  if (!trimmed) {
    throw new Error('插件调用路径不能为空')
  }

  if (trimmed.startsWith('/')) {
    return `${base}${trimmed}`
  }

  return `${base}/plugin/${trimmed.replace(/^\/+/, '')}`
}

async function parseResponse(response: Response): Promise<unknown> {
  const contentType = response.headers.get('content-type') || ''
  if (contentType.includes('application/json')) {
    return await response.json()
  }
  return await response.text()
}

export function installPluginAPI(): void {
  window.pluginAPI = {
    call: async (path: string, payload?: unknown) => {
      const url = toBackendUrl(path)
      const hasBody = payload !== undefined
      logger.info(`插件调用后端接口: ${url}`)
      const response = await authenticatedApiFetch(url, {
        method: hasBody ? 'POST' : 'GET',
        headers: hasBody ? { 'Content-Type': 'application/json' } : undefined,
        body: hasBody ? JSON.stringify(payload) : undefined,
      })
      const data = await parseResponse(response)
      if (!response.ok) {
        const message = typeof data === 'string' ? data : JSON.stringify(data)
        throw new Error(`插件接口调用失败: ${response.status} ${message}`)
      }
      return data
    },
    subscribe: (topic: string, handler: (message: WebSocketBaseMessage) => void) => {
      const normalizedTopic = String(topic || '').trim()
      if (!normalizedTopic) {
        throw new Error('插件订阅主题不能为空')
      }
      const subscriptionId = subscribe({ id: normalizedTopic }, handler)
      return () => unsubscribe(subscriptionId)
    },
    getPageContext: () => getPluginPageContext(),
  }
}
