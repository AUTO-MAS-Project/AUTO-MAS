// WebSocket 连接层
// 职责：地址协商、建立/关闭唯一连接、有限退避重连、消息解析与发送、
// 按 id + type 分发、请求响应关联、断开事件通知生命周期协调器。
// 不持有业务处理逻辑，不管理后端进程。

import { ref, type Ref } from 'vue'
import { OpenAPI } from '@/api'
import { fetchAuthenticatedWebSocketHandshake } from '@/utils/websocketAuth'
import { dispatchMessage, subscribe, unsubscribe } from './subscriptions'
import { WS_ID_MAIN, WS_SNAPSHOT_RESPONSE } from './types'
import type { WSConnectionState, WSDisconnectEvent, WSEnvelope } from './types'

const logger = window.electronAPI.getLogger('WebSocket连接')

// ==================== 配置 ====================

const DEFAULT_WS_PATH = '/api/core/ws'
const CONNECTION_REPLACED_CLOSE_CODE = 4001
const CONNECTION_REPLACED_CLOSE_REASON = 'connection replaced'
const MESSAGE_TOO_BIG_CLOSE_CODE = 1009

// 重连退避：3s × 1.5ⁿ，封顶 30s；每轮最多 5 次，一轮失败后交由生命周期协调器决策
const RECONNECT_DELAY = 3000
const RECONNECT_DELAY_MAX = 30000
const RECONNECT_BACKOFF = 1.5
const RECONNECT_CYCLE_ATTEMPTS = 5

// ==================== 状态 ====================

const state: Ref<WSConnectionState> = ref('idle')

let socket: WebSocket | null = null
let connectPromise: Promise<boolean> | null = null
let reconnectTimer: number | undefined
let reconnectAttempts = 0
// 连接代次：每次 shutdown 递增，使协商期间在途的连接尝试恢复后失效，
// 避免旧协程创建的连接把已终止的连接层复活
let connectGeneration = 0
let backendDevMode = import.meta.env.DEV === true || window.location.hostname === 'localhost'
let websocketUrl = 'ws://127.0.0.1:36163/api/core/ws'
let websocketAuthProtocol = ''

type DisconnectListener = (event: WSDisconnectEvent) => void
type CycleFailureListener = () => void
const disconnectListeners: DisconnectListener[] = []
const cycleFailureListeners: CycleFailureListener[] = []

// ==================== 地址协商 ====================

const normalizeWsPath = (value?: string): string => {
  if (!value) return DEFAULT_WS_PATH
  return value.startsWith('/') ? value : `/${value}`
}

const toWebSocketBase = (value: string): string => {
  if (value.startsWith('ws://') || value.startsWith('wss://')) {
    return value.replace(/\/+$/, '')
  }
  if (value.startsWith('https://')) {
    return `wss://${value.slice('https://'.length)}`.replace(/\/+$/, '')
  }
  if (value.startsWith('http://')) {
    return `ws://${value.slice('http://'.length)}`.replace(/\/+$/, '')
  }
  return `ws://${value}`.replace(/\/+$/, '')
}

/** 协商主 WebSocket 地址、开发模式和进程级认证协议。 */
const negotiateWebSocketUrl = async (): Promise<string> => {
  let httpBase = OpenAPI.BASE || 'http://127.0.0.1:36163'
  let websocketBase = toWebSocketBase(httpBase)
  let wsPath = DEFAULT_WS_PATH

  if (window.electronAPI?.getApiEndpoint) {
    try {
      httpBase = await window.electronAPI.getApiEndpoint('local')
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.warn(`获取 HTTP 端点失败，继续使用当前 OpenAPI.BASE: ${errorMsg}`)
    }

    try {
      const endpoint = await window.electronAPI.getApiEndpoint('websocket')
      websocketBase = toWebSocketBase(endpoint)
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.warn(`获取 WebSocket 基础端点失败，将从 HTTP 端点推导: ${errorMsg}`)
      websocketBase = toWebSocketBase(httpBase)
    }
  }

  // 主连接从不降级为未认证连接。Electron 通过 preload 获取进程令牌，
  // 浏览器开发模式只允许从可信 loopback 元数据端点获取。
  const handshake = await fetchAuthenticatedWebSocketHandshake(httpBase)
  backendDevMode = handshake.devMode
  websocketAuthProtocol = handshake.authProtocol
  if (handshake.wsPath) {
    wsPath = normalizeWsPath(handshake.wsPath)
  }

  OpenAPI.BASE = httpBase
  websocketUrl = `${websocketBase}${wsPath}`
  logger.info(`已协商 WebSocket 链接: ${websocketUrl}, devMode=${backendDevMode}`)
  return websocketUrl
}

