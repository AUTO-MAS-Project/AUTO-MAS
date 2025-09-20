import { ref, type Ref } from 'vue'
import { message, Modal, notification } from 'ant-design-vue'

// 基础配置
const BASE_WS_URL = 'ws://localhost:36163/api/core/ws'
const HEARTBEAT_INTERVAL = 15000
const HEARTBEAT_TIMEOUT = 5000
const BACKEND_CHECK_INTERVAL = 3000 // 后端检查间隔
const MAX_RESTART_ATTEMPTS = 3 // 最大重启尝试次数
const RESTART_DELAY = 2000 // 重启延迟

// 类型定义
export type WebSocketStatus = '连接中' | '已连接' | '已断开' | '连接错误'

export interface WebSocketBaseMessage {
  id?: string
  type: string
  data?: any
}

export interface ProgressMessage {
  percent?: number
  status?: string
  msg?: string
}

export interface ResultMessage {
  success?: boolean
  result?: any
}

export interface ErrorMessage {
  msg?: string
  code?: number
}

export interface NotifyMessage {
  title?: string
  content?: string
}

export interface WebSocketSubscriber {
  id: string
  onProgress?: (data: ProgressMessage) => void
  onResult?: (data: ResultMessage) => void
  onError?: (err: ErrorMessage) => void
  onNotify?: (n: NotifyMessage) => void
}

// 后端状态类型
export type BackendStatus = 'unknown' | 'starting' | 'running' | 'stopped' | 'error'

// 全局存储接口 - 添加后端管理和连接控制
interface GlobalWSStorage {
  wsRef: WebSocket | null
  status: Ref<WebSocketStatus>
  subscribers: Ref<Map<string, WebSocketSubscriber>>
  // 修改消息队列结构，使用Map存储消息和时间戳
  messageQueue: Ref<Map<string, { message: WebSocketBaseMessage; timestamp: number }>>
  heartbeatTimer?: number
  isConnecting: boolean
  lastPingTime: number
  connectionId: string
  moduleLoadCount: number
  createdAt: number
  hasEverConnected: boolean
  reconnectAttempts: number
  // 新增：后端管理
  backendStatus: Ref<BackendStatus>
  backendCheckTimer?: number
  backendRestartAttempts: number
  isRestartingBackend: boolean
  lastBackendCheck: number
  // 新增：连接保护
  lastConnectAttempt: number
  // 新增：连接权限控制
  allowNewConnection: boolean
  connectionReason: string
}

const WS_STORAGE_KEY = Symbol.for('GLOBAL_WEBSOCKET_PERSISTENT')

// 初始化全局存储
const initGlobalStorage = (): GlobalWSStorage => {
  return {
    wsRef: null,
    status: ref<WebSocketStatus>('已断开'),
    subscribers: ref(new Map<string, WebSocketSubscriber>()),
    // 初始化消息队列
    messageQueue: ref(new Map<string, { message: WebSocketBaseMessage; timestamp: number }>()),
    heartbeatTimer: undefined,
    isConnecting: false,
    lastPingTime: 0,
    connectionId: Math.random().toString(36).substring(2, 9),
    moduleLoadCount: 0,
    createdAt: Date.now(),
    hasEverConnected: false,
    reconnectAttempts: 0,
    // 后端管理
    backendStatus: ref<BackendStatus>('unknown'),
    backendCheckTimer: undefined,
    backendRestartAttempts: 0,
    isRestartingBackend: false,
    lastBackendCheck: 0,
    // 连接保护
    lastConnectAttempt: 0,
    // 连接权限控制
    allowNewConnection: true, // 初始化时允许创建连接
    connectionReason: '系统初始化',
  }
}

// 获取全局存储
const getGlobalStorage = (): GlobalWSStorage => {
  if (!(window as any)[WS_STORAGE_KEY]) {
    ;(window as any)[WS_STORAGE_KEY] = initGlobalStorage()
  }

  return (window as any)[WS_STORAGE_KEY] as GlobalWSStorage
}

// 设置全局状态
const setGlobalStatus = (status: WebSocketStatus) => {
  const global = getGlobalStorage()
  global.status.value = status
}

