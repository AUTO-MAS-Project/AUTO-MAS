// 应用生命周期协调器
// 职责：应用级常驻订阅（生命周期/电源/弹窗）、正常关闭流程（含 10 秒 taskkill 兜底）、
// 异常断开后的后端自动重启与恢复失败兜底。
// 连接层（services/websocket）只负责连接与分发，后端进程管理与退出决策集中在这里。

import { ref, watch, type Ref } from 'vue'
import { Modal } from 'ant-design-vue'
import { Service } from '@/api'
import { useAppClosing } from '@/composables/useAppClosing'
import {
  connect,
  connectionState,
  isBackendDevMode,
  onDisconnected,
  onReconnectCycleFailed,
  scheduleReconnect,
  send,
  shutdown as shutdownConnection,
  stopReconnect,
} from '@/services/websocket/connection'
import { subscribe } from '@/services/websocket/subscriptions'
import {
  WS_BACKEND_SHUTDOWN_READY,
  WS_DIALOG_REQUEST,
  WS_DIALOG_RESPONSE,
  WS_FRONTEND_CLOSE_REQUESTED,
  WS_ID_MAIN,
  WS_POWER_COUNTDOWN_CANCELLED,
  WS_POWER_COUNTDOWN_UPDATED,
  type WSDialogRequestData,
  type WSPowerCountdownData,
} from '@/services/websocket/types'

const logger = window.electronAPI.getLogger('应用生命周期')

// ==================== 常量 ====================

// 正常关闭流程超时（非心跳超时）：10 秒内未收到 backend.shutdown.ready 直接 taskkill
const CLOSE_READY_TIMEOUT = 10000
// 收到 ready 后等待后端进程正常退出的时限，超时才允许 taskkill
const PROCESS_EXIT_TIMEOUT = 5000
const PROCESS_POLL_INTERVAL = 300
// 后端自动重启
const MAX_BACKEND_RESTART_ATTEMPTS = 3
const RESTART_DELAY = 2000
// 一轮重连失败后，后端进程仍存活时的下一轮延迟
const NEXT_CYCLE_DELAY = 30000
const DEV_MODE_RETRY_DELAY = 3000
// 倒计时消息停止更新后自动清除展示状态
const POWER_COUNTDOWN_STALE_MS = 3000

export type BackendStatus = 'unknown' | 'starting' | 'running' | 'stopped' | 'error'

// ==================== 模块级状态 ====================

let initialized = false

// 正常关闭流程状态（权威，优先级最高）
let closePromise: Promise<void> | null = null
let shutdownReadyReceived = false
let closeRequestedByBackend = false
let taskkillDone = false
let resolveShutdownReady: ((ready: boolean) => void) | null = null

// 后端自动重启状态
let isRestartingBackend = false
let backendRestartAttempts = 0
let restartFailureShown = false

const backendStatus: Ref<BackendStatus> = ref('unknown')
const powerCountdown: Ref<WSPowerCountdownData | null> = ref(null)
const dialogRequests: Ref<WSDialogRequestData[]> = ref([])

let powerCountdownStaleTimer: number | undefined

const delay = (ms: number): Promise<void> => new Promise(resolve => window.setTimeout(resolve, ms))

const isClosing = (): boolean => closePromise !== null

// ==================== 常驻订阅 ====================

const handleShutdownReady = (): void => {
  // 仅在本次关闭流程期间生效：第三方（如 Koishi 远程命令）触发的 /close
  // 也会广播 ready，不能留下陈旧标志影响之后真正的关闭流程
  if (!isClosing()) {
    logger.info('收到 backend.shutdown.ready（非关闭流程期间，忽略）')
    return
  }
  logger.info('收到 backend.shutdown.ready，后端清理完成')
  shutdownReadyReceived = true
  resolveShutdownReady?.(true)
}

const handleCloseRequested = (): void => {
  logger.info('收到后端关闭请求 frontend.close.requested，前端开始退出')
  closeRequestedByBackend = true
  if (closePromise) return
  closePromise = runBackendRequestedClose().catch(error => {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`后端请求关闭流程异常: ${errorMsg}`)
    return window.electronAPI?.appQuit?.()
  })
}