// ==================== 连接管理 ====================

const clearReconnectTimer = (): void => {
  if (reconnectTimer !== undefined) {
    window.clearTimeout(reconnectTimer)
    reconnectTimer = undefined
  }
}

export const isConnectionReplacedClose = (event: WSDisconnectEvent): boolean =>
  event.code === CONNECTION_REPLACED_CLOSE_CODE && event.reason === CONNECTION_REPLACED_CLOSE_REASON

export const isMessageTooBigClose = (event: WSDisconnectEvent): boolean =>
  event.code === MESSAGE_TOO_BIG_CLOSE_CODE

// 终止性关闭仅两种：连接被替换（4001）与消息超限（1009）。
// 这两种关闭停止**自动**重连（进入 suspended 挂起态）以避免连接风暴，
// 但不是不可恢复终态：用户显式发起的恢复仍可 connect({ force: true })。
// 后端在关闭准备期 / 重启期会以 1012 (service closing) 拒绝主连接
// （app/core/ws/manager.py、app/api/websocket.py），该场景后端随后会恢复，
// 因此 1012 走普通退避重连等待后端回来，属预期行为。
export const shouldReconnectAfterClose = (event: WSDisconnectEvent): boolean =>
  !isConnectionReplacedClose(event) && !isMessageTooBigClose(event)

// ==================== 状态快照 ====================

// 最近一次快照的 revision（诊断用）；后端重启后会从 0 重新计数
let snapshotRevision: number | null = null

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

/**
 * 消费后端状态快照（id=Main, type=snapshot.response）。
 * 后端在每次主连接建立后通过 on_connect hook 主动推送
 * （app/core/ws/bootstrap.py），data.states 为 type -> id -> data 的
 * 可合并状态集合。此处将每条状态按原始 id/type 重新分发，使现有
 * 订阅者在断线重连后自然恢复最新状态，无需各页面单独处理。
 */
const applySnapshot = (message: WSEnvelope): void => {
  const { revision, states } = message.data as { revision?: unknown; states?: unknown }
  if (!isRecord(states)) {
    logger.warn(
      `快照消息 states 形状异常，已忽略: ${Array.isArray(states) ? 'array' : typeof states}`
    )
    return
  }

  let dispatched = 0
  let dropped = 0
  for (const [type, statesById] of Object.entries(states)) {
    if (!isRecord(statesById)) {
      logger.warn(`快照条目形状异常，已跳过: type=${type}`)
      continue
    }
    for (const [id, data] of Object.entries(statesById)) {
      if (!isRecord(data)) {
        logger.warn(`快照状态数据形状异常，已跳过: id=${id}, type=${type}`)
        continue
      }
      if (dispatchMessage({ id, type, data })) {
        dispatched++
      } else {
        dropped++
      }
    }
  }

  if (typeof revision === 'number') {
    snapshotRevision = revision
  }
  logger.info(
    `已应用状态快照: revision=${typeof revision === 'number' ? revision : '未知'}, ` +
      `重分发 ${dispatched} 条, 无订阅者 ${dropped} 条`
  )
}