// 设置后端状态
const setBackendStatus = (status: BackendStatus) => {
  const global = getGlobalStorage()
  global.backendStatus.value = status
}

// 检查后端是否运行（通过WebSocket连接状态判断）
const checkBackendStatus = (): boolean => {
  const global = getGlobalStorage()

  // 如果WebSocket存在且状态为OPEN，说明后端运行正常
  if (global.wsRef && global.wsRef.readyState === WebSocket.OPEN) {
    return true
  }

  // 如果WebSocket不存在或状态不是OPEN，说明后端可能有问题
  return false
}

// 重启后端
const restartBackend = async (): Promise<boolean> => {
  const global = getGlobalStorage()

  if (global.isRestartingBackend) {
    return false
  }

  try {
    global.isRestartingBackend = true
    global.backendRestartAttempts++

    setBackendStatus('starting')

    // 调用 Electron API 重启后端
    if ((window.electronAPI as any)?.startBackend) {
      const result = await (window.electronAPI as any).startBackend()
      if (result.success) {
        setBackendStatus('running')
        global.backendRestartAttempts = 0
        return true
      } else {
        setBackendStatus('error')
        return false
      }
    } else {
      setBackendStatus('error')
      return false
    }
  } catch (error) {
    setBackendStatus('error')
    return false
  } finally {
    global.isRestartingBackend = false
  }
}

// 后端监控和重启逻辑
const handleBackendFailure = async () => {
  const global = getGlobalStorage()

  if (global.backendRestartAttempts >= MAX_RESTART_ATTEMPTS) {
    // 弹窗提示用户重启整个应用
    Modal.error({
      title: '后端服务异常',
      content: '后端服务多次重启失败，请重启整个应用程序。',
      okText: '重启应用',
      onOk: () => {
        if ((window.electronAPI as any)?.windowClose) {
          ;(window.electronAPI as any).windowClose()
        } else {
          window.location.reload()
        }
      },
    })
    return
  }

  // 尝试重启后端
  setTimeout(async () => {
    const success = await restartBackend()
    if (success) {
      // 重启成功，允许重连并等待一段时间后重新连接 WebSocket
      setConnectionPermission(true, '后端重启后重连')
      setTimeout(() => {
        connectGlobalWebSocket('后端重启后重连').then(() => {
          // 连接完成后禁止新连接
          setConnectionPermission(false, '正常运行中')
        })
      }, RESTART_DELAY)
    } else {
      // 重启失败，继续监控
      setTimeout(handleBackendFailure, RESTART_DELAY)
    }
  }, RESTART_DELAY)
}

// 启动后端监控（仅基于WebSocket状态）
const startBackendMonitoring = () => {
  const global = getGlobalStorage()

  if (global.backendCheckTimer) {
    clearInterval(global.backendCheckTimer)
  }

  global.backendCheckTimer = window.setInterval(() => {
    const isRunning = checkBackendStatus()
    const now = Date.now()
    global.lastBackendCheck = now

    // 基于 WebSocket 状态判断后端运行状态
    if (isRunning) {
      // WebSocket连接正常
      if (global.backendStatus.value !== 'running') {
        setBackendStatus('running')
        global.backendRestartAttempts = 0 // 重置重启计数
      }
    } else {
      // WebSocket连接异常，但不频繁报告
      const shouldReportStatus = global.backendStatus.value === 'running'
      if (shouldReportStatus) {
        setBackendStatus('stopped')
      }
    }

    // 仅在必要时检查心跳超时
    if (global.lastPingTime > 0 && now - global.lastPingTime > HEARTBEAT_TIMEOUT * 2) {
      if (global.wsRef && global.wsRef.readyState === WebSocket.OPEN) {
        setBackendStatus('error')
      }
    }
  }, BACKEND_CHECK_INTERVAL * 2) // 降低检查频率
}

// 停止心跳
const stopGlobalHeartbeat = () => {
  const global = getGlobalStorage()
  if (global.heartbeatTimer) {
    clearInterval(global.heartbeatTimer)
    global.heartbeatTimer = undefined
  }
}

