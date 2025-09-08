import { ref, type Ref } from 'vue'
import { message, notification } from 'ant-design-vue'

// WebSocket 调试开关
const WS_DEV = true
const WS_VERSION = 'v2.5-PERSISTENT-' + Date.now()
console.log(`🚀 WebSocket 模块已加载: ${WS_VERSION} - 永久连接模式`)

// 基础配置
const BASE_WS_URL = 'ws://localhost:36163/api/core/ws'
const HEARTBEAT_INTERVAL = 15000
const HEARTBEAT_TIMEOUT = 5000

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
  // 兼容旧版 API
  onMessage?: (raw: WebSocketBaseMessage) => void
  onStatusChange?: (status: WebSocketStatus) => void
}

// 兼容旧版 connect(config) 接口
export interface WebSocketConfig {
  taskId: string
  mode?: string
  showNotifications?: boolean
  onProgress?: (data: ProgressMessage) => void
  onResult?: (data: ResultMessage) => void
  onError?: (err: ErrorMessage | string) => void
  onNotify?: (n: NotifyMessage) => void
  onMessage?: (raw: WebSocketBaseMessage) => void
  onStatusChange?: (status: WebSocketStatus) => void
}

// 日志工具
const wsLog = (message: string, ...args: any[]) => {
  if (!WS_DEV) return
  const timestamp = new Date().toISOString().split('T')[1].split('.')[0]
  console.log(`[WS ${timestamp}] ${message}`, ...args)
}

const wsWarn = (message: string, ...args: any[]) => {
  if (!WS_DEV) return
  const timestamp = new Date().toISOString().split('T')[1].split('.')[0]
  console.warn(`[WS ${timestamp}] ${message}`, ...args)
}

const wsError = (message: string, ...args: any[]) => {
  if (!WS_DEV) return
  const timestamp = new Date().toISOString().split('T')[1].split('.')[0]
  console.error(`[WS ${timestamp}] ${message}`, ...args)
}

// 全局存储接口 - 移除销毁相关字段
interface GlobalWSStorage {
  wsRef: WebSocket | null
  status: Ref<WebSocketStatus>
  subscribers: Ref<Map<string, WebSocketSubscriber>>
  heartbeatTimer?: number
  isConnecting: boolean
  lastPingTime: number
  connectionId: string
  moduleLoadCount: number
  createdAt: number
  hasEverConnected: boolean
  reconnectAttempts: number // 新增：重连尝试次数
}

const WS_STORAGE_KEY = Symbol.for('GLOBAL_WEBSOCKET_PERSISTENT')

// 初始化全局存储
const initGlobalStorage = (): GlobalWSStorage => {
  return {
    wsRef: null,
    status: ref<WebSocketStatus>('已断开'),
    subscribers: ref(new Map<string, WebSocketSubscriber>()),
    heartbeatTimer: undefined,
    isConnecting: false,
    lastPingTime: 0,
    connectionId: Math.random().toString(36).substr(2, 9),
    moduleLoadCount: 0,
    createdAt: Date.now(),
    hasEverConnected: false,
    reconnectAttempts: 0
  }
}

// 获取全局存储
const getGlobalStorage = (): GlobalWSStorage => {
  if (!(window as any)[WS_STORAGE_KEY]) {
    wsLog('首次初始化全局 WebSocket 存储 - 永久连接模式')
    ;(window as any)[WS_STORAGE_KEY] = initGlobalStorage()
  }

  const storage = (window as any)[WS_STORAGE_KEY] as GlobalWSStorage
  storage.moduleLoadCount++

  const uptime = ((Date.now() - storage.createdAt) / 1000).toFixed(1)
  wsLog(`模块加载第${storage.moduleLoadCount}次，存储运行时间: ${uptime}s，连接状态: ${storage.status.value}`)

  return storage
}

// 设置全局状态
const setGlobalStatus = (status: WebSocketStatus) => {
  const global = getGlobalStorage()
  const oldStatus = global.status.value
  global.status.value = status
  wsLog(`状态变更: ${oldStatus} -> ${status} [连接ID: ${global.connectionId}]`)

  // 广播状态变化给所有订阅者（兼容 onStatusChange）
  global.subscribers.value.forEach(sub => {
    sub.onStatusChange?.(status)
  })
}

// 停止心跳
const stopGlobalHeartbeat = () => {
  const global = getGlobalStorage()
  if (global.heartbeatTimer) {
    clearInterval(global.heartbeatTimer)
    global.heartbeatTimer = undefined
    wsLog('心跳检测已停止')
  }
}