const handlePowerCountdownUpdated = (data: WSPowerCountdownData): void => {
  powerCountdown.value = data
  if (powerCountdownStaleTimer !== undefined) {
    window.clearTimeout(powerCountdownStaleTimer)
  }
  // 倒计时更新停止（已执行或后端消失）后清除展示状态
  powerCountdownStaleTimer = window.setTimeout(() => {
    powerCountdown.value = null
  }, POWER_COUNTDOWN_STALE_MS)
}

const handlePowerCountdownCancelled = (): void => {
  logger.info('电源倒计时已取消')
  if (powerCountdownStaleTimer !== undefined) {
    window.clearTimeout(powerCountdownStaleTimer)
    powerCountdownStaleTimer = undefined
  }
  powerCountdown.value = null
}

const handleDialogRequest = (data: WSDialogRequestData): void => {
  if (!data.requestId) {
    logger.warn('弹窗请求缺少 requestId，已忽略')
    return
  }
  // 重连后后端会重发未完成的弹窗请求，按 requestId 去重
  if (dialogRequests.value.some(item => item.requestId === data.requestId)) {
    logger.debug(`弹窗请求已存在，忽略重复: ${data.requestId}`)
    return
  }
  logger.info(`收到弹窗请求: ${data.requestId}`)
  dialogRequests.value = [...dialogRequests.value, data]
}

/** 回复应用内弹窗（用户选择第一个选项时 choice=true） */
export function respondDialog(requestId: string, choice: boolean): void {
  // 发送失败（断连瞬间）时保留弹窗，等重连后用户可再次作答
  if (!send(WS_ID_MAIN, WS_DIALOG_RESPONSE, { requestId, choice })) {
    logger.warn(`弹窗响应发送失败，保留弹窗等待重试: ${requestId}`)
    return
  }
  dialogRequests.value = dialogRequests.value.filter(item => item.requestId !== requestId)
}

// ==================== 正常关闭流程 ====================

const waitForShutdownReady = (timeoutMs: number): Promise<boolean> => {
  if (shutdownReadyReceived) return Promise.resolve(true)
  return new Promise<boolean>(resolve => {
    let settled = false
    const settle = (ready: boolean): void => {
      if (settled) return
      settled = true
      resolveShutdownReady = null
      resolve(ready)
    }
    resolveShutdownReady = settle
    window.setTimeout(() => settle(false), timeoutMs)
  })
}

const queryBackendRunning = async (): Promise<boolean | null> => {
  try {
    const status = await window.electronAPI?.backendStatus?.()
    if (typeof status?.isRunning === 'boolean') {
      return status.isRunning
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.warn(`查询后端进程状态失败: ${errorMsg}`)
  }
  return null
}

const waitForBackendExit = async (timeoutMs: number): Promise<boolean> => {
  const startedAt = Date.now()
  while (Date.now() - startedAt < timeoutMs) {
    const running = await queryBackendRunning()
    if (running !== true) return true
    await delay(PROCESS_POLL_INTERVAL)
  }
  return false
}

const killBackend = async (): Promise<void> => {
  // taskkill 幂等：整个关闭流程仅执行一次
  if (taskkillDone) return
  taskkillDone = true
  logger.warn('执行 taskkill 强制关闭后端')
  try {
    await window.electronAPI?.killAllProcesses?.()
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`taskkill 执行失败: ${errorMsg}`)
  }
}

const runCloseFlow = async (): Promise<void> => {
  logger.info('开始执行退出并关闭后端流程')
  const { showClosingOverlay } = useAppClosing()
  showClosingOverlay()

  // 关闭流程期间停止普通自动重连；自动重启与 taskkill 互斥由 isClosing() 保证
  stopReconnect()

  // 先挂好 ready 等待，再发 POST /close，避免消息先于等待到达
  const readyPromise = waitForShutdownReady(CLOSE_READY_TIMEOUT)

  try {
    await Service.closeApiCoreClosePost()
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.warn(`POST /close 请求失败: ${errorMsg}`)
  }

  const ready = await readyPromise
  if (ready) {
    // 已收到 ready：优先等待后端进程正常退出，超时才 taskkill
    logger.info('等待后端进程正常退出')
    const exited = await waitForBackendExit(PROCESS_EXIT_TIMEOUT)
    if (!exited) {
      logger.warn('后端进程未在规定时间内退出')
      await killBackend()
      await waitForBackendExit(PROCESS_EXIT_TIMEOUT)
    }
  } else {
    // 超时或等待期间连接断开且未收到 ready：不自动重启，直接 taskkill
    logger.warn('未在超时时间内收到 backend.shutdown.ready')
    await killBackend()
    await waitForBackendExit(PROCESS_EXIT_TIMEOUT)
  }

  shutdownConnection('应用关闭')
  logger.info('后端已退出，关闭前端')
  await window.electronAPI?.appQuit?.()
}