// 启动心跳
const startGlobalHeartbeat = (ws: WebSocket) => {
  const global = getGlobalStorage()
  stopGlobalHeartbeat()

  global.heartbeatTimer = window.setInterval(() => {
    if (ws.readyState === WebSocket.OPEN) {
      try {
        const pingTime = Date.now()
        global.lastPingTime = pingTime
        ws.send(
          JSON.stringify({
            type: 'Signal',
            data: { Ping: pingTime, connectionId: global.connectionId },
          })
        )
        setTimeout(() => {
          /* 心跳超时不主动断开 */
        }, HEARTBEAT_TIMEOUT)
      } catch {
        /* ignore */
      }
    }
  }, HEARTBEAT_INTERVAL)
}

// 获取消息队列
const getMessageQueue = (): Map<string, { message: WebSocketBaseMessage; timestamp: number }> => {
  const global = getGlobalStorage()
  return global.messageQueue.value
}

// 设置消息队列
const setMessageQueue = (queue: Map<string, { message: WebSocketBaseMessage; timestamp: number }>): void => {
  const global = getGlobalStorage()
  global.messageQueue.value = queue
}

const handleMessage = (raw: WebSocketBaseMessage) => {
  const global = getGlobalStorage()
  const msgType = String(raw.type)
  const id = raw.id

  // 添加原始消息调试
  console.log('[WebSocket Debug] 收到原始消息:', {
    type: msgType,
    id: id,
    data: raw.data,
    fullMessage: raw
  })

  // 优先处理Signal类型的ping-pong消息，不受id限制
  if (msgType === 'Signal') {
    // 处理心跳响应
    if (raw.data && raw.data.Pong) {
      global.lastPingTime = 0 // 重置ping时间，表示收到了响应
      return
    }

    // 处理后端发送的Ping，回复Pong
    if (raw.data && raw.data.Ping) {
      const ws = global.wsRef
      if (ws && ws.readyState === WebSocket.OPEN) {
        try {
          ws.send(
            JSON.stringify({
              type: 'Signal',
              data: { Pong: raw.data.Ping, connectionId: global.connectionId },
            })
          )
        } catch (e) {
          // Pong发送失败，静默处理
        }
      }
      return
    }
  }

  const dispatch = (sub: WebSocketSubscriber) => {
    if (msgType === 'Signal') return

    if (msgType === 'Progress') return sub.onProgress?.(raw.data as ProgressMessage)
    if (msgType === 'Result') return sub.onResult?.(raw.data as ResultMessage)
    if (msgType === 'Update') {
      // 处理Update类型消息，当作Progress处理
      console.log('[WebSocket Debug] 收到Update消息:', raw)
      return sub.onProgress?.(raw as any)
    }
    if (msgType === 'Info') {
      // 处理Info类型消息，当作Notify处理
      console.log('[WebSocket Debug] 收到Info消息:', raw)
      return sub.onNotify?.(raw as any)
    }
    if (msgType === 'Message') {
      // 处理Message类型消息，当作Notify处理
      console.log('[WebSocket Debug] 收到Message消息:', raw)
      return sub.onNotify?.(raw as any)
    }
    if (msgType === 'Error') {
      sub.onError?.(raw.data as ErrorMessage)
      if (!sub.onError && raw.data && (raw.data as ErrorMessage).msg) {
        message.error((raw.data as ErrorMessage).msg)
      }
      return
    }
    if (msgType === 'Notify') {
      sub.onNotify?.(raw.data as NotifyMessage)
      if (raw.data && (raw.data as NotifyMessage).title) {
        notification.info({
          message: (raw.data as NotifyMessage).title,
          description: (raw.data as NotifyMessage).content,
        })
      }
      return
    }
    // 其他类型可扩展
    console.log('[WebSocket Debug] 未处理的消息类型:', msgType, raw)
  }

  if (id) {
    const sub = global.subscribers.value.get(id)
    console.log('[WebSocket Debug] 查找订阅者:', {
      messageId: id,
      hasSubscriber: !!sub,
      totalSubscribers: global.subscribers.value.size,
      allSubscriberIds: Array.from(global.subscribers.value.keys())
    })
    if (sub) {
      console.log('[WebSocket Debug] 分发消息给订阅者:', id)
      dispatch(sub)
    } else {
      // 将没有订阅者的消息暂存到消息队列中
      console.warn('[WebSocket Debug] 未找到对应的订阅者，将消息暂存到队列中:', id)
      const messageQueue = getMessageQueue()
      messageQueue.set(id, {
        message: raw,
        timestamp: Date.now()
      })
      setMessageQueue(messageQueue)
      
      // 清理过期消息（超过1分钟的消息）
      const now = Date.now()
      messageQueue.forEach((queued, msgId) => {
        if (now - queued.timestamp > 60000) { // 1分钟 = 60000毫秒
          console.log('[WebSocket] 清理过期消息:', msgId)
          messageQueue.delete(msgId)
        }
      })
      setMessageQueue(messageQueue)
    }
  }
  // 移除无id消息的处理逻辑，因为后端不会发送这类消息
}