// 启动心跳
const startGlobalHeartbeat = (ws: WebSocket) => {
  const global = getGlobalStorage()
  stopGlobalHeartbeat()

  wsLog('启动心跳检测，间隔15秒')
  global.heartbeatTimer = window.setInterval(() => {
    wsLog(`心跳检测 - WebSocket状态: ${ws.readyState} (0=CONNECTING, 1=OPEN, 2=CLOSING, 3=CLOSED)`)

    if (ws.readyState === WebSocket.OPEN) {
      try {
        const pingTime = Date.now()
        global.lastPingTime = pingTime
        const pingData = { Ping: pingTime, connectionId: global.connectionId }

        wsLog('发送心跳ping', pingData)
        ws.send(JSON.stringify({
          type: 'Signal',
          data: pingData
        }))

        // 心跳超时检测 - 但不主动断开连接
        setTimeout(() => {
          if (global.lastPingTime === pingTime && ws.readyState === WebSocket.OPEN) {
            wsWarn(`心跳超时 - 发送时间: ${pingTime}, 当前lastPingTime: ${global.lastPingTime}, 连接状态: ${ws.readyState}`)
            wsWarn('心跳超时但保持连接，等待网络层或服务端处理')
          }
        }, HEARTBEAT_TIMEOUT)

      } catch (e) {
        wsError('心跳发送失败', e)
        if (ws.readyState !== WebSocket.OPEN) {
          wsWarn('心跳发送失败，当前连接已不再是 OPEN 状态')
        }
      }
    } else {
      wsWarn(`心跳检测时连接状态异常: ${ws.readyState}，但不主动断开连接`)
    }
  }, HEARTBEAT_INTERVAL)
}

// 处理消息
const handleMessage = (raw: WebSocketBaseMessage) => {
  const global = getGlobalStorage()
  const msgType = String(raw.type)
  const id = raw.id

  // 处理心跳响应
  if (msgType === 'Signal' && raw.data && raw.data.Pong) {
    const pongTime = raw.data.Pong
    const latency = Date.now() - pongTime
    wsLog(`收到心跳pong响应，延迟: ${latency}ms`)
    global.lastPingTime = 0 // 重置ping时间，表示收到了响应
    return
  }

  // 记录其他类型的消息
  if (msgType !== 'Signal') {
    wsLog(`收到消息: type=${msgType}, id=${id || 'broadcast'}`)
  }

  const dispatch = (sub: WebSocketSubscriber) => {
    if (msgType === 'Signal') return

    // 兼容旧版：先调用通用 onMessage 回调
    sub.onMessage?.(raw)

    if (msgType === 'Progress') return sub.onProgress?.(raw.data as ProgressMessage)
    if (msgType === 'Result') return sub.onResult?.(raw.data as ResultMessage)
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
          description: (raw.data as NotifyMessage).content
        })
      }
      return
    }
    // 其他类型可扩展
  }

  if (id) {
    const sub = global.subscribers.value.get(id)
    if (sub) {
      dispatch(sub)
    } else {
      wsWarn(`未找到 ws_id=${id} 的订阅者, type=${msgType}`)
    }
  } else {
    // 无 id 的消息广播给所有订阅者
    global.subscribers.value.forEach((sub: WebSocketSubscriber) => dispatch(sub))
  }
}

// 延迟重连函数
const scheduleReconnect = (global: GlobalWSStorage) => {
  const delay = Math.min(1000 * Math.pow(2, global.reconnectAttempts), 30000) // 最大30秒
  wsLog(`计划在 ${delay}ms 后重连 (第${global.reconnectAttempts + 1}次尝试)`)

  setTimeout(() => {
    global.reconnectAttempts++
    createGlobalWebSocket()
  }, delay)
}

