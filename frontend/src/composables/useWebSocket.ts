// websocket.ts
import { ref, type Ref } from 'vue'
import schedulerHandlers from '@/views/scheduler/schedulerHandlers'
import { Modal } from 'ant-design-vue'
import { useAppClosing } from '@/composables/useAppClosing'
import { getLogger } from '@/utils/logger'

const logger = getLogger('WebSocket连接')

// ====== 配置项 ======
const BASE_WS_URL = 'ws://localhost:36163/api/core/ws'
const HEARTBEAT_INTERVAL = 30000 // 30秒心跳间隔，与后端保持一致
const HEARTBEAT_TIMEOUT = 45000 // 45秒超时，给网络延迟留够时间
const BACKEND_CHECK_INTERVAL = 6000 // 6秒检查间隔
const MAX_RESTART_ATTEMPTS = 3
const RESTART_DELAY = 2000
const MAX_QUEUE_SIZE = 50 // 每个 ID 或全局 type 队列最大条数
const MESSAGE_TTL = 60000 // 60 秒过期

// WebSocket重连相关配置
const MAX_WS_RECONNECT_ATTEMPTS = 5 // WebSocket最大重连尝试次数
const WS_RECONNECT_DELAY = 3000 // WebSocket重连延迟（3秒）
const WS_RECONNECT_DELAY_MAX = 30000 // WebSocket重连最大延迟（30秒）
const WS_RECONNECT_BACKOFF = 1.5 // WebSocket重连退避倍数

// ====== DEBUG 控制 ======
const DEBUG = process.env.NODE_ENV === 'development'

const log = (...args: any[]) => {
  if (DEBUG) logger.debug('[WebSocket]', ...args)
}
const warn = (...args: any[]) => {
  if (DEBUG) logger.warn('[WebSocket]', ...args)
}