// 后端启动后建立连接的公开函数
export const connectAfterBackendStart = async (): Promise<boolean> => {
  setConnectionPermission(true, '后端启动后连接')

  try {
    const connected = await connectGlobalWebSocket('后端启动后连接')
    if (connected) {
      startBackendMonitoring()
      // 连接完成后禁止新连接
      setConnectionPermission(false, '正常运行中')
      return true
    } else {
      return false
    }
  } catch (error) {
    return false
  }
}

// 创建 WebSocket 连接
const createGlobalWebSocket = (): WebSocket => {
  const global = getGlobalStorage()

  // 检查现有连接状态
  if (global.wsRef) {
    if (global.wsRef.readyState === WebSocket.OPEN) {
      return global.wsRef
    }

    if (global.wsRef.readyState === WebSocket.CONNECTING) {
      return global.wsRef
    }
  }

  const ws = new WebSocket(BASE_WS_URL)

  ws.onopen = () => {
    global.isConnecting = false
    global.hasEverConnected = true
    global.reconnectAttempts = 0
    setGlobalStatus('已连接')

    startGlobalHeartbeat(ws)

    // 连接成功后禁止新连接
    setConnectionPermission(false, '正常运行中')

    // 发送连接确认和初始pong
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
    } catch {
      /* ignore */
    }
    
    // 自动订阅ID为"Main"的消息，用于处理ping-pong等系统消息
    _subscribe("Main", {
      onNotify: () => {
        // Main ID的消息通常不包含需要处理的Notify内容，但保留处理函数以确保订阅完整性
      }
    });
  }

  ws.onmessage = ev => {
    try {
      const raw = JSON.parse(ev.data) as WebSocketBaseMessage
      handleMessage(raw)
    } catch (e) {
      // 消息解析失败，静默处理
    }
  }

  ws.onerror = () => {
    setGlobalStatus('连接错误')
  }

  ws.onclose = event => {
    setGlobalStatus('已断开')
    stopGlobalHeartbeat()
    global.isConnecting = false

    // 检查是否是后端自杀导致的关闭
    if (event.code === 1000 && event.reason === 'Ping超时') {
      handleBackendFailure().catch(error => {
        // 忽略错误，或者可以添加适当的错误处理
        console.warn('handleBackendFailure error:', error)
      })
    } else {
      // 连接断开，不自动重连，等待后端重启
      setGlobalStatus('已断开')
    }
  }

  // 为新创建的 WebSocket 设置引用
  global.wsRef = ws

  return ws
}

// 连接全局 WebSocket
const connectGlobalWebSocket = async (reason: string = '未指定原因'): Promise<boolean> => {
  const global = getGlobalStorage()

  // 首先检查连接权限
  if (!checkConnectionPermission()) {
    return false
  }

  // 验证连接原因是否合法
  if (!isValidConnectionReason(reason)) {
    return false
  }

  // 尝试获取全局连接锁
  if (!acquireConnectionLock()) {
    return false
  }

  try {
    // 严格检查现有连接，避免重复创建
    if (global.wsRef) {
      const state = global.wsRef.readyState

      if (state === WebSocket.OPEN) {
        setGlobalStatus('已连接')
        return true
      }

      if (state === WebSocket.CONNECTING) {
        return true
      }

      // CLOSING 或 CLOSED 状态才允许创建新连接
      if (state === WebSocket.CLOSING) {
        return false
      }
    }

    // 检查全局连接标志 - 增强防重复逻辑
    if (global.isConnecting) {
      return false
    }

    // 额外保护：检查最近连接尝试时间，避免过于频繁的连接
    const now = Date.now()
    const MIN_CONNECT_INTERVAL = 2000 // 最小连接间隔2秒
    if (global.lastConnectAttempt && now - global.lastConnectAttempt < MIN_CONNECT_INTERVAL) {
      return false
    }

    global.isConnecting = true
    global.lastConnectAttempt = now

    // 清理旧连接引用（如果存在且已关闭）
    if (global.wsRef && global.wsRef.readyState === WebSocket.CLOSED) {
      global.wsRef = null
    }

    global.wsRef = createGlobalWebSocket()
    setGlobalStatus('连接中')
    return true
  } catch (e) {
    setGlobalStatus('连接错误')
    global.isConnecting = false
    return false
  } finally {
    // 确保始终释放连接锁
    releaseConnectionLock()
  }
}

