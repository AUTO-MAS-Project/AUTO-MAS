// WebSocket 连接层
// 职责：地址协商、建立/关闭唯一连接、有限退避重连、消息解析与发送、
// 按 id + type 分发、请求响应关联、断开事件通知生命周期协调器。
// 不持有业务处理逻辑，不管理后端进程。

import { translate as t } from '@/i18n'
import { ref, type Ref } from 'vue'
import { OpenAPI } from '@/api'
import { dispatchMessage, subscribe, unsubscribe } from './subscriptions'
import { getDefaultHttpEndpoint, getDefaultWebSocketEndpoint } from '@/utils/backendEndpoint'
import type {
  WSConnectionState,
  WSDataForType,
  WSDisconnectEvent,
  WSEnvelope,
  WSJsonObject,
} from './types'

const logger = window.electronAPI.getLogger('WebSocket连接')

// ==================== 配置 ====================

const DEFAULT_WS_PATH = '/api/core/ws'
const WS_META_URL = '/api/core/ws_meta'
const WS_META_TIMEOUT = 3000

// 重连退避：3s × 1.5ⁿ，封顶 30s；每轮最多 5 次，一轮失败后交由生命周期协调器决策
const RECONNECT_DELAY = 3000
const RECONNECT_DELAY_MAX = 30000
const RECONNECT_BACKOFF = 1.5
const RECONNECT_CYCLE_ATTEMPTS = 5

// ==================== 状态 ====================

const state: Ref<WSConnectionState> = ref('idle')

let socket: WebSocket | null = null
let connectPromise: Promise<boolean> | null = null
let connectAttemptToken: symbol | null = null
let reconnectTimer: number | undefined
let reconnectAttempts = 0
let automaticReconnectEnabled = true
// 连接代次：每次 shutdown 递增，使协商期间在途的连接尝试恢复后失效，
// 避免旧异步尝试创建的连接把已终止或已被立即重连替换的连接层复活
let connectGeneration = 0
let backendDevMode = import.meta.env.DEV === true || window.location.hostname === 'localhost'
let websocketUrl = `${getDefaultWebSocketEndpoint()}${DEFAULT_WS_PATH}`

type DisconnectListener = (event: WSDisconnectEvent) => void
type CycleFailureListener = () => void
type ConnectedListener = () => void | Promise<void>
const disconnectListeners: DisconnectListener[] = []
const cycleFailureListeners: CycleFailureListener[] = []
const connectedListeners: ConnectedListener[] = []

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

const fetchWithTimeout = async (
  input: RequestInfo | URL,
  init: RequestInit,
  timeoutMs: number
): Promise<Response> => {
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), timeoutMs)
  try {
    return await fetch(input, { ...init, signal: controller.signal })
  } finally {
    window.clearTimeout(timer)
  }
}

/** 协商主 WebSocket 地址与后端开发模式，失败时回退本地默认配置 */
const negotiateWebSocketUrl = async (): Promise<string> => {
  let httpBase = OpenAPI.BASE || getDefaultHttpEndpoint()
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

  try {
    const response = await fetchWithTimeout(
      `${httpBase.replace(/\/+$/, '')}${WS_META_URL}`,
      { method: 'GET', headers: { Accept: 'application/json' }, cache: 'no-store' },
      WS_META_TIMEOUT
    )
    if (response.ok) {
      const meta = (await response.json()) as { devMode?: boolean; wsPath?: string }
      if (typeof meta.devMode === 'boolean') {
        backendDevMode = meta.devMode
      }
      if (typeof meta.wsPath === 'string' && meta.wsPath.trim()) {
        wsPath = normalizeWsPath(meta.wsPath.trim())
      }
    } else {
      logger.warn(`协商 WebSocket 元信息失败，HTTP 状态: ${response.status}`)
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.warn(`协商 WebSocket 元信息失败，继续使用本地回退配置: ${errorMsg}`)
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

const handleMessage = (raw: string): void => {
  let message: WSEnvelope<WSJsonObject>
  try {
    const parsed: unknown = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      logger.warn(`入站消息不是 JSON 对象，已丢弃: ${raw.slice(0, 200)}`)
      return
    }
    const envelope = parsed as Partial<WSEnvelope<unknown>>
    if (
      typeof envelope.id !== 'string' ||
      !envelope.id.trim() ||
      typeof envelope.type !== 'string' ||
      !envelope.type.trim()
    ) {
      logger.warn(`入站消息缺少 id/type，已丢弃: ${raw.slice(0, 200)}`)
      return
    }
    const data = envelope.data ?? {}
    if (!data || typeof data !== 'object' || Array.isArray(data)) {
      logger.warn(`入站消息 data 不是 JSON 对象，已丢弃: ${raw.slice(0, 200)}`)
      return
    }
    message = {
      id: envelope.id.trim(),
      type: envelope.type.trim(),
      data: data as WSJsonObject,
    }
  } catch (e) {
    const errorMsg = e instanceof Error ? e.message : String(e)
    logger.warn(`解析 WebSocket 消息失败: ${errorMsg}`)
    return
  }

  // 找不到订阅者的消息直接丢弃
  if (!dispatchMessage(message)) {
    logger.debug(`无订阅者，丢弃消息: id=${message.id}, type=${message.type}`)
  }
}

const handleClosed = (event: WSDisconnectEvent): void => {
  if (state.value === 'closed') return
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
  if (
    (state.value as WSConnectionState) !== 'closed' &&
    automaticReconnectEnabled &&
    !connectPromise
  ) {
    scheduleNextAttempt()
  }
}

const scheduleNextAttempt = (): void => {
  clearReconnectTimer()
  if (state.value === 'closed' || !automaticReconnectEnabled) return

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
    reconnectTimer = undefined
    if (!automaticReconnectEnabled || state.value === 'closed') return
    void connect()
  }, delay)
}