// 创建 WebSocket 连接 - 移除销毁检查，确保永不放弃连接
const createGlobalWebSocket = (): WebSocket => {
  const global = getGlobalStorage()

  // 检查现有连接状态
  if (global.wsRef) {
    wsLog(`检查现有连接状态: ${global.wsRef.readyState}`)

    if (global.wsRef.readyState === WebSocket.OPEN) {
      wsLog('检测到已有活跃连接，直接返回现有连接')
      return global.wsRef
    }

    if (global.wsRef.readyState === WebSocket.CONNECTING) {
      wsLog('检测到正在连接的 WebSocket，返回现有连接实例')
      return global.wsRef
    }

    wsLog('现有连接状态为 CLOSING 或 CLOSED，将创建新连接')
  }

  wsLog(`开始创建新的 WebSocket 连接到: ${BASE_WS_URL}`)
  const ws = new WebSocket(BASE_WS_URL)

  // 记录连接创建
  wsLog(`WebSocket 实例已创建 [连接ID: ${global.connectionId}]`)

  ws.onopen = () => {
    wsLog(`WebSocket 连接已建立 [连接ID: ${global.connectionId}]`)
    global.isConnecting = false
    global.hasEverConnected = true
    global.reconnectAttempts = 0 // 重置重连计数
    setGlobalStatus('已连接')
    startGlobalHeartbeat(ws)

    // 发送连接确认
    try {
      const connectData = { Connect: true, connectionId: global.connectionId }
      wsLog('发送连接确认信号', connectData)
      ws.send(JSON.stringify({
        type: 'Signal',
        data: connectData
      }))
    } catch (e) {
      wsError('发送连接确认失败', e)
    }
  }

  ws.onmessage = (ev) => {
    try {
      const raw = JSON.parse(ev.data) as WebSocketBaseMessage
      handleMessage(raw)
    } catch (e) {
      wsError('解析 WebSocket 消息失败', e, '原始数据:', ev.data)
    }
  }

  ws.onerror = (event) => {
    wsError(`WebSocket 连接错误 [连接ID: ${global.connectionId}]`, event)
    wsError(`错误发生时连接状态: ${ws.readyState}`)
    setGlobalStatus('连接错误')
  }

  ws.onclose = (event) => {
    wsLog(`WebSocket 连接已关闭 [连接ID: ${global.connectionId}]`)
    wsLog(`关闭码: ${event.code}, 关闭原因: "${event.reason}", 是否干净关闭: ${event.wasClean}`)

    // 详细分析关闭原因
    const closeReasons: { [key: number]: string } = {
      1000: '正常关闭',
      1001: '终端离开（如页面关闭）',
      1002: '协议错误',
      1003: '不支持的数据类型',
      1005: '未收到状态码',
      1006: '连接异常关闭',
      1007: '数据格式错误',
      1008: '策略违规',
      1009: '消息过大',
      1010: '扩展协商失败',
      1011: '服务器意外错误',
      1015: 'TLS握手失败'
    }

    const reasonDesc = closeReasons[event.code] || '未知原因'
    wsLog(`关闭详情: ${reasonDesc}`)

    setGlobalStatus('已断开')
    stopGlobalHeartbeat()
    global.isConnecting = false

    // 永不放弃：立即安排重连
    wsLog('连接断开，安排自动重连以保持永久连接')
    scheduleReconnect(global)
  }

  // 为新创建的 WebSocket 设置引用
  global.wsRef = ws
  wsLog(`WebSocket 引用已设置到全局存储`)

  return ws
}

// 连接全局 WebSocket - 简化逻辑，移除销毁检查
const connectGlobalWebSocket = async (): Promise<boolean> => {
  const global = getGlobalStorage()

  // 详细检查连接状态
  if (global.wsRef) {
    wsLog(`检查现有连接: readyState=${global.wsRef.readyState}, isConnecting=${global.isConnecting}`)

    if (global.wsRef.readyState === WebSocket.OPEN) {
      wsLog('WebSocket 已连接，直接返回')
      return true
    }

    if (global.wsRef.readyState === WebSocket.CONNECTING) {
      wsLog('WebSocket 正在连接中')
      return true
    }
  }

  if (global.isConnecting) {
    wsLog('全局连接标志显示正在连接中，等待连接完成')
    return true
  }

  try {
    wsLog('开始建立 WebSocket 连接流程')
    global.isConnecting = true
    global.wsRef = createGlobalWebSocket()
    setGlobalStatus('连接中')
    wsLog('WebSocket 连接流程已启动')
    return true
  } catch (e) {
    wsError('创建 WebSocket 失败', e)
    setGlobalStatus('连接错误')
    global.isConnecting = false

    // 即使创建失败也要安排重连
    scheduleReconnect(global)
    return false
  }
}

// 模块初始化逻辑
wsLog('=== WebSocket 模块开始初始化 - 永久连接模式 ===')
const global = getGlobalStorage()

if (global.moduleLoadCount > 1) {
  wsLog(`检测到模块热更新重载 (第${global.moduleLoadCount}次)`)
  wsLog(`当前连接状态: ${global.wsRef ? global.wsRef.readyState : 'null'}`)
  wsLog('保持现有连接，不重新建立连接')
} else {
  wsLog('首次加载模块，建立永久 WebSocket 连接')
  connectGlobalWebSocket()
}

// 页面卸载时不关闭连接，保持永久连接
window.addEventListener('beforeunload', () => {
  wsLog('页面即将卸载，但保持 WebSocket 连接')
})