// 强制日志输出，用于诊断重连问题
const forceLog = (...args: any[]) => {
  // 在生产环境中只输出重要的日志
  if (DEBUG || args[0]?.includes?.('重复消息') || args[0]?.includes?.('订阅')) {
    logger.info('[WebSocket-FORCE]', ...args)
  }
}
const forceWarn = (...args: any[]) => {
  logger.warn('[WebSocket-FORCE]', ...args)
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
  // WebSocket重连相关状态
  wsReconnectAttempts: number
  wsReconnectTimer?: number
  isAutoReconnecting: boolean
  lastDisconnectTime: number
  reconnectFailureModalShown: boolean
  autoRestartTimer?: number // 添加自动重启定时器
  // 全局订阅ID，避免重复订阅
  globalTaskManagerSubscriptionId?: string
  globalMainSubscriptionId?: string
  // 消息去重
  lastProcessedMessages?: Map<string, number>
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
  // WebSocket重连相关状态
  wsReconnectAttempts: 0,
  wsReconnectTimer: undefined,
  isAutoReconnecting: false,
  lastDisconnectTime: 0,
  reconnectFailureModalShown: false,
  autoRestartTimer: undefined, // 初始化自动重启定时器
  // 初始化全局订阅ID
  globalTaskManagerSubscriptionId: undefined,
  globalMainSubscriptionId: undefined,
  // 初始化消息去重
  lastProcessedMessages: undefined,
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

        // 重启成功后自动重连WebSocket
        setTimeout(async () => {
          try {
            log('后端重启成功，开始重新连接WebSocket')
            setConnectionPermission(true, '后端重启后重连')

            const connected = await connectGlobalWebSocket('后端重启后重连')
            if (connected) {
              log('后端重启后WebSocket重连成功')
              setTimeout(() => {
                setConnectionPermission(false, '正常运行中')
              }, 1000)
              startBackendMonitoring()
            } else {
              warn('后端重启后WebSocket重连失败，启动自动重连')
              startAutoReconnect()
            }
          } catch (e) {
            warn('后端重启后重连异常:', e)
            startAutoReconnect()
          }
        }, RESTART_DELAY)

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

// WebSocket自动重连功能
const startAutoReconnect = () => {
  forceLog('startAutoReconnect函数被调用')
  const global = getGlobalStorage()

  forceLog(`重连状态检查: isAutoReconnecting=${global.isAutoReconnecting}, reconnectFailureModalShown=${global.reconnectFailureModalShown}`)

  // 如果已经在重连中或者已经显示过失败弹窗，则不再重连
  if (global.isAutoReconnecting || global.reconnectFailureModalShown) {
    forceWarn(
      `跳过重连: 已在重连中=${global.isAutoReconnecting}, 已显示弹窗=${global.reconnectFailureModalShown}`
    )
    return
  }

  // 确保连接权限允许重连
  if (!global.allowNewConnection) {
    forceLog('自动重连被阻止，重置连接权限')
    setConnectionPermission(true, 'WebSocket自动重连')
  }

  // 如果已经有重连定时器在运行，先停止它
  if (global.wsReconnectTimer) {
    log('检测到已有重连定时器，先停止它')
    clearTimeout(global.wsReconnectTimer)
    global.wsReconnectTimer = undefined
  }

  global.isAutoReconnecting = true
  global.lastDisconnectTime = Date.now()

  forceLog(
    `开始WebSocket自动重连，当前重试次数: ${global.wsReconnectAttempts}，最大重试次数: ${MAX_WS_RECONNECT_ATTEMPTS}`
  )

  const attemptReconnect = () => {
    if (global.wsReconnectAttempts >= MAX_WS_RECONNECT_ATTEMPTS) {
      log(`达到最大重连次数 ${MAX_WS_RECONNECT_ATTEMPTS}，显示失败弹窗`)
      global.isAutoReconnecting = false
      showReconnectFailureModal()
      return
    }

    global.wsReconnectAttempts++

    // 计算重连延迟（指数退避）
    const baseDelay = WS_RECONNECT_DELAY
    const attempt = global.wsReconnectAttempts
    const delay = Math.min(
      baseDelay * Math.pow(WS_RECONNECT_BACKOFF, attempt - 1),
      WS_RECONNECT_DELAY_MAX
    )

    forceLog(`第 ${attempt} 次重连尝试，延迟 ${delay}ms`)

    global.wsReconnectTimer = window.setTimeout(async () => {
      try {
        forceLog(`执行第 ${attempt} 次重连尝试，当前wsReconnectAttempts=${global.wsReconnectAttempts}`)
        setConnectionPermission(true, 'WebSocket自动重连')

        // 不要在这里设置isConnecting，让connectGlobalWebSocket函数内部处理
        // global.isConnecting = true
        // setGlobalStatus('连接中')
        forceLog('准备调用connectGlobalWebSocket')

        const connected = await connectGlobalWebSocket('WebSocket自动重连')
        forceLog(`connectGlobalWebSocket返回结果: ${connected}`)

        if (connected) {
          forceLog('WebSocket对象创建成功，等待连接结果')
          // 注意：这里connected=true只是表示WebSocket对象创建成功
          // 实际的连接成功会在onopen事件中处理
          // 如果连接失败，需要等待一段时间来判断连接是否真的成功

          // 等待一段时间来判断连接是否成功
          setTimeout(() => {
            forceLog(`2秒超时检查: WebSocket状态=${global.wsRef?.readyState}`)
            if (global.wsRef && global.wsRef.readyState === WebSocket.OPEN) {
              forceLog('WebSocket连接确认成功')
              startBackendMonitoring() // 启动后端监控
            } else if (global.wsRef && (global.wsRef.readyState === WebSocket.CLOSED || global.wsRef.readyState === WebSocket.CLOSING)) {
              forceLog('WebSocket连接失败，继续下一次重连尝试')
              // 连接失败，继续下一次尝试
              global.isConnecting = false
              setGlobalStatus('已断开')
              attemptReconnect()
            } else {
              forceLog(`WebSocket状态异常: ${global.wsRef?.readyState}，继续下一次重连`)
              global.isConnecting = false
              setGlobalStatus('已断开')
              attemptReconnect()
            }
          }, 2000) // 等待2秒判断连接结果
        } else {
          forceWarn(
            `第 ${attempt} 次重连失败，准备下一次尝试，当前wsReconnectAttempts=${global.wsReconnectAttempts}`
          )
          // 关键修复：重置isConnecting状态
          global.isConnecting = false
          setGlobalStatus('已断开')
          forceLog('状态已重置为已断开，准备下一次重连尝试')
          // 继续下一次尝试（通过递归调用）
          attemptReconnect()
        }
      } catch (e) {
        forceWarn(`第 ${attempt} 次重连异常:`, e)
        // 确保重置状态
        global.isConnecting = false
        setGlobalStatus('连接错误')
        // 异常时也继续尝试重连
        attemptReconnect()
      }
    }, delay)
  }

  attemptReconnect()
}

// 停止自动重连
const stopAutoReconnect = () => {
  const global = getGlobalStorage()

  if (global.wsReconnectTimer) {
    clearTimeout(global.wsReconnectTimer)
    global.wsReconnectTimer = undefined
    log('停止WebSocket自动重连定时器')
  }

  const wasAutoReconnecting = global.isAutoReconnecting
  global.isAutoReconnecting = false
  if (wasAutoReconnecting) {
    log('自动重连状态已停止')
  }
}

// 显示重连失败弹窗
const showReconnectFailureModal = () => {
  const global = getGlobalStorage()

  // 防止重复显示弹窗
  if (global.reconnectFailureModalShown) {
    log('重连失败弹窗已显示过，跳过')
    return
  }

  log(
    `显示重连失败弹窗，重试次数已达到: ${global.wsReconnectAttempts}/${MAX_WS_RECONNECT_ATTEMPTS}`
  )
  global.reconnectFailureModalShown = true
  global.isAutoReconnecting = false

  // 清除之前的自动重启定时器（如果存在）
  if (global.autoRestartTimer) {
    clearTimeout(global.autoRestartTimer)
    global.autoRestartTimer = undefined
  }

  // 设置10秒后自动重启后端服务
  let autoRestartExecuted = false
  global.autoRestartTimer = window.setTimeout(async () => {
    if (!autoRestartExecuted) {
      autoRestartExecuted = true
      log('用户10秒内无响应，自动重启后端服务')

      // 关闭可能存在的弹窗
      Modal.destroyAll()

      // 执行重启后端服务的逻辑
      global.reconnectFailureModalShown = false
      resetReconnectState()

      try {
        const success = await restartBackend()
        if (success) {
          log('自动重启后端成功，开始重新连接')
          setConnectionPermission(true, '后端重启后重连')

          setTimeout(async () => {
            try {
              const connected = await connectGlobalWebSocket('后端重启后重连')
              if (connected) {
                log('自动重启后端后WebSocket重连成功')
                setTimeout(() => {
                  setConnectionPermission(false, '正常运行中')
                }, 1000)
                startBackendMonitoring()
              } else {
                warn('自动重启后端后WebSocket重连失败，启动自动重连')
                startAutoReconnect()
              }
            } catch (e) {
              warn('自动重启后端后重连异常:', e)
              startAutoReconnect()
            }
          }, RESTART_DELAY)
        } else {
          warn('自动重启后端失败，启动自动重连')
          startAutoReconnect()
        }
      } catch (e) {
        warn('自动重启后端异常:', e)
        startAutoReconnect()
      }
    }
  }, 10000) // 10秒

  Modal.confirm({
    title: 'WebSocket连接异常',
    content: 'WebSocket连接已断开且多次重连失败，这可能是因为后端服务异常。请选择处理方式：（10秒后将自动重启后端服务）',
    okText: '重启整个应用',
    cancelText: '重启后端服务',
    centered: true,
    maskClosable: false,
    onOk: () => {
      // 清除自动重启定时器
      if (global.autoRestartTimer) {
        clearTimeout(global.autoRestartTimer)
        global.autoRestartTimer = undefined
      }
      autoRestartExecuted = true

      log('用户选择重启整个应用')
      // 显示关闭遮罩
      const { showClosingOverlay } = useAppClosing()
      showClosingOverlay()

      // 重启整个应用
      if ((window.electronAPI as any)?.appRestart) {
        ; (window.electronAPI as any).appRestart()
      } else if ((window.electronAPI as any)?.windowClose) {
        ; (window.electronAPI as any).windowClose()
      } else {
        window.location.reload()
      }
    },
    onCancel: async () => {
      // 清除自动重启定时器
      if (global.autoRestartTimer) {
        clearTimeout(global.autoRestartTimer)
        global.autoRestartTimer = undefined
      }
      autoRestartExecuted = true

      log('用户选择重启后端服务')
      // 重置重连状态并重启后端服务
      global.reconnectFailureModalShown = false
      resetReconnectState()

      try {
        // 重启后端服务
        const success = await restartBackend()
        if (success) {
          log('后端重启成功，开始重新连接')
          // 设置连接权限
          setConnectionPermission(true, '后端重启后重连')

          // 等待后端完全启动后重连
          setTimeout(async () => {
            try {
              const connected = await connectGlobalWebSocket('后端重启后重连')
              if (connected) {
                log('重启后端后WebSocket重连成功')
                setTimeout(() => {
                  setConnectionPermission(false, '正常运行中')
                }, 1000)
                startBackendMonitoring()
              } else {
                warn('重启后端后WebSocket重连失败，启动自动重连')
                startAutoReconnect()
              }
            } catch (e) {
              warn('重启后端后重连异常:', e)
              startAutoReconnect()
            }
          }, RESTART_DELAY)
        } else {
          warn('后端重启失败，启动自动重连')
          startAutoReconnect()
        }
      } catch (e) {
        warn('后端重启异常:', e)
        startAutoReconnect()
      }
    },
  })
}

// 重置重连状态
const resetReconnectState = () => {
  const global = getGlobalStorage()
  log(
    `重置重连状态，之前的重试次数: ${global.wsReconnectAttempts}，自动重连中: ${global.isAutoReconnecting}`
  )
  global.wsReconnectAttempts = 0
  global.reconnectFailureModalShown = false

  // 清除自动重启定时器
  if (global.autoRestartTimer) {
    clearTimeout(global.autoRestartTimer)
    global.autoRestartTimer = undefined
    log('已清除自动重启定时器')
  }

  stopAutoReconnect()
  log(`重连状态已重置，当前自动重连状态: ${global.isAutoReconnecting}`)
}

// 完全重置WebSocket状态
const resetWebSocketState = () => {
  const global = getGlobalStorage()

  log('完全重置WebSocket状态')

  // 重置连接状态
  global.isConnecting = false
  global.lastConnectAttempt = 0

  // 重置重连状态
  global.wsReconnectAttempts = 0
  global.isAutoReconnecting = false
  global.reconnectFailureModalShown = false

  // 清除所有定时器
  if (global.wsReconnectTimer) {
    clearTimeout(global.wsReconnectTimer)
    global.wsReconnectTimer = undefined
  }

  if (global.autoRestartTimer) {
    clearTimeout(global.autoRestartTimer)
    global.autoRestartTimer = undefined
  }

  // 重置连接权限
  setConnectionPermission(true, '状态重置')

  log('WebSocket状态完全重置完成')
}

const handleBackendFailure = async () => {
  const global = getGlobalStorage()
  log(`后端故障处理开始，当前重启尝试次数: ${global.backendRestartAttempts}`)

  if (global.backendRestartAttempts >= MAX_RESTART_ATTEMPTS) {
    warn('后端多次重启失败，显示最终错误弹窗')
    Modal.error({
      title: '后端服务异常',
      content: '后端服务多次重启失败，请重启整个应用程序。',
      okText: '重启应用',
      onOk: () => {
        // 显示关闭遮罩
        const { showClosingOverlay } = useAppClosing()
        showClosingOverlay()

        if ((window.electronAPI as any)?.appRestart) {
          ; (window.electronAPI as any).appRestart()
        } else if ((window.electronAPI as any)?.windowClose) {
          ; (window.electronAPI as any).windowClose()
        } else {
          window.location.reload()
        }
      },
    })
    return
  }

  setTimeout(async () => {
    log('尝试重启后端服务...')
    const success = await restartBackend()
    if (success) {
      log('后端重启成功，准备重新连接')
      // 统一在一个地方管理连接权限
      setConnectionPermission(true, '后端重启后重连')

      // 等待后端完全启动
      setTimeout(async () => {
        try {
          log('尝试重新建立WebSocket连接')
          const connected = await connectGlobalWebSocket('后端重启后重连')
          if (connected) {
            log('后端重启后WebSocket重连成功')
            // 连接成功后再禁用权限
            setTimeout(() => {
              setConnectionPermission(false, '正常运行中')
              resetReconnectState() // 重置重连状态
            }, 1000)
            startBackendMonitoring() // 启动后端监控
          } else {
            warn('后端重启后WebSocket重连失败')
            setConnectionPermission(false, '连接失败')
            // 如果重连失败，可以尝试启动自动重连
            startAutoReconnect()
          }
        } catch (e) {
          warn('重启后重连异常:', e)
          setConnectionPermission(false, '连接失败')
          startAutoReconnect()
        }
      }, RESTART_DELAY)
    } else {
      warn('后端重启失败，继续尝试')
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
const messageMatchesFilter = (
  message: WebSocketBaseMessage,
  filter: SubscriptionFilter
): boolean => {
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
      refCount: 1,
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

  // 强制输出消息处理信息，包含订阅数量
  const subscriptionCount = global.subscriptions.value.size
  logger.info(`[WS-MSG] 处理消息: type=${raw.type}, id=${raw.id}, 订阅数=${subscriptionCount}`)

  if (DEBUG) {
    log('收到原始消息:', { type: raw.type, id: raw.id, data: raw.data })
  }

  // 添加消息去重机制，防止同一消息被重复处理
  // 对于Update类型的消息，使用更精确的去重策略
  let messageKey: string
  if (raw.type === 'Update' && raw.data?.task_info) {
    // 对于任务更新消息，基于任务信息内容生成哈希
    const taskInfoHash = JSON.stringify(raw.data.task_info.map((task: any) => ({
      script_id: task.script_id,
      name: task.name,
      status: task.status,
      userCount: task.userList?.length || 0
    })))
    messageKey = `${raw.type}_${raw.id}_${taskInfoHash}`
  } else {
    messageKey = `${raw.type}_${raw.id}_${JSON.stringify(raw.data)}`
  }

  if (!global.lastProcessedMessages) {
    global.lastProcessedMessages = new Map()
  }

  // 检查是否在最近200ms内处理过相同的消息（增加时间窗口）
  const lastProcessed = global.lastProcessedMessages.get(messageKey)
  if (lastProcessed && now - lastProcessed < 200) {
    logger.warn(`[WS-MSG] 重复消息被过滤: ${messageKey.substring(0, 100)}...`)
    return
  }
  global.lastProcessedMessages.set(messageKey, now)

  // 清理过期的消息记录（保留最近2秒的记录）
  for (const [key, timestamp] of global.lastProcessedMessages.entries()) {
    if (now - timestamp > 2000) {
      global.lastProcessedMessages.delete(key)
    }
  }

  let dispatched = false
  let matchingSubscriptions = 0

  // 使用副本进行迭代，防止在处理函数中修改订阅列表导致的问题
  const subscriptionsCopy = new Map(global.subscriptions.value)

  // 输出所有订阅的详细信息
  logger.info(`[WS-MSG] 当前所有订阅:`)
  subscriptionsCopy.forEach((subscription, id) => {
    logger.info(`  - ${id}: ${JSON.stringify(subscription.filter)}`)
  })

  // 分发给所有匹配的订阅者
  subscriptionsCopy.forEach(subscription => {
    if (messageMatchesFilter(raw, subscription.filter)) {
      matchingSubscriptions++
      logger.info(`[WS-MSG] 匹配订阅: ${subscription.subscriptionId}`)
      try {
        // 再次检查订阅是否仍然存在，因为在同一个事件循环中它可能已被删除
        if (global.subscriptions.value.has(subscription.subscriptionId)) {
          subscription.handler(raw)
          dispatched = true
          logger.info(`[WS-MSG] 已分发给: ${subscription.subscriptionId}`)
        } else {
          logger.warn(`[WS-MSG] 订阅已被删除: ${subscription.subscriptionId}`)
        }
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
    handler,
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
  if (isGlobalConnectingLock) {
    forceWarn('连接锁已被占用')
    return false
  }
  isGlobalConnectingLock = true
  forceLog('连接锁已获取')
  return true
}
const releaseConnectionLock = () => {
  isGlobalConnectingLock = false
  forceLog('连接锁已释放')
}

const allowedConnectionReasons = [
  '后端启动后连接',
  '后端重启后重连',
  '系统初始化',
  '手动重连',
  '强制连接',
  'WebSocket自动重连',
  '断开后重连',
  '状态重置',
  '问题修复',
]
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
      forceLog('警告：尝试创建新连接但当前连接仍有效，直接返回现有连接')
      return global.wsRef
    }
    if (global.wsRef.readyState === WebSocket.CONNECTING) {
      forceLog('警告：尝试创建新连接但当前连接正在建立中，直接返回现有连接')
      return global.wsRef
    }
    // 清理已关闭或错误状态的连接
    forceLog(`清理旧的WebSocket连接，状态: ${global.wsRef.readyState}`)
    global.wsRef = null
  }

  forceLog(`创建新的WebSocket连接: ${BASE_WS_URL}`)
  const ws = new WebSocket(BASE_WS_URL)
  global.wsRef = ws
  forceLog(`WebSocket对象已创建，初始状态: ${ws.readyState}`)

  ws.onopen = () => {
    forceLog('WebSocket连接已打开，连接成功！')
    global.isConnecting = false
    global.hasEverConnected = true
    global.reconnectAttempts = 0
    setGlobalStatus('已连接')
    setBackendStatus('running') // WebSocket连接成功时设置后端为运行状态
    startGlobalHeartbeat(ws)

    // 立即重置WebSocket重连状态
    forceLog('重置重连状态，连接已成功建立')
    resetReconnectState()

    // 连接成功后的权限管理
    // 对于自动重连，延迟设置权限以确保重连机制不被阻止
    if (global.connectionReason === 'WebSocket自动重连') {
      // 自动重连成功后，延迟设置权限，确保不会立即阻止下次重连
      setTimeout(() => {
        setConnectionPermission(false, '正常运行中')
      }, 2000) // 增加延迟时间
    } else if (global.connectionReason !== '系统初始化') {
      // 其他情况下正常设置权限
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

  ws.onerror = error => {
    forceLog('WebSocket发生错误:', error)
    setGlobalStatus('连接错误')
    setBackendStatus('error') // WebSocket错误时设置后端为错误状态
    warn('WebSocket错误:', error)
  }

  ws.onclose = event => {
    forceLog(`WebSocket连接关闭事件触发: code=${event.code}, reason="${event.reason}"`)
    setGlobalStatus('已断开')
    // WebSocket断开时设置后端状态
    if (event.code === 1000 && (event.reason === 'Ping超时' || event.reason === '心跳超时')) {
      setBackendStatus('error')
    } else {
      setBackendStatus('stopped')
    }
    stopGlobalHeartbeat()
    global.isConnecting = false

    forceLog(`WebSocket连接关闭详情: code=${event.code}, reason="${event.reason}"`)

    // 重置一些可能阻止重连的状态
    global.lastConnectAttempt = 0

    // 根据关闭原因决定处理方式
    if (event.code === 1000 && (event.reason === 'Ping超时' || event.reason === '心跳超时')) {
      // 心跳超时通常意味着后端有问题，直接处理后端故障
      handleBackendFailure().catch(e => warn('handleBackendFailure error:', e))
    } else if (event.code === 1000 && event.reason === '正常关闭') {
      // 明确的正常关闭，不重连
      log('WebSocket正常关闭，不启动重连')
    } else {
      // 所有其他情况都尝试自动重连（包括异常断开、后端关闭等）
      forceLog(`检测到连接断开 (code=${event.code}, reason="${event.reason}")，启动自动重连`)

      // 确保重连不会被阻止
      if (!global.allowNewConnection) {
        forceLog('连接权限被禁用，重置权限以允许重连')
        setConnectionPermission(true, '断开后重连')
      }

      // 如果当前正在重连过程中，直接触发下一次重连尝试
      if (global.isAutoReconnecting) {
        forceLog('当前已在重连中，触发下一次重连尝试')
        // 重置连接状态，让重连流程继续
        global.isConnecting = false
        setGlobalStatus('已断开')
        // 直接调用attemptReconnect来继续重连流程
        // 但是我们需要访问attemptReconnect函数，这里先用一个简单的方法
        setTimeout(() => {
          if (global.wsReconnectAttempts < 5) { // MAX_WS_RECONNECT_ATTEMPTS
            forceLog('延迟触发下一次重连尝试')
            // 这里我们需要一个方法来继续重连，暂时重置状态让新的重连开始
            global.isAutoReconnecting = false
            startAutoReconnect()
          }
        }, 1000) // 1秒后继续重连
      } else {
        forceLog('即将调用startAutoReconnect函数')
        startAutoReconnect()
        forceLog('startAutoReconnect函数调用完成')
      }
    }
  }

  return ws
}

const connectGlobalWebSocket = async (reason: string = '手动重连'): Promise<boolean> => {
  const global = getGlobalStorage()

  // 对于自动重连，如果权限被禁用，先尝试重置权限
  if (reason === 'WebSocket自动重连' && !checkConnectionPermission()) {
    forceLog('自动重连权限被禁用，尝试重置权限')
    setConnectionPermission(true, 'WebSocket自动重连')
  }

  forceLog(`connectGlobalWebSocket被调用，原因: ${reason}，权限: ${checkConnectionPermission()}`)

  if (!checkConnectionPermission() || !isValidConnectionReason(reason)) {
    forceWarn(
      `连接被拒绝: 权限=${checkConnectionPermission()}, 原因="${reason}"是否有效=${isValidConnectionReason(reason)}`
    )
    return false
  }
  if (!acquireConnectionLock()) {
    forceWarn('获取连接锁失败')
    return false
  }

  try {
    forceLog('开始连接检查流程')

    if (global.wsRef) {
      const state = global.wsRef.readyState
      forceLog(`现有WebSocket状态: ${state}`)
      if (state === WebSocket.OPEN) {
        forceLog('现有连接已打开，直接返回成功')
        setGlobalStatus('已连接')
        return true
      }
      if (state === WebSocket.CONNECTING) {
        forceLog('现有连接正在建立中，直接返回成功')
        setGlobalStatus('连接中')
        return true
      }
      if (state === WebSocket.CLOSING) {
        forceWarn('现有连接正在关闭中，返回失败')
        return false
      }
    } else {
      forceLog('没有现有WebSocket连接')
    }

    if (global.isConnecting) {
      forceWarn('已在连接中，返回失败')
      return false
    }

    const now = Date.now()
    const timeSinceLastAttempt = global.lastConnectAttempt ? now - global.lastConnectAttempt : 0
    forceLog(`距离上次连接尝试: ${timeSinceLastAttempt}ms`)
    if (global.lastConnectAttempt && timeSinceLastAttempt < 2000) {
      forceWarn(`连接尝试过于频繁，距离上次: ${timeSinceLastAttempt}ms`)
      return false
    }

    forceLog('开始创建新的WebSocket连接')
    global.isConnecting = true
    global.lastConnectAttempt = now
    if (global.wsRef?.readyState === WebSocket.CLOSED) global.wsRef = null

    global.wsRef = createGlobalWebSocket()
    setGlobalStatus('连接中')
    forceLog('WebSocket连接创建完成，返回成功')
    return true
  } catch (e) {
    forceWarn('connectGlobalWebSocket异常:', e)
    setGlobalStatus('连接错误')
    global.isConnecting = false
    return false
  } finally {
    releaseConnectionLock()
  }
}

export const connectAfterBackendStart = async (): Promise<boolean> => {
  setConnectionPermission(true, '后端启动后连接')

  // 尝试连接，最多重试3次
  for (let attempt = 1; attempt <= 3; attempt++) {
    try {
      log(`后端启动后连接WebSocket，第${attempt}次尝试`)
      const connected = await connectGlobalWebSocket('后端启动后连接')
      if (connected) {
        startBackendMonitoring()
        setConnectionPermission(false, '正常运行中')
        log('后端启动后WebSocket连接成功')
        return true
      }

      // 如果不是最后一次尝试，等待一下再重试
      if (attempt < 3) {
        log(`第${attempt}次连接失败，等待2秒后重试`)
        await new Promise(resolve => setTimeout(resolve, 2000))
      }
    } catch (e) {
      warn(`第${attempt}次连接异常:`, e)
      if (attempt < 3) {
        await new Promise(resolve => setTimeout(resolve, 2000))
      }
    }
  }

  log('后端启动后WebSocket连接失败，已重试3次')
  return false
}

// 强制连接模式，用于跳过初始化时
export const forceConnectWebSocket = async (): Promise<boolean> => {
  log('强制WebSocket连接模式开始')

  const global = getGlobalStorage()

  // 显示当前状态
  log('当前连接状态:', {
    status: global.status.value,
    wsReadyState: global.wsRef?.readyState,
    allowNewConnection: global.allowNewConnection,
    connectionReason: global.connectionReason,
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
    }, 2000) // 增加到2秒
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

// 将订阅ID存储在全局存储中，避免模块重载导致的变量重置

const initializeGlobalSubscriptions = () => {
  const global = getGlobalStorage()

  forceLog('initializeGlobalSubscriptions被调用')
  forceLog(`当前订阅数量: ${global.subscriptions.value.size}`)
  forceLog(`现有TaskManager订阅ID: ${global.globalTaskManagerSubscriptionId}`)
  forceLog(`现有Main订阅ID: ${global.globalMainSubscriptionId}`)

  // 清理旧的订阅
  if (global.globalTaskManagerSubscriptionId) {
    unsubscribe(global.globalTaskManagerSubscriptionId)
    global.globalTaskManagerSubscriptionId = undefined
    forceLog('清理旧的TaskManager订阅')
  }

  if (global.globalMainSubscriptionId) {
    unsubscribe(global.globalMainSubscriptionId)
    global.globalMainSubscriptionId = undefined
    forceLog('清理旧的Main订阅')
  }

  // 创建新的订阅
  global.globalTaskManagerSubscriptionId = subscribe({ id: 'TaskManager' }, (msg: WebSocketBaseMessage) => {
    try {
      ExternalWSHandlers.taskManagerMessage(msg)
    } catch (e) {
      warn('External taskManagerMessage handler error:', e)
    }
  })

  global.globalMainSubscriptionId = subscribe({ id: 'Main' }, (msg: WebSocketBaseMessage) => {
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

  forceLog(`全局订阅已初始化: TaskManager=${global.globalTaskManagerSubscriptionId}, Main=${global.globalMainSubscriptionId}`)
  forceLog(`初始化后订阅数量: ${global.subscriptions.value.size}`)
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
        if (DEBUG && type !== 'Signal') {
          // 避免心跳消息spam日志
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
        message: { id, type, data },
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
    // WebSocket重连相关信息
    wsReconnectAttempts: global.wsReconnectAttempts,
    isAutoReconnecting: global.isAutoReconnecting,
    lastDisconnectTime: global.lastDisconnectTime,
    reconnectFailureModalShown: global.reconnectFailureModalShown,
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
    allowedReasons: allowedConnectionReasons,
  }

  // 在开发模式下暴露调试功能到全局
  if (DEBUG && typeof window !== 'undefined') {
    ; (window as any).wsDebug = debug
  }

  // 手动重连功能
  const manualReconnect = async () => {
    log('用户手动触发重连')

    const global = getGlobalStorage()

    // 重置所有可能阻止重连的状态
    global.isConnecting = false
    global.lastConnectAttempt = 0
    global.reconnectFailureModalShown = false

    // 停止现有的重连尝试
    stopAutoReconnect()

    // 重置重连状态
    resetReconnectState()

    setConnectionPermission(true, '手动重连')

    try {
      const connected = await connectGlobalWebSocket('手动重连')
      if (connected) {
        log('手动重连成功')
        setConnectionPermission(false, '正常运行中')
        startBackendMonitoring() // 启动后端监控
        return true
      } else {
        warn('手动重连失败')
        return false
      }
    } catch (e) {
      warn('手动重连异常:', e)
      return false
    }
  }

  // 重置重连状态
  const resetReconnect = () => {
    log('用户重置重连状态')
    resetReconnectState()
  }

  // 完全重置WebSocket状态
  const resetWebSocketStateManually = () => {
    log('用户完全重置WebSocket状态')
    resetWebSocketState()
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
    manualReconnect,
    resetReconnect,
    resetWebSocketState: resetWebSocketStateManually,
    connectAfterBackendStart,
    debug: DEBUG ? debug : undefined,
  }
}

// ====== 页面卸载保护 ======
window.addEventListener('beforeunload', () => {
  // 保持连接
})

// ====== 模块加载计数 ======
const global = getGlobalStorage()
if (global.moduleLoadCount === 0) global.moduleLoadCount = 1