const runBackendRequestedClose = async (): Promise<void> => {
  // 后端主动要求前端关闭：后端自行退出中，前端不再发 /close、不重启、不 taskkill
  const { showClosingOverlay } = useAppClosing()
  showClosingOverlay()
  stopReconnect()
  shutdownConnection('后端请求关闭')
  await window.electronAPI?.appQuit?.()
}

/**
 * 退出并关闭后端（幂等）。
 * 状态优先级：关闭流程最高，期间不允许自动重启；重复调用返回同一流程。
 */
export function closeApp(): Promise<void> {
  if (closePromise) return closePromise
  closePromise = runCloseFlow().catch(error => {
    // 关闭流程异常时兜底退出，避免卡死在遮罩上
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`关闭流程异常: ${errorMsg}`)
    return window.electronAPI?.appQuit?.()
  })
  return closePromise
}

// ==================== 异常断开与自动恢复 ====================

const showRestartFailureModal = (): void => {
  // 达到恢复失败上限：仅提示一次，提供重启应用兜底
  if (restartFailureShown) return
  restartFailureShown = true
  backendStatus.value = 'error'
  stopReconnect()

  Modal.error({
    title: '后端服务恢复失败',
    content: '后端服务多次重启后仍无法建立连接，请重启整个应用后再试。',
    okText: '重启应用',
    onOk: () => {
      const { showClosingOverlay } = useAppClosing()
      showClosingOverlay()

      if (window.electronAPI?.appRestart) {
        window.electronAPI.appRestart()
      } else if (window.electronAPI?.windowClose) {
        window.electronAPI.windowClose()
      } else {
        window.location.reload()
      }
    },
  })
}

const restartBackendFlow = async (): Promise<void> => {
  // 单飞行：同一次异常只触发一个重启流程；关闭流程期间禁止重启
  if (isRestartingBackend || restartFailureShown || isClosing()) return

  if (backendRestartAttempts >= MAX_BACKEND_RESTART_ATTEMPTS) {
    showRestartFailureModal()
    return
  }

  isRestartingBackend = true
  backendRestartAttempts++
  backendStatus.value = 'starting'
  logger.warn(`后端进程已停止，尝试自动重启 (第 ${backendRestartAttempts} 次)`)

  try {
    await window.electronAPI?.stopBackend?.()
    // 每个异步步骤后重新确认：关闭流程期间立即放弃重启，保证与 taskkill 互斥
    if (isClosing()) return

    const result = await window.electronAPI?.startBackend?.()
    if (isClosing()) return

    if (result?.success) {
      logger.info('后端重启成功，重新建立 WebSocket 连接')
      backendStatus.value = 'running'
      await delay(RESTART_DELAY)
      if (isClosing()) return
      // 连接失败会触发连接层自身的重连循环，无需额外处理
      await connect()
    } else {
      backendStatus.value = 'error'
      logger.error(`后端重启失败: ${result?.error ?? '未知错误'}`)
      if (backendRestartAttempts >= MAX_BACKEND_RESTART_ATTEMPTS) {
        showRestartFailureModal()
      } else if (!isClosing()) {
        scheduleReconnect(RESTART_DELAY)
      }
    }
  } catch (error) {
    backendStatus.value = 'error'
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`后端重启异常: ${errorMsg}`)
    if (backendRestartAttempts >= MAX_BACKEND_RESTART_ATTEMPTS) {
      showRestartFailureModal()
    } else if (!isClosing()) {
      scheduleReconnect(RESTART_DELAY)
    }
  } finally {
    isRestartingBackend = false
  }
}