// 主要 Hook 函数
export function useWebSocket() {
  const global = getGlobalStorage()

  const subscribe = (id: string, handlers: Omit<WebSocketSubscriber, 'id'>) => {
    global.subscribers.value.set(id, { id, ...handlers })
    wsLog(`添加订阅者: ${id}，当前订阅者总数: ${global.subscribers.value.size}`)
  }

  const unsubscribe = (id: string) => {
    const existed = global.subscribers.value.delete(id)
    wsLog(`移除订阅者: ${id}，是否存在: ${existed}，剩余订阅者: ${global.subscribers.value.size}`)
  }

  const sendRaw = (type: string, data?: any, id?: string) => {
    const ws = global.wsRef
    wsLog(`尝试发送消息: type=${type}, id=${id || 'broadcast'}`)

    if (ws && ws.readyState === WebSocket.OPEN) {
      try {
        const messageData = { id, type, data }
        ws.send(JSON.stringify(messageData))
        wsLog('消息发送成功')
      } catch (e) {
        wsError('发送消息失败', e)
      }
    } else {
      wsWarn(`WebSocket 未准备就绪: ${ws ? `状态=${ws.readyState}` : '连接为null'}`)
      wsWarn('消息将在连接恢复后可用')
    }
  }

  const startTaskRaw = (params: any) => {
    wsLog('发送启动任务请求', params)
    sendRaw('StartTask', params)
  }

  // 移除 destroy 功能，确保连接永不断开
  const forceReconnect = () => {
    wsLog('手动触发重连')
    if (global.wsRef) {
      // 不关闭现有连接，直接尝试创建新连接
      global.isConnecting = false
      connectGlobalWebSocket()
    }
    return true
  }

  const getConnectionInfo = () => {
    const info = {
      connectionId: global.connectionId,
      status: global.status.value,
      subscriberCount: global.subscribers.value.size,
      moduleLoadCount: global.moduleLoadCount,
      wsReadyState: global.wsRef ? global.wsRef.readyState : null,
      isConnecting: global.isConnecting,
      hasHeartbeat: !!global.heartbeatTimer,
      hasEverConnected: global.hasEverConnected,
      reconnectAttempts: global.reconnectAttempts,
      wsDevEnabled: WS_DEV,
      isPersistentMode: true // 标识为永久连接模式
    }
    wsLog('连接信息查询', info)
    return info
  }

  // 兼容旧版 API：connect 重载
  async function connect(): Promise<boolean>
  async function connect(config: WebSocketConfig): Promise<string | null>
  async function connect(config?: WebSocketConfig): Promise<boolean | string | null> {
    if (!config) {
      // 无参数调用：返回连接状态
      return connectGlobalWebSocket()
    }

    // 有参数调用：建立订阅，复用现有连接
    const ok = await connectGlobalWebSocket()
    if (!ok) {
      // 即使连接失败也要建立订阅，等待连接恢复
      wsLog('连接暂时不可用，但仍建立订阅等待连接恢复')
    }

    // 先移除旧订阅避免重复
    if (global.subscribers.value.has(config.taskId)) {
      unsubscribe(config.taskId)
    }

    subscribe(config.taskId, {
      onProgress: config.onProgress,
      onResult: config.onResult,
      onError: (e) => {
        if (typeof config.onError === 'function') config.onError(e)
      },
      onNotify: (n) => {
        config.onNotify?.(n)
        if (config.showNotifications && n?.title) {
          notification.info({ message: n.title, description: n.content })
        }
      },
      onMessage: config.onMessage,
      onStatusChange: config.onStatusChange
    })

    // 立即推送当前状态
    config.onStatusChange?.(global.status.value)

    // 可根据 mode 发送一个初始信号（可选）
    if (config.mode) {
      sendRaw('Mode', { mode: config.mode }, config.taskId)
    }

    return config.taskId
  }

  // 兼容旧版 API：disconnect / disconnectAll - 只取消订阅，不断开连接
  const disconnect = (taskId: string) => {
    if (!taskId) return
    unsubscribe(taskId)
    wsLog(`兼容模式取消订阅: ${taskId}`)
  }

  const disconnectAll = () => {
    const ids = Array.from(global.subscribers.value.keys())
    ids.forEach((id: string) => unsubscribe(id))
    wsLog('已取消所有订阅 (disconnectAll)')
  }

  return {
    // 兼容 API
    connect,
    disconnect,
    disconnectAll,
    // 原有 API & 工具
    subscribe,
    unsubscribe,
    sendRaw,
    startTaskRaw,
    forceReconnect,
    getConnectionInfo,
    status: global.status,
    subscribers: global.subscribers
  }
}
