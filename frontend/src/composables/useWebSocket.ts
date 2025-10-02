// websocket.ts
import { ref, type Ref } from 'vue'
import schedulerHandlers from '@/views/scheduler/schedulerHandlers'
import { Modal } from 'ant-design-vue'

// ====== 配置项 ======
const BASE_WS_URL = 'ws://localhost:36163/api/core/ws'
const HEARTBEAT_INTERVAL = 30000  // 30秒心跳间隔，与后端保持一致
const HEARTBEAT_TIMEOUT = 45000   // 45秒超时，给网络延迟留够时间
const BACKEND_CHECK_INTERVAL = 6000  // 6秒检查间隔
const MAX_RESTART_ATTEMPTS = 3
const RESTART_DELAY = 2000
const MAX_QUEUE_SIZE = 50 // 每个 ID 或全局 type 队列最大条数
const MESSAGE_TTL = 60000 // 60 秒过期

// ====== DEBUG 控制 ======
const DEBUG = process.env.NODE_ENV === 'development'

const log = (...args: any[]) => {
  if (DEBUG) console.log('[WebSocket]', ...args)
}
const warn = (...args: any[]) => {
  if (DEBUG) console.warn('[WebSocket]', ...args)
}

// ====== 类型定义 ======
export type WebSocketStatus = '连接中' | '已连接' | '已断开' | '连接错误'
export type BackendStatus = 'unknown' | 'starting' | 'running' | 'stopped' | 'error'

export interface WebSocketBaseMessage {
  id?: string
  type: string
  data?: any
}

export interface SubscriptionFilter {
  type?: string
  id?: string
  needCache?: boolean
}

export interface WebSocketSubscription {
  subscriptionId: string
  filter: SubscriptionFilter
  handler: (message: WebSocketBaseMessage) => void
}

interface CacheMarker {
  type?: string
  id?: string
  refCount: number
}

interface CachedMessage {
  message: WebSocketBaseMessage
  timestamp: number
}

// ====== 全局存储 ======
interface GlobalWSStorage {
  wsRef: WebSocket | null
  status: Ref<WebSocketStatus>
  subscriptions: Ref<Map<string, WebSocketSubscription>>
  cacheMarkers: Ref<Map<string, CacheMarker>>
  cachedMessages: Ref<Array<CachedMessage>>
  heartbeatTimer?: number
  isConnecting: boolean
  lastPingTime: number
  connectionId: string
  moduleLoadCount: number
  createdAt: number
  hasEverConnected: boolean
  reconnectAttempts: number
  backendStatus: Ref<BackendStatus>
  backendCheckTimer?: number
  backendRestartAttempts: number
  isRestartingBackend: boolean
  lastBackendCheck: number
  lastConnectAttempt: number
  allowNewConnection: boolean
  connectionReason: string
  subscriptionCounter: number
}

const WS_STORAGE_KEY = Symbol.for('GLOBAL_WEBSOCKET_PERSISTENT')

const initGlobalStorage = (): GlobalWSStorage => ({
  wsRef: null,
  status: ref<WebSocketStatus>('已断开'),
  subscriptions: ref(new Map()),
  cacheMarkers: ref(new Map()),
  cachedMessages: ref([]),
  heartbeatTimer: undefined,
  isConnecting: false,
  lastPingTime: 0,
  connectionId: Math.random().toString(36).substring(2, 9),
  moduleLoadCount: 0,
  createdAt: Date.now(),
  hasEverConnected: false,
  reconnectAttempts: 0,
  backendStatus: ref<BackendStatus>('unknown'),
  backendCheckTimer: undefined,
  backendRestartAttempts: 0,
  isRestartingBackend: false,
  lastBackendCheck: 0,
  lastConnectAttempt: 0,
  allowNewConnection: true,
  connectionReason: '系统初始化',
  subscriptionCounter: 0,
})

const getGlobalStorage = (): GlobalWSStorage => {
  if (!(window as any)[WS_STORAGE_KEY]) {
    ; (window as any)[WS_STORAGE_KEY] = initGlobalStorage()
  }
  return (window as any)[WS_STORAGE_KEY]
}

// ====== 状态设置 ======
const setGlobalStatus = (status: WebSocketStatus) => {
  getGlobalStorage().status.value = status
}
const setBackendStatus = (status: BackendStatus) => {
  getGlobalStorage().backendStatus.value = status
}