const handleMessage = (raw: string): void => {
  let message: WSEnvelope
  try {
    const parsed = JSON.parse(raw) as Partial<WSEnvelope>
    if (typeof parsed?.id !== 'string' || typeof parsed?.type !== 'string') {
      logger.warn(`入站消息缺少 id/type，已丢弃: ${raw.slice(0, 200)}`)
      return
    }
    message = { id: parsed.id, type: parsed.type, data: parsed.data ?? {} }
  } catch (e) {
    const errorMsg = e instanceof Error ? e.message : String(e)
    logger.warn(`解析 WebSocket 消息失败: ${errorMsg}`)
    return
  }

  if (message.id === WS_ID_MAIN && message.type === WS_SNAPSHOT_RESPONSE) {
    // 快照信封本身也分发一次（供请求-响应关联或诊断订阅者观察），
    // 无订阅者不告警；随后展开 states 逐条重分发
    dispatchMessage(message)
    applySnapshot(message)
    return
  }

  // 找不到订阅者的消息直接丢弃
  if (!dispatchMessage(message)) {
    logger.debug(`无订阅者，丢弃消息: id=${message.id}, type=${message.type}`)
  }
}

const handleClosed = (event: WSDisconnectEvent): void => {
  if (state.value === 'closed') return

  if (!shouldReconnectAfterClose(event)) {
    clearReconnectTimer()
    reconnectAttempts = 0
    // 终止性关闭只挂起自动重连，不是不可恢复终态：用户显式发起的恢复
    // （manualReconnect / 重启后端 / 启动重试）仍可 connect({ force: true })。
    // 只有 shutdown() 才会进入不可恢复的 'closed'。
    state.value = 'suspended'
    if (isConnectionReplacedClose(event)) {
      logger.info('主 WebSocket 已被同进程的新连接替换，旧连接停止重连')
    } else {
      logger.error('主 WebSocket 消息超过协议上限，停止自动重连以避免连接风暴')
      for (const listener of [...disconnectListeners]) {
        try {
          listener(event)
        } catch (e) {
          const errorMsg = e instanceof Error ? e.message : String(e)
          logger.warn(`断开事件监听器错误: ${errorMsg}`)
        }
      }
    }
    return
  }

  state.value = 'reconnecting'

  for (const listener of [...disconnectListeners]) {
    try {
      listener(event)
    } catch (e) {
      const errorMsg = e instanceof Error ? e.message : String(e)
      logger.warn(`断开事件监听器错误: ${errorMsg}`)
    }
  }

  // 断开事件可能触发生命周期协调器进入关闭流程（state 变为 closed）
  if ((state.value as WSConnectionState) !== 'closed') {
    scheduleNextAttempt()
  }
}

const scheduleNextAttempt = (): void => {
  clearReconnectTimer()

  if (reconnectAttempts >= RECONNECT_CYCLE_ATTEMPTS) {
    // 一轮重连失败：清零计数并交由生命周期协调器决策（重启后端 / 延迟下一轮）
    reconnectAttempts = 0
    logger.warn('本轮 WebSocket 重连失败，交由生命周期协调器处理')
    for (const listener of [...cycleFailureListeners]) {
      try {
        listener()
      } catch (e) {
        const errorMsg = e instanceof Error ? e.message : String(e)
        logger.warn(`重连失败监听器错误: ${errorMsg}`)
      }
    }
    return
  }

  reconnectAttempts++
  const delay = Math.min(
    RECONNECT_DELAY * Math.pow(RECONNECT_BACKOFF, reconnectAttempts - 1),
    RECONNECT_DELAY_MAX
  )
  logger.info(`第 ${reconnectAttempts} 次重连尝试，延迟 ${delay}ms`)
  reconnectTimer = window.setTimeout(() => {
    void connect()
  }, delay)
}

export interface ConnectOptions {
  /**
   * 用户显式发起的连接（手动重连 / 重启后端 / 启动重试）。
   * 可越过 `suspended` 挂起守卫重新建连；但**无法**越过 shutdown() 的
   * 不可恢复终态 `closed`。自动重连路径（退避定时器 / scheduleReconnect）
   * 绝不传 force，以保证 1009、4001 后不会出现连接风暴。
   */
  force?: boolean
}

/**
 * 建立唯一主 WebSocket 连接。
 * 同时最多存在一个连接尝试；已连接时直接返回成功。
 *
 * @param options force=true 表示用户显式发起，可从 suspended 挂起态恢复
 * @returns 连接是否成功建立（open 事件触发）
 */
