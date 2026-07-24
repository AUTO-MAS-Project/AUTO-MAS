// useWebSocket.ts - 主 WebSocket 组合式 API 门面
// 连接、重连和请求关联归 services/websocket；应用退出与后端恢复归 useAppLifecycle。

import { computed } from 'vue'
import schedulerHandlers from '@/views/scheduler/schedulerHandlers'
import {
  connectionInfo,
  connectionState,
  isConnectionReplacedClose,
  request,
  send as sendEnvelope,
  shouldReconnectAfterClose as shouldReconnectAfterTransportClose,
  stopReconnect,
} from '@/services/websocket/connection'
import {
  subscribe as subscribeEnvelope,
  subscriptionCount,
  unsubscribe,
} from '@/services/websocket/subscriptions'
import type {
  WSConnectionState,
  WSEnvelope,
  WSMessageHandler,
  WSSubscriptionKey,
} from '@/services/websocket/types'
import { initializeAppLifecycle, useAppLifecycle } from '@/composables/useAppLifecycle'

export type { WSConnectionState, WSEnvelope, WSMessageHandler, WSSubscriptionKey }
export { request, unsubscribe }
export { createWebSocketAuthProtocol } from '@/utils/websocketAuth'

export type WebSocketStatus = '连接中' | '已连接' | '已断开' | '连接错误'
export type BackendStatus = 'unknown' | 'starting' | 'running' | 'stopped' | 'error'

/** 旧页面的消息类型门面；底层入站信封始终具有 id/type/data。 */
export interface WebSocketBaseMessage {
  id?: string
  type: string
  data?: any
}

export interface SubscriptionFilter {
  id?: string
  type?: string
  /** 迁移期只保留字段兼容；新连接层不缓存、不重放消息。 */
  needCache?: boolean
}

export interface WebSocketSubscription {
  subscriptionId: string
  filter: SubscriptionFilter
  handler: (message: WebSocketBaseMessage) => void
}

export interface DialogRequestData {
  requestId: string
  title: string
  message: string
  options: string[]
}

export interface DialogResponseMessage {
  id: 'Main'
  type: 'dialog.response'
  data: {
    requestId: string
    choice: boolean
  }
}

interface WebSocketCloseDetails {
  code: number
  reason: string
}

const logger = window.electronAPI.getLogger('WebSocket门面')
const lifecycle = useAppLifecycle()

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

export const normalizeDialogRequestData = (value: unknown): DialogRequestData | null => {
  if (!isRecord(value) || typeof value.requestId !== 'string') return null

  const requestId = value.requestId.trim()
  if (!requestId) return null
  const options = Array.isArray(value.options)
    ? value.options.filter(
        (option): option is string => typeof option === 'string' && option.trim().length > 0
      )
    : []

  return {
    requestId,
    title:
      typeof value.title === 'string' && value.title.trim().length > 0 ? value.title : '操作提示',
    message: typeof value.message === 'string' ? value.message : '',
    options: options.length > 0 ? options : ['确定', '取消'],
  }
}

export const createDialogResponseMessage = (
  requestId: string,
  choice: boolean
): DialogResponseMessage => ({
  id: 'Main',
  type: 'dialog.response',
  data: { requestId, choice },
})

export { isConnectionReplacedClose }

export const shouldReconnectAfterClose = (
  event: WebSocketCloseDetails,
  isAppClosing: boolean
): boolean => !isAppClosing && shouldReconnectAfterTransportClose(event)

export const subscribe = (
  filter: SubscriptionFilter,
  handler: (message: WebSocketBaseMessage) => void
): string =>
  subscribeEnvelope({ id: filter.id, type: filter.type }, message =>
    handler(message as WebSocketBaseMessage)
  )

export const send = (id: string, type: string, data?: Record<string, unknown>): boolean =>
  sendEnvelope(id, type, data)

const sendRaw = (type: string, data?: unknown, id?: string): boolean => {
  if (data !== undefined && !isRecord(data)) {
    logger.warn(`拒绝发送非对象 WebSocket data: id=${id ?? ''}, type=${type}`)
    return false
  }
  return sendEnvelope(id ?? '', type, data)
}

export const ExternalWSHandlers = {
  mainMessage: (message: WebSocketBaseMessage) => schedulerHandlers.handleMainMessage(message),
  taskManagerMessage: (message: WebSocketBaseMessage) =>
    schedulerHandlers.handleTaskManagerMessage(message),
}

let compatibilitySubscriptionsInitialized = false

const initializeCompatibilitySubscriptions = (): void => {
  if (compatibilitySubscriptionsInitialized) return
  compatibilitySubscriptionsInitialized = true
  subscribe({ id: 'TaskManager', type: 'Signal' }, message =>
    ExternalWSHandlers.taskManagerMessage(message)
  )
  for (const type of ['Signal', 'Message', 'Update']) {
    subscribe({ id: 'Main', type }, message => ExternalWSHandlers.mainMessage(message))
  }
}

const initializeRuntime = (): void => {
  initializeAppLifecycle()
  initializeCompatibilitySubscriptions()
}

const status = computed<WebSocketStatus>(() => {
  const state = connectionState().value
  if (state === 'open') return '已连接'
  if (state === 'connecting' || state === 'reconnecting') return '连接中'
  if (state === 'closed') return '连接错误'
  return '已断开'
})

export const connectAfterBackendStart = async (): Promise<boolean> => {
  initializeRuntime()
  return await lifecycle.connectWithRetry(5, 1000)
}

export const forceConnectWebSocket = async (): Promise<boolean> => {
  initializeRuntime()
  return await lifecycle.connectWithRetry(3, 1000)
}

export function useWebSocket() {
  initializeRuntime()

  const getConnectionInfo = () => {
    const info = connectionInfo()
    const readyState = typeof info.readyState === 'number' ? info.readyState : null
    const state = connectionState().value
    return {
      connectionId: 'main',
      status: status.value,
      subscriberCount: subscriptionCount(),
      moduleLoadCount: 1,
      wsReadyState: readyState,
      isConnecting: state === 'connecting' || state === 'reconnecting',
      hasHeartbeat: false,
      hasEverConnected: state === 'open',
      reconnectAttempts: typeof info.reconnectAttempts === 'number' ? info.reconnectAttempts : 0,
      isPersistentMode: true,
      wsReconnectAttempts: typeof info.reconnectAttempts === 'number' ? info.reconnectAttempts : 0,
      isAutoReconnecting: state === 'reconnecting',
      lastDisconnectTime: null,
    }
  }

  const getBackendStatus = () => ({
    status: lifecycle.backendStatus.value,
    restartAttempts: 0,
    isRestarting: lifecycle.backendStatus.value === 'starting',
    lastCheck: Date.now(),
  })

  const restartBackend = async (): Promise<boolean> => {
    await lifecycle.restartBackendManually()
    return connectionState().value === 'open'
  }

  const resetReconnect = (): void => {
    stopReconnect()
  }

  return {
    subscribe,
    unsubscribe,
    send,
    sendRaw,
    request,
    getConnectionInfo,
    status,
    backendStatus: lifecycle.backendStatus,
    restartBackend,
    getBackendStatus,
    manualReconnect: lifecycle.manualReconnect,
    resetReconnect,
    resetWebSocketState: resetReconnect,
    connectAfterBackendStart,
    state: connectionState(),
  }
}