// ====== 后端管理 ======
const checkBackendStatus = (): boolean => {
  const global = getGlobalStorage()
  return !!(global.wsRef && global.wsRef.readyState === WebSocket.OPEN)
}

const restartBackend = async (): Promise<boolean> => {
  const global = getGlobalStorage()
  if (global.isRestartingBackend) return false

  try {
    global.isRestartingBackend = true
    global.backendRestartAttempts++
    setBackendStatus('starting')

    if ((window.electronAPI as any)?.startBackend) {
      const result = await (window.electronAPI as any).startBackend()
      if (result?.success) {
        setBackendStatus('running')
        global.backendRestartAttempts = 0
        return true
      }
    }
    setBackendStatus('error')
    return false
  } catch (e) {
    setBackendStatus('error')
    return false
  } finally {
    global.isRestartingBackend = false
  }
}

const handleBackendFailure = async () => {
  const global = getGlobalStorage()
  if (global.backendRestartAttempts >= MAX_RESTART_ATTEMPTS) {
    Modal.error({
      title: '后端服务异常',
      content: '后端服务多次重启失败，请重启整个应用程序。',
      okText: '重启应用',
      onOk: () => {
        if ((window.electronAPI as any)?.windowClose) {
          ; (window.electronAPI as any).windowClose()
        } else {
          window.location.reload()
        }
      },
    })
    return
  }

  setTimeout(async () => {
    const success = await restartBackend()
    if (success) {
      // 统一在一个地方管理连接权限
      setConnectionPermission(true, '后端重启后重连')

      // 等待后端完全启动
      setTimeout(async () => {
        try {
          const connected = await connectGlobalWebSocket('后端重启后重连')
          if (connected) {
            // 连接成功后再禁用权限
            setTimeout(() => {
              setConnectionPermission(false, '正常运行中')
            }, 1000)
          }
        } catch (e) {
          warn('重启后重连失败:', e)
          setConnectionPermission(false, '连接失败')
        }
      }, RESTART_DELAY)
    } else {
      // 重启失败，继续尝试
      setTimeout(handleBackendFailure, RESTART_DELAY)
    }
  }, RESTART_DELAY)
}

const startBackendMonitoring = () => {
  const global = getGlobalStorage()
  if (global.backendCheckTimer) clearInterval(global.backendCheckTimer)

  global.backendCheckTimer = window.setInterval(() => {
    const isRunning = checkBackendStatus()
    const now = Date.now()
    global.lastBackendCheck = now

    if (isRunning) {
      if (global.backendStatus.value !== 'running') {
        setBackendStatus('running')
        global.backendRestartAttempts = 0
      }
    } else if (global.backendStatus.value === 'running') {
      setBackendStatus('stopped')
    }

    // 检查心跳超时：如果超过心跳超时时间且连接仍然打开，说明后端可能有问题
    if (global.lastPingTime > 0 && now - global.lastPingTime > HEARTBEAT_TIMEOUT) {
      if (global.wsRef?.readyState === WebSocket.OPEN) {
        setBackendStatus('error')
        // 主动关闭可能有问题的连接
        global.wsRef.close(1000, '心跳超时')
      }
    }
  }, BACKEND_CHECK_INTERVAL)
}

// ====== 心跳 ======
const stopGlobalHeartbeat = () => {
  const global = getGlobalStorage()
  if (global.heartbeatTimer) {
    clearInterval(global.heartbeatTimer)
    global.heartbeatTimer = undefined
  }
}

const startGlobalHeartbeat = (ws: WebSocket) => {
  const global = getGlobalStorage()
  stopGlobalHeartbeat()
  global.heartbeatTimer = window.setInterval(() => {
    if (ws.readyState === WebSocket.OPEN) {
      const pingTime = Date.now()
      global.lastPingTime = pingTime
      try {
        ws.send(
          JSON.stringify({
            type: 'Signal',
            data: { Ping: pingTime, connectionId: global.connectionId },
          })
        )
      } catch { }
    }
  }, HEARTBEAT_INTERVAL)
}

// ====== 消息队列和缓存管理 ======
const cleanupExpiredMessages = (now: number) => {
  const global = getGlobalStorage()
  global.cachedMessages.value = global.cachedMessages.value.filter(
    cached => now - cached.timestamp <= MESSAGE_TTL
  )
}