export async function connect(options?: ConnectOptions): Promise<boolean> {
  if (state.value === 'closed') {
    logger.warn('连接层已关闭，拒绝新的连接请求')
    return false
  }
  if (state.value === 'suspended' && options?.force !== true) {
    logger.warn('连接层已挂起（协议级终止性关闭），仅接受用户显式发起的重连')
    return false
  }
  if (socket && socket.readyState === WebSocket.OPEN) {
    return true
  }
  if (connectPromise) {
    return connectPromise
  }

  clearReconnectTimer()
  if (state.value !== 'reconnecting') {
    state.value = 'connecting'
  }

  const myGeneration = connectGeneration
  connectPromise = (async (): Promise<boolean> => {
    try {
      await negotiateWebSocketUrl()

      // 协商期间可能已 shutdown（代次递增并置 closed）：放弃本次尝试，
      // 不创建新连接，避免复活已终止的连接层
      if (myGeneration !== connectGeneration || state.value === 'closed') {
        logger.info('连接协商完成时连接层已关闭，放弃本次尝试')
        connectPromise = null
        return false
      }

      return await new Promise<boolean>(resolve => {
        let settled = false
        logger.info(`创建 WebSocket 连接: ${websocketUrl}`)
        const ws = new WebSocket(websocketUrl, websocketAuthProtocol)
        socket = ws

        ws.onopen = () => {
          // 代次失效（onopen 前发生了 shutdown）：关闭这个刚建立的连接，不复活状态
          if (myGeneration !== connectGeneration) {
            try {
              ws.close(1000, '连接层已关闭')
            } catch {
              // 忽略
            }
            return
          }
          if (socket !== ws) return
          logger.info('WebSocket 连接已建立')
          state.value = 'open'
          reconnectAttempts = 0
          if (!settled) {
            settled = true
            connectPromise = null
            resolve(true)
          }
        }

        ws.onmessage = event => {
          if (socket !== ws) return
          handleMessage(String(event.data))
        }

        ws.onerror = () => {
          if (socket !== ws) return
          logger.warn('WebSocket 连接发生错误')
        }

        ws.onclose = event => {
          // 无论是否已被 shutdown 置换，都要 settle 本次连接尝试，
          // 避免等待方（connectWithRetry/重启流程）永久挂起
          if (!settled) {
            settled = true
            connectPromise = null
            resolve(false)
          }
          if (socket !== ws) return
          socket = null
          logger.info(`WebSocket 连接关闭: code=${event.code}, reason="${event.reason}"`)
          handleClosed({ code: event.code, reason: event.reason })
        }
      })
    } catch (error) {
      // 协商或构造异常：清空单飞行状态并按失败尝试进入重连，避免连接层永久卡死
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.warn(`建立 WebSocket 连接异常: ${errorMsg}`)
      connectPromise = null
      if ((state.value as WSConnectionState) !== 'closed') {
        state.value = 'reconnecting'
        scheduleNextAttempt()
      }
      return false
    }
  })()

  return connectPromise
}

/**
 * 由生命周期协调器安排下一轮重连（例如后端进程仍在运行、等待其恢复时）。
 *
 * @param delayMs 延迟毫秒数，默认使用最大退避间隔
 */
export function scheduleReconnect(delayMs: number = RECONNECT_DELAY_MAX): void {
  // closed 为不可恢复终态；suspended 只禁止自动重连，用户显式恢复走 connect({ force: true })
  if (state.value === 'closed' || state.value === 'suspended') return
  clearReconnectTimer()
  state.value = 'reconnecting'
  reconnectTimer = window.setTimeout(() => {
    void connect()
  }, delayMs)
}

/** 停止自动重连（保持当前连接不变） */
export function stopReconnect(): void {
  clearReconnectTimer()
  reconnectAttempts = 0
}

/**
 * 关闭连接层（终态）。用于应用退出流程：停止重连并关闭连接，
 * 此后 connect 请求将被拒绝。
 */