// 连接权限控制函数
const setConnectionPermission = (allow: boolean, reason: string) => {
  const global = getGlobalStorage()
  global.allowNewConnection = allow
  global.connectionReason = reason
}

const checkConnectionPermission = (): boolean => {
  const global = getGlobalStorage()
  return global.allowNewConnection
}

// 只在后端启动/重启时允许创建连接
const allowedConnectionReasons = ['后端启动后连接', '后端重启后重连']

const isValidConnectionReason = (reason: string): boolean =>
  allowedConnectionReasons.includes(reason)

// 全局连接锁 - 防止多个模块实例同时连接
let isGlobalConnectingLock = false

// 获取全局连接锁
const acquireConnectionLock = (): boolean => {
  if (isGlobalConnectingLock) {
    return false
  }
  isGlobalConnectingLock = true
  return true
}

// 释放全局连接锁
const releaseConnectionLock = () => {
  isGlobalConnectingLock = false
}

// 模块初始化逻辑 - 不自动建立连接
const global = getGlobalStorage()

// 只在模块真正加载时计数一次
if (global.moduleLoadCount === 0) {
  global.moduleLoadCount = 1
}

// 页面卸载时不关闭连接，保持永久连接
window.addEventListener('beforeunload', () => {
  // 保持连接
})

// 主要 Hook 函数
export function useWebSocket() {
  const global = getGlobalStorage()

  const subscribe = (id: string, handlers: Omit<WebSocketSubscriber, 'id'>) => {
    // 使用全局的subscribe函数来确保消息队列机制正常工作
    _subscribe(id, handlers);
  }

  const unsubscribe = (id: string) => {
    global.subscribers.value.delete(id)
  }

  const sendRaw = (type: string, data?: any, id?: string) => {
    const ws = global.wsRef

    if (ws && ws.readyState === WebSocket.OPEN) {
      try {
        ws.send(JSON.stringify({ id, type, data }))
      } catch (e) {
        // 发送失败，静默处理
      }
    }
  }

  const getConnectionInfo = () => ({
    connectionId: global.connectionId,
    status: global.status.value,
    subscriberCount: global.subscribers.value.size,
    moduleLoadCount: global.moduleLoadCount,
    wsReadyState: global.wsRef ? global.wsRef.readyState : null,
    isConnecting: global.isConnecting,
    hasHeartbeat: !!global.heartbeatTimer,
    hasEverConnected: global.hasEverConnected,
    reconnectAttempts: global.reconnectAttempts,
    isPersistentMode: true, // 标识为永久连接模式
  })

  const restartBackendManually = async () => {
    const global = getGlobalStorage()
    global.backendRestartAttempts = 0
    return await restartBackend()
  }

  const getBackendStatus = () => {
    const global = getGlobalStorage()
    return {
      status: global.backendStatus.value,
      restartAttempts: global.backendRestartAttempts,
      isRestarting: global.isRestartingBackend,
      lastCheck: global.lastBackendCheck,
    }
  }

  return {
    subscribe,
    unsubscribe,
    sendRaw,
    getConnectionInfo,
    status: global.status,
    subscribers: global.subscribers,
    backendStatus: global.backendStatus,
    restartBackend: restartBackendManually,
    getBackendStatus,
  }
}

/**
 * 订阅指定ID的消息
 * @param id 消息ID
 * @param subscriber 订阅者对象
 */