// 检查消息是否匹配订阅条件
const messageMatchesFilter = (message: WebSocketBaseMessage, filter: SubscriptionFilter): boolean => {
  // 如果都不指定，匹配所有消息
  if (!filter.type && !filter.id) return true

  // 如果只指定type
  if (filter.type && !filter.id) return message.type === filter.type

  // 如果只指定id
  if (!filter.type && filter.id) return message.id === filter.id

  // 如果同时指定type和id，必须都匹配
  return message.type === filter.type && message.id === filter.id
}

// 获取缓存标记的key
const getCacheMarkerKey = (filter: SubscriptionFilter): string => {
  if (filter.type && filter.id) return `${filter.type}:${filter.id}`
  if (filter.type) return `type:${filter.type}`
  if (filter.id) return `id:${filter.id}`
  return 'all'
}

// 添加缓存标记
const addCacheMarker = (filter: SubscriptionFilter) => {
  if (!filter.needCache) return

  const global = getGlobalStorage()
  const key = getCacheMarkerKey(filter)
  const existing = global.cacheMarkers.value.get(key)

  if (existing) {
    existing.refCount++
  } else {
    global.cacheMarkers.value.set(key, {
      type: filter.type,
      id: filter.id,
      refCount: 1
    })
  }

  log(`缓存标记 ${key} 引用计数: ${global.cacheMarkers.value.get(key)?.refCount}`)
}

// 移除缓存标记
const removeCacheMarker = (filter: SubscriptionFilter) => {
  if (!filter.needCache) return

  const global = getGlobalStorage()
  const key = getCacheMarkerKey(filter)
  const existing = global.cacheMarkers.value.get(key)

  if (existing) {
    existing.refCount--
    if (existing.refCount <= 0) {
      global.cacheMarkers.value.delete(key)
      log(`移除缓存标记: ${key}`)
    } else {
      log(`缓存标记 ${key} 引用计数: ${existing.refCount}`)
    }
  }
}

// 检查消息是否需要缓存
const shouldCacheMessage = (message: WebSocketBaseMessage): boolean => {
  const global = getGlobalStorage()

  for (const [, marker] of global.cacheMarkers.value) {
    const filter = { type: marker.type, id: marker.id }
    if (messageMatchesFilter(message, filter)) {
      return true
    }
  }
  return false
}

// ====== 消息分发 ======
const handleMessage = (raw: WebSocketBaseMessage) => {
  const global = getGlobalStorage()
  const now = Date.now()

  if (DEBUG) {
    log('收到原始消息:', { type: raw.type, id: raw.id, data: raw.data })
  }

  let dispatched = false

  // 分发给所有匹配的订阅者
  global.subscriptions.value.forEach((subscription) => {
    if (messageMatchesFilter(raw, subscription.filter)) {
      try {
        subscription.handler(raw)
        dispatched = true
      } catch (e) {
        warn(`订阅处理器错误 [${subscription.subscriptionId}]:`, e)
      }
    }
  })

  // 如果需要缓存且有标记，则添加到缓存
  if (shouldCacheMessage(raw)) {
    global.cachedMessages.value.push({ message: raw, timestamp: now })
    // 限制缓存大小
    if (global.cachedMessages.value.length > MAX_QUEUE_SIZE) {
      global.cachedMessages.value = global.cachedMessages.value.slice(-MAX_QUEUE_SIZE)
    }
    log(`消息已缓存: type=${raw.type}, id=${raw.id}`)
  }

  // 定期清理过期消息（每处理50条消息触发一次，避免频繁且更可预测）
  if (global.cachedMessages.value.length > 0 && global.cachedMessages.value.length % 50 === 0) {
    cleanupExpiredMessages(now)
  }

  if (!dispatched) {
    log('无订阅者接收此消息:', raw)
  }
}