export function shutdown(reason: string = '应用关闭'): void {
  state.value = 'closed'
  // 递增代次使协商中的在途连接尝试恢复后自行失效
  connectGeneration++
  clearReconnectTimer()
  reconnectAttempts = 0
  connectPromise = null
  const ws = socket
  socket = null
  if (ws && ws.readyState !== WebSocket.CLOSED) {
    try {
      ws.close(1000, reason)
    } catch {
      // 连接可能已在关闭中
    }
  }
}

// ==================== 发送与请求响应 ====================

/**
 * 发送统一信封消息。
 *
 * @returns 是否发送成功；未连接时返回 false
 */
export function send(id: string, type: string, data?: Record<string, unknown>): boolean {
  const ws = socket
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    logger.warn(`WebSocket 未连接，无法发送消息: id=${id}, type=${type}`)
    return false
  }
  try {
    ws.send(JSON.stringify({ id, type, data: data ?? {} }))
    return true
  } catch (e) {
    const errorMsg = e instanceof Error ? e.message : String(e)
    logger.warn(`发送消息失败: ${errorMsg}`)
    return false
  }
}

let requestCounter = 0

/**
 * 请求-响应关联：发送带 requestId 的请求消息，等待相同 id 下匹配
 * requestId 的响应消息（responseTypes 中任意一种）。
 *
 * @param id 路由 ID
 * @param requestType 请求消息类别
 * @param responseTypes 视为响应的消息类别列表（如正常响应与错误响应）
 * @param data 请求数据（requestId 字段自动填充）
 * @param timeoutMs 超时毫秒数
 */
export function request(
  id: string,
  requestType: string,
  responseTypes: string[],
  data?: Record<string, unknown>,
  timeoutMs: number = 10000
): Promise<WSEnvelope> {
  const requestId = `req_${Date.now()}_${++requestCounter}`

  return new Promise<WSEnvelope>((resolve, reject) => {
    const subscriptionIds: string[] = []
    const timer = window.setTimeout(() => {
      cleanup()
      reject(new Error(`请求超时: ${id}/${requestType}`))
    }, timeoutMs)

    const cleanup = (): void => {
      window.clearTimeout(timer)
      for (const subscriptionId of subscriptionIds) {
        unsubscribe(subscriptionId)
      }
    }

    for (const responseType of responseTypes) {
      subscriptionIds.push(
        subscribe({ id, type: responseType }, message => {
          const responseId = (message.data as { requestId?: string }).requestId
          if (responseId !== requestId) return
          cleanup()
          resolve(message)
        })
      )
    }

    if (!send(id, requestType, { ...(data ?? {}), requestId })) {
      cleanup()
      reject(new Error(`请求发送失败: ${id}/${requestType}`))
    }
  })
}

// ==================== 状态与事件 ====================

/** 连接状态（响应式） */
export function connectionState(): Ref<WSConnectionState> {
  return state
}

/** 后端是否处于开发模式（经 ws_meta 协商） */
export function isBackendDevMode(): boolean {
  return backendDevMode
}

/** 注册断开事件监听（生命周期协调器使用） */
export function onDisconnected(listener: DisconnectListener): () => void {
  disconnectListeners.push(listener)
  return () => {
    const index = disconnectListeners.indexOf(listener)
    if (index >= 0) disconnectListeners.splice(index, 1)
  }
}

/** 注册一轮重连失败监听（生命周期协调器决定重启后端或延迟下一轮） */
export function onReconnectCycleFailed(listener: CycleFailureListener): () => void {
  cycleFailureListeners.push(listener)
  return () => {
    const index = cycleFailureListeners.indexOf(listener)
    if (index >= 0) cycleFailureListeners.splice(index, 1)
  }
}

/** 连接诊断信息 */
export function connectionInfo(): Record<string, unknown> {
  return {
    state: state.value,
    url: websocketUrl,
    readyState: socket?.readyState ?? null,
    reconnectAttempts,
    hasReconnectTimer: reconnectTimer !== undefined,
    backendDevMode,
    snapshotRevision,
  }
}