export const _subscribe = (id: string, subscriber: Omit<WebSocketSubscriber, 'id'>) => {
  const global = getGlobalStorage()
  const fullSubscriber: WebSocketSubscriber = { ...subscriber, id }
  
  // 添加订阅者
  global.subscribers.value.set(id, fullSubscriber)
  console.log('[WebSocket] 添加订阅者:', id, '当前订阅者数量:', global.subscribers.value.size)
  
  // 检查消息队列中是否有该订阅者的消息
  const messageQueue = getMessageQueue()
  console.log('[WebSocket] 检查消息队列，当前队列大小:', messageQueue.size, '队列内容:', Array.from(messageQueue.entries()))
  
  // 检查特定ID的消息
  const queuedMessage = messageQueue.get(id)
  if (queuedMessage) {
    console.log('[WebSocket] 发现队列中的消息，立即分发给新订阅者:', id, '消息内容:', queuedMessage)
    // 创建临时订阅者对象用于分发消息
    const tempSubscriber: WebSocketSubscriber = { ...subscriber, id }
    console.log('[WebSocket] 开始处理遗留消息，订阅者ID:', id, '消息:', queuedMessage.message)
    try {
      handleMessageDispatch(queuedMessage.message, tempSubscriber)
      console.log('[WebSocket] 遗留消息处理完成，订阅者ID:', id)
    } catch (error) {
      console.error('[WebSocket] 处理遗留消息时出错，订阅者ID:', id, '错误:', error)
    }
    // 从队列中移除已处理的消息
    messageQueue.delete(id)
    setMessageQueue(messageQueue)
    console.log('[WebSocket] 已从队列中移除消息，剩余队列大小:', messageQueue.size)
  } else {
    console.log('[WebSocket] 未在队列中找到ID为', id, '的消息')
  }
  
  // 清理过期消息（超过1分钟的消息）
  const now = Date.now()
  let cleanedCount = 0
  messageQueue.forEach((queued, msgId) => {
    if (now - queued.timestamp > 60000) { // 1分钟 = 60000毫秒
      console.log('[WebSocket] 清理过期消息:', msgId, '消息内容:', queued.message, '时间戳:', queued.timestamp)
      messageQueue.delete(msgId)
      cleanedCount++
    }
  })
  if (cleanedCount > 0) {
    console.log('[WebSocket] 共清理过期消息数量:', cleanedCount)
    setMessageQueue(messageQueue)
  }
}

// 新增函数：处理消息分发
const handleMessageDispatch = (raw: WebSocketBaseMessage, sub: WebSocketSubscriber) => {
  const msgType = raw.type

  if (msgType === 'Signal') return

  if (msgType === 'Progress') return sub.onProgress?.(raw.data as ProgressMessage)
  if (msgType === 'Result') return sub.onResult?.(raw.data as ResultMessage)
  if (msgType === 'Update') {
    // 处理Update类型消息，当作Progress处理
    console.log('[WebSocket Debug] 分发Update消息:', raw)
    return sub.onProgress?.(raw as any)
  }
  if (msgType === 'Info') {
    // 处理Info类型消息，当作Notify处理
    console.log('[WebSocket Debug] 分发Info消息:', raw)
    return sub.onNotify?.(raw as any)
  }
  if (msgType === 'Message') {
    // 处理Message类型消息，当作Notify处理
    console.log('[WebSocket Debug] 分发Message消息:', raw)
    return sub.onNotify?.(raw as any)
  }
  if (msgType === 'Error') {
    sub.onError?.(raw.data as ErrorMessage)
    if (!sub.onError && raw.data && (raw.data as ErrorMessage).msg) {
      message.error((raw.data as ErrorMessage).msg)
    }
    return
  }
  if (msgType === 'Notify') {
    sub.onNotify?.(raw.data as NotifyMessage)
    if (raw.data && (raw.data as NotifyMessage).title) {
      notification.info({
        message: (raw.data as NotifyMessage).title,
        description: (raw.data as NotifyMessage).content,
      })
    }
    return
  }
  
  // 其他类型可扩展
  console.log('[WebSocket Debug] 未处理的消息类型:', msgType, raw)
}