// ====== 新的订阅机制 ======
export const subscribe = (
  filter: SubscriptionFilter,
  handler: (message: WebSocketBaseMessage) => void
): string => {
  const global = getGlobalStorage()
  const subscriptionId = `sub_${++global.subscriptionCounter}_${Date.now()}`

  const subscription: WebSocketSubscription = {
    subscriptionId,
    filter,
    handler
  }

  global.subscriptions.value.set(subscriptionId, subscription)

  // 添加缓存标记
  addCacheMarker(filter)

  // 回放匹配的缓存消息
  const matchingMessages = global.cachedMessages.value.filter(cached =>
    messageMatchesFilter(cached.message, filter)
  )

  if (matchingMessages.length > 0) {
    log(`回放 ${matchingMessages.length} 条缓存消息给订阅 ${subscriptionId}`)
    matchingMessages.forEach(cached => {
      try {
        handler(cached.message)
      } catch (e) {
        warn(`回放消息时处理器错误 [${subscriptionId}]:`, e)
      }
    })
  }

  log(`新订阅创建: ${subscriptionId}`, filter)
  return subscriptionId
}

export const unsubscribe = (subscriptionId: string): void => {
  const global = getGlobalStorage()
  const subscription = global.subscriptions.value.get(subscriptionId)

  if (subscription) {
    // 移除缓存标记
    removeCacheMarker(subscription.filter)

    // 清理缓存中没有任何标记的消息
    cleanupUnmarkedCache()

    global.subscriptions.value.delete(subscriptionId)
    log(`订阅已取消: ${subscriptionId}`)
  } else {
    warn(`尝试取消不存在的订阅: ${subscriptionId}`)
  }
}

// 清理没有标记的缓存消息
const cleanupUnmarkedCache = () => {
  const global = getGlobalStorage()

  global.cachedMessages.value = global.cachedMessages.value.filter(cached => {
    // 检查是否还有标记需要这条消息
    for (const [, marker] of global.cacheMarkers.value) {
      const filter = { type: marker.type, id: marker.id }
      if (messageMatchesFilter(cached.message, filter)) {
        return true
      }
    }
    return false
  })
}

// ====== 连接控制 ======
let isGlobalConnectingLock = false
const acquireConnectionLock = () => {
  if (isGlobalConnectingLock) return false
  isGlobalConnectingLock = true
  return true
}
const releaseConnectionLock = () => {
  isGlobalConnectingLock = false
}

const allowedConnectionReasons = ['后端启动后连接', '后端重启后重连', '系统初始化', '手动重连', '强制连接']
const isValidConnectionReason = (reason: string) => allowedConnectionReasons.includes(reason)
const checkConnectionPermission = () => getGlobalStorage().allowNewConnection
const setConnectionPermission = (allow: boolean, reason: string) => {
  const global = getGlobalStorage()
  global.allowNewConnection = allow
  global.connectionReason = reason
}

const createGlobalWebSocket = (): WebSocket => {
  const global = getGlobalStorage()

  // 清理旧连接
  if (global.wsRef) {
    if (global.wsRef.readyState === WebSocket.OPEN) {
      log('警告：尝试创建新连接但当前连接仍有效')
      return global.wsRef
    }
    if (global.wsRef.readyState === WebSocket.CONNECTING) {
      log('警告：尝试创建新连接但当前连接正在建立中')
      return global.wsRef
    }
    // 清理已关闭或错误状态的连接
    global.wsRef = null
  }

  const ws = new WebSocket(BASE_WS_URL)
  global.wsRef = ws

  ws.onopen = () => {
    global.isConnecting = false
    global.hasEverConnected = true
    global.reconnectAttempts = 0
    setGlobalStatus('已连接')
    startGlobalHeartbeat(ws)

    // 只有在特殊连接原因下才设置为正常运行
    if (global.connectionReason !== '系统初始化') {
      setConnectionPermission(false, '正常运行中')
    }

    try {
      ws.send(
        JSON.stringify({
          type: 'Signal',
          data: { Connect: true, connectionId: global.connectionId },
        })
      )
      ws.send(
        JSON.stringify({
          type: 'Signal',
          data: { Pong: Date.now(), connectionId: global.connectionId },
        })
      )
    } catch (e) {
      warn('发送初始信号失败:', e)
    }

    initializeGlobalSubscriptions()
    log('WebSocket连接已建立并初始化完成')
  }

  ws.onmessage = ev => {
    try {
      const raw = JSON.parse(ev.data) as WebSocketBaseMessage
      handleMessage(raw)
    } catch (e) {
      warn('解析WebSocket消息失败:', e, '原始数据:', ev.data)
    }
  }

  ws.onerror = (error) => {
    setGlobalStatus('连接错误')
    warn('WebSocket错误:', error)
  }

  ws.onclose = event => {
    setGlobalStatus('已断开')
    stopGlobalHeartbeat()
    global.isConnecting = false

    log(`WebSocket连接关闭: code=${event.code}, reason="${event.reason}"`)

    // 根据关闭原因决定是否需要处理后端故障
    if (event.code === 1000 && event.reason === 'Ping超时') {
      handleBackendFailure().catch(e => warn('handleBackendFailure error:', e))
    } else if (event.code === 1000 && event.reason === '心跳超时') {
      handleBackendFailure().catch(e => warn('handleBackendFailure error:', e))
    }
  }

  return ws
}