const notifyConnected = (): void => {
  for (const listener of [...connectedListeners]) {
    try {
      void Promise.resolve(listener()).catch(error => {
        const errorMsg = error instanceof Error ? error.message : String(error)
        logger.warn(`连接成功监听器错误: ${errorMsg}`)
      })
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.warn(`连接成功监听器错误: ${errorMsg}`)
    }
  }
}

/**
 * 建立唯一主 WebSocket 连接。
 * 同时最多存在一个连接尝试；已连接时直接返回成功。
 *
 * @returns 连接是否成功建立（open 事件触发）
 */
export async function connect(): Promise<boolean> {
  if (state.value === 'closed') {
    logger.warn('连接层已关闭，拒绝新的连接请求')
    return false
  }
  if (socket && socket.readyState === WebSocket.OPEN) {
    return true
  }
  if (connectPromise) {
    return connectPromise
  }

  automaticReconnectEnabled = true
  clearReconnectTimer()
  if (state.value !== 'reconnecting') {
    state.value = 'connecting'
  }

  const myGeneration = connectGeneration
  const attemptToken = Symbol('ws-connect-attempt')
  connectAttemptToken = attemptToken
  const clearOwnedAttempt = (): void => {
    if (connectAttemptToken !== attemptToken) return
    connectAttemptToken = null
    connectPromise = null
    // onclose 会在本次单飞行 Promise 尚未清理时进入 handleClosed，
    // 因此把失败后的续排兜底放在所有权释放之后；已有计时器时不重复安排。
    if (
      state.value === 'reconnecting' &&
      automaticReconnectEnabled &&
      socket === null &&
      reconnectTimer === undefined &&
      myGeneration === connectGeneration
    ) {
      scheduleNextAttempt()
    }
  }

  const attemptPromise = (async (): Promise<boolean> => {
    try {
      await negotiateWebSocketUrl()

      // 协商期间可能已 shutdown（代次递增并置 closed）：放弃本次尝试，
      // 不创建新连接，避免复活已终止的连接层
      if (myGeneration !== connectGeneration || state.value === 'closed') {
        logger.info('连接协商完成时连接层已关闭，放弃本次尝试')
        return false
      }

      return await new Promise<boolean>(resolve => {
        let settled = false
        const settle = (connected: boolean): void => {
          if (settled) return
          settled = true
          resolve(connected)
        }
        logger.info(`创建 WebSocket 连接: ${websocketUrl}`)
        const ws = new WebSocket(websocketUrl)
        socket = ws

        ws.onopen = () => {
          // 代次失效（onopen 前发生了 shutdown/reconnectNow）：
          // 关闭这个刚建立的连接，不复活状态。
          if (myGeneration !== connectGeneration || state.value === 'closed' || socket !== ws) {
            try {
              ws.close(1000, '连接层已关闭')
            } catch {
              // 忽略
            }
            settle(false)
            return
          }
          logger.info('WebSocket 连接已建立')
          state.value = 'open'
          reconnectAttempts = 0
          settle(true)
          notifyConnected()
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
          settle(false)
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
      if (
        (state.value as WSConnectionState) !== 'closed' &&
        automaticReconnectEnabled &&
        myGeneration === connectGeneration
      ) {
        state.value = 'reconnecting'
        scheduleNextAttempt()
      }
      return false
    }
  })().finally(clearOwnedAttempt)
  connectPromise = attemptPromise

  return attemptPromise
}

/**
 * 由生命周期协调器安排下一轮重连（例如后端进程仍在运行、等待其恢复时）。
 *
 * @param delayMs 延迟毫秒数，默认使用最大退避间隔
 */
export function scheduleReconnect(delayMs: number = RECONNECT_DELAY_MAX): void {
  if (state.value === 'closed') return
  automaticReconnectEnabled = true
  clearReconnectTimer()
  state.value = 'reconnecting'
  reconnectTimer = window.setTimeout(() => {
    reconnectTimer = undefined
    if (!automaticReconnectEnabled || state.value === 'closed') return
    void connect()
  }, delayMs)
}

/** 停止自动重连（保持当前连接不变） */
export function stopReconnect(): void {
  automaticReconnectEnabled = false
  clearReconnectTimer()
  reconnectAttempts = 0
}

/**
 * 立即替换当前连接并建立一个新连接。
 * 用于系统恢复或后端重启完成后的显式恢复；旧连接/旧协商代次不能覆盖新连接状态。
 */
export async function reconnectNow(reason: string = '立即重连'): Promise<boolean> {
  if (state.value === 'closed') return false

  automaticReconnectEnabled = true
  connectGeneration++
  clearReconnectTimer()
  reconnectAttempts = 0
  connectPromise = null
  connectAttemptToken = null
  state.value = 'reconnecting'

  const previousSocket = socket
  socket = null
  if (previousSocket && previousSocket.readyState !== WebSocket.CLOSED) {
    try {
      previousSocket.close(1000, reason.slice(0, 120))
    } catch {
      // 旧连接可能已在关闭中；新连接仍可继续建立。
    }
  }

  return connect()
}

/**
 * 关闭连接层（终态）。用于应用退出流程：停止重连并关闭连接，
 * 此后 connect 请求将被拒绝。
 */
export function shutdown(reason: string = '应用关闭'): void {
  state.value = 'closed'
  automaticReconnectEnabled = false
  // 递增代次使协商中的在途连接尝试恢复后自行失效
  connectGeneration++
  clearReconnectTimer()
  reconnectAttempts = 0
  connectPromise = null
  connectAttemptToken = null
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
export function send<TType extends string>(
  id: string,
  type: TType,
  data?: WSDataForType<TType>
): boolean {
  if (!id.trim() || !type.trim()) {
    logger.warn('WebSocket 消息 id/type 不能为空')
    return false
  }
  const ws = socket
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    logger.warn(`WebSocket 未连接，无法发送消息: id=${id}, type=${type}`)
    return false
  }
  try {
    ws.send(JSON.stringify({ id: id.trim(), type: type.trim(), data: data ?? {} }))
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
  responseTypes: readonly string[],
  data?: WSJsonObject,
  timeoutMs: number = 10000
): Promise<WSEnvelope> {
  const requestId = `req_${Date.now()}_${++requestCounter}`

  return new Promise<WSEnvelope>((resolve, reject) => {
    const subscriptionIds: string[] = []
    const timer = window.setTimeout(() => {
      cleanup()
      reject(new Error(t('misc.requestTimedOutP0', { p0: id, p1: requestType })))
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
          const responseId = message.data.requestId
          if (responseId !== requestId) return
          cleanup()
          resolve(message)
        })
      )
    }

    if (!send(id, requestType, { ...(data ?? {}), requestId })) {
      cleanup()
      reject(new Error(t('misc.requestFailedP0P1', { p0: id, p1: requestType })))
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

/**
 * 注册成功连接监听。每次连接进入 open 时调用一次，可用于读取 HTTP 权威快照。
 * 返回幂等释放函数；不会重放注册前的连接事件。
 */
export function onConnected(listener: ConnectedListener): () => void {
  connectedListeners.push(listener)
  let disposed = false
  return () => {
    if (disposed) return
    disposed = true
    const index = connectedListeners.indexOf(listener)
    if (index >= 0) connectedListeners.splice(index, 1)
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
    automaticReconnectEnabled,
    backendDevMode,
  }
}