const handleDisconnected = (): void => {
  if (isClosing() || closeRequestedByBackend) {
    // 关闭流程期间断开：连接层进入终态，禁止任何重连；
    // 未收到 ready 则立刻走 taskkill 分支
    shutdownConnection('关闭流程中断开')
    if (!shutdownReadyReceived) {
      logger.warn('关闭流程期间 WebSocket 断开且未收到 ready')
      resolveShutdownReady?.(false)
    }
    return
  }
  backendStatus.value = 'stopped'
}

const handleReconnectCycleFailed = async (): Promise<void> => {
  if (isClosing() || restartFailureShown) return

  const running = await queryBackendRunning()
  if (running === false) {
    // 后端进程已死：自动重启（与 taskkill 互斥——关闭流程中不会进入此分支）
    await restartBackendFlow()
  } else {
    // 后端进程存活或状态未知：延迟后继续下一轮重连
    logger.warn('后端进程仍在运行或状态未知，稍后继续重连')
    scheduleReconnect(isBackendDevMode() ? DEV_MODE_RETRY_DELAY : NEXT_CYCLE_DELAY)
  }
}

// ==================== 初始化与连接 ====================

/**
 * 初始化生命周期协调器：注册应用级常驻订阅与连接事件监听。
 * 幂等；必须在建立 WebSocket 连接前调用，重连不会重复注册，页面切换不会取消。
 */
export function initializeAppLifecycle(): void {
  if (initialized) return
  initialized = true

  // 应用级常驻订阅（应用退出时随进程释放）
  subscribe({ id: WS_ID_MAIN, type: WS_BACKEND_SHUTDOWN_READY }, () => handleShutdownReady())
  subscribe({ id: WS_ID_MAIN, type: WS_FRONTEND_CLOSE_REQUESTED }, () => handleCloseRequested())
  subscribe({ id: WS_ID_MAIN, type: WS_POWER_COUNTDOWN_UPDATED }, message =>
    handlePowerCountdownUpdated(message.data as unknown as WSPowerCountdownData)
  )
  subscribe({ id: WS_ID_MAIN, type: WS_POWER_COUNTDOWN_CANCELLED }, () =>
    handlePowerCountdownCancelled()
  )
  subscribe({ id: WS_ID_MAIN, type: WS_DIALOG_REQUEST }, message =>
    handleDialogRequest(message.data as unknown as WSDialogRequestData)
  )

  onDisconnected(() => handleDisconnected())
  onReconnectCycleFailed(() => {
    void handleReconnectCycleFailed()
  })

  logger.info('应用生命周期协调器已初始化')
}

/**
 * 建立主 WebSocket 连接，失败时按间隔重试。
 * 用于启动流程；连接失败不抛异常（初始化容错由调用方决定）。
 */
export async function connectWithRetry(
  attempts: number = 3,
  retryDelayMs: number = 2000
): Promise<boolean> {
  initializeAppLifecycle()

  for (let attempt = 1; attempt <= attempts; attempt++) {
    try {
      const connected = await connect()
      if (connected) {
        backendStatus.value = 'running'
        return true
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.warn(`第 ${attempt} 次连接异常: ${errorMsg}`)
    }
    if (attempt < attempts) {
      await delay(retryDelayMs)
    }
  }
  logger.warn(`WebSocket 连接失败，已重试 ${attempts} 次`)
  return false
}

/** 手动重连（devtools/恢复入口） */
export async function manualReconnect(): Promise<boolean> {
  if (isClosing()) return false
  stopReconnect()
  restartFailureShown = false
  backendRestartAttempts = 0
  const connected = await connect()
  if (connected) backendStatus.value = 'running'
  return connected
}

/** 手动重启后端（重置失败计数） */
export async function restartBackendManually(): Promise<void> {
  backendRestartAttempts = 0
  restartFailureShown = false
  await restartBackendFlow()
}

// 连接成功时重置重启计数与失败标志
watch(connectionState(), state => {
  if (state === 'open') {
    backendRestartAttempts = 0
    restartFailureShown = false
    backendStatus.value = 'running'
  }
})

export function useAppLifecycle() {
  return {
    initializeAppLifecycle,
    connectWithRetry,
    closeApp,
    manualReconnect,
    restartBackendManually,
    respondDialog,
    backendStatus,
    powerCountdown,
    dialogRequests,
    connectionState: connectionState(),
  }
}