const connectGlobalWebSocket = async (reason: string = '手动重连'): Promise<boolean> => {
  const global = getGlobalStorage()
  if (!checkConnectionPermission() || !isValidConnectionReason(reason)) {
    warn(`连接被拒绝: 权限=${checkConnectionPermission()}, 原因="${reason}"是否有效=${isValidConnectionReason(reason)}`)
    return false
  }
  if (!acquireConnectionLock()) return false

  try {
    if (global.wsRef) {
      const state = global.wsRef.readyState
      if (state === WebSocket.OPEN) {
        setGlobalStatus('已连接')
        return true
      }
      if (state === WebSocket.CONNECTING) return true
      if (state === WebSocket.CLOSING) return false
    }

    if (global.isConnecting) return false

    const now = Date.now()
    if (global.lastConnectAttempt && now - global.lastConnectAttempt < 2000) return false

    global.isConnecting = true
    global.lastConnectAttempt = now
    if (global.wsRef?.readyState === WebSocket.CLOSED) global.wsRef = null

    global.wsRef = createGlobalWebSocket()
    setGlobalStatus('连接中')
    return true
  } catch (e) {
    setGlobalStatus('连接错误')
    global.isConnecting = false
    return false
  } finally {
    releaseConnectionLock()
  }
}

export const connectAfterBackendStart = async (): Promise<boolean> => {
  setConnectionPermission(true, '后端启动后连接')
  try {
    const connected = await connectGlobalWebSocket('后端启动后连接')
    if (connected) {
      startBackendMonitoring()
      setConnectionPermission(false, '正常运行中')
      return true
    }
    return false
  } catch {
    return false
  }
}

// 强制连接模式，用于强行进入应用时
export const forceConnectWebSocket = async (): Promise<boolean> => {
  log('强制WebSocket连接模式开始')

  const global = getGlobalStorage()

  // 显示当前状态
  log('当前连接状态:', {
    status: global.status.value,
    wsReadyState: global.wsRef?.readyState,
    allowNewConnection: global.allowNewConnection,
    connectionReason: global.connectionReason
  })

  // 设置连接权限
  setConnectionPermission(true, '强制连接')
  log('已设置强制连接权限')

  try {
    // 尝试连接，最多重试3次
    let connected = false
    let attempts = 0
    const maxAttempts = 3

    while (!connected && attempts < maxAttempts) {
      attempts++
      log(`强制连接尝试 ${attempts}/${maxAttempts}`)

      try {
        connected = await connectGlobalWebSocket('强制连接')
        if (connected) {
          startBackendMonitoring()
          log('强制WebSocket连接成功')
          break
        } else {
          warn(`强制连接尝试 ${attempts} 失败`)
          if (attempts < maxAttempts) {
            // 等待1秒后重试
            await new Promise(resolve => setTimeout(resolve, 1000))
          }
        }
      } catch (attemptError) {
        warn(`强制连接尝试 ${attempts} 异常:`, attemptError)
        if (attempts < maxAttempts) {
          await new Promise(resolve => setTimeout(resolve, 1000))
        }
      }
    }

    if (!connected) {
      warn('所有强制连接尝试均失败，但不阻止应用启动')
    }

    return connected
  } catch (error) {
    warn('强制WebSocket连接异常:', error)
    return false
  } finally {
    // 稍后重置连接权限，给连接时间
    setTimeout(() => {
      setConnectionPermission(false, '强制连接完成')
      log('强制连接权限已重置')
    }, 2000)  // 增加到2秒
  }
}

// ====== 全局处理器 ======
let _defaultHandlersLoaded = true
let _defaultTaskManagerHandler = schedulerHandlers.handleTaskManagerMessage
let _defaultMainHandler = schedulerHandlers.handleMainMessage

export const ExternalWSHandlers = {
  mainMessage: (message: any) => {
    try {
      if (_defaultHandlersLoaded && typeof _defaultMainHandler === 'function') {
        _defaultMainHandler(message)
        return
      }
    } catch (e) {
      warn('default main handler error:', e)
    }
  },
  taskManagerMessage: (message: any) => {
    try {
      if (_defaultHandlersLoaded && typeof _defaultTaskManagerHandler === 'function') {
        _defaultTaskManagerHandler(message)
        return
      }
    } catch (e) {
      warn('default taskManager handler error:', e)
    }
  },
}

const initializeGlobalSubscriptions = () => {
  subscribe({ id: 'TaskManager' }, (msg: WebSocketBaseMessage) => {
    try {
      ExternalWSHandlers.taskManagerMessage(msg)
    } catch (e) {
      warn('External taskManagerMessage handler error:', e)
    }
  })

  subscribe({ id: 'Main' }, (msg: WebSocketBaseMessage) => {
    if (msg.type === 'Signal' && msg.data) {
      if (msg.data.Pong) {
        getGlobalStorage().lastPingTime = 0
        return
      }
      if (msg.data.Ping) {
        const global = getGlobalStorage()
        const ws = global.wsRef
        if (ws?.readyState === WebSocket.OPEN) {
          try {
            ws.send(
              JSON.stringify({
                type: 'Signal',
                data: { Pong: msg.data.Ping, connectionId: global.connectionId },
              })
            )
          } catch { }
        }
        return
      }
    }
    try {
      ExternalWSHandlers.mainMessage(msg)
    } catch (e) {
      warn('External mainMessage handler error:', e)
    }
  })
}

// ====== Vue Hook ======
export function useWebSocket() {
  const global = getGlobalStorage()

  const sendRaw = (type: string, data?: any, id?: string) => {
    const ws = global.wsRef
    if (ws?.readyState === WebSocket.OPEN) {
      try {
        const message = { id, type, data }
        ws.send(JSON.stringify(message))
        if (DEBUG && type !== 'Signal') {  // 避免心跳消息spam日志
          log('发送消息:', message)
        }
        return true
      } catch (e) {
        warn('发送消息失败:', e, { id, type, data })
        return false
      }
    } else {
      warn('WebSocket未连接，无法发送消息:', {
        readyState: ws?.readyState,
        message: { id, type, data }
      })
      return false
    }
  }

  const getConnectionInfo = () => ({
    connectionId: global.connectionId,
    status: global.status.value,
    subscriberCount: global.subscriptions.value.size,
    moduleLoadCount: global.moduleLoadCount,
    wsReadyState: global.wsRef ? global.wsRef.readyState : null,
    isConnecting: global.isConnecting,
    hasHeartbeat: !!global.heartbeatTimer,
    hasEverConnected: global.hasEverConnected,
    reconnectAttempts: global.reconnectAttempts,
    isPersistentMode: true,
  })

  const restartBackendManually = async () => {
    const g = getGlobalStorage()
    g.backendRestartAttempts = 0
    return await restartBackend()
  }

  const getBackendStatus = () => ({
    status: global.backendStatus.value,
    restartAttempts: global.backendRestartAttempts,
    isRestarting: global.isRestartingBackend,
    lastCheck: global.lastBackendCheck,
  })

  // 调试功能
  const debug = {
    forceConnect: forceConnectWebSocket,
    normalConnect: connectAfterBackendStart,
    getGlobalStorage,
    setConnectionPermission,
    checkConnectionPermission,
    allowedReasons: allowedConnectionReasons
  }

  // 在开发模式下暴露调试功能到全局
  if (DEBUG && typeof window !== 'undefined') {
    ; (window as any).wsDebug = debug
  }

  return {
    subscribe,
    unsubscribe,
    sendRaw,
    getConnectionInfo,
    status: global.status,
    backendStatus: global.backendStatus,
    restartBackend: restartBackendManually,
    getBackendStatus,
    debug: DEBUG ? debug : undefined
  }
}

// ====== 页面卸载保护 ======
window.addEventListener('beforeunload', () => {
  // 保持连接
})

// ====== 模块加载计数 ======
const global = getGlobalStorage()
if (global.moduleLoadCount === 0) global.moduleLoadCount = 1
