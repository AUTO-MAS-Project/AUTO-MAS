// 应用生命周期协调器
// 职责：应用级常驻订阅（生命周期/电源）、正常关闭流程（含 taskkill 兜底）、
// 异常断开后的后端自动重启与恢复失败兜底。
// 连接层（services/websocket）只负责连接与分发，后端进程管理与退出决策集中在这里。

import { ref, type Ref } from 'vue'
import { Modal } from 'ant-design-vue'
import { Service } from '@/api'
import { useAppClosing } from '@/composables/useAppClosing'
import { realtimeSnapshotApi } from '@/services/realtimeSnapshotApi'
import {
  bootstrapResidentResources,
  disposeResidentResources,
} from '@/services/websocket/residentResources'
import {
  connect,
  connectionState,
  isBackendDevMode,
  onConnected,
  onDisconnected,
  onReconnectCycleFailed,
  reconnectNow,
  scheduleReconnect,
  shutdown as shutdownConnection,
  stopReconnect,
} from '@/services/websocket/connection'
import { subscribe, unsubscribe } from '@/services/websocket/subscriptions'
import {
  WS_BACKEND_SHUTDOWN_READY,
  WS_FRONTEND_CLOSE_REQUESTED,
  WS_ID_MAIN,
  WS_POWER_COUNTDOWN_CANCELLED,
  WS_POWER_COUNTDOWN_UPDATED,
  type WSDisconnectEvent,
  type WSPowerCountdownData,
} from '@/services/websocket/types'

const logger = window.electronAPI.getLogger('应用生命周期')

// ==================== 常量 ====================

// 正常关闭流程超时（非心跳超时）：超时未收到 backend.shutdown.ready 直接 taskkill。
// teardown 会等待所有任务真正收尾（含模拟器清理），10 秒不足以覆盖重任务场景，
// 过早 taskkill 会打断插件与配置清理；后端挂死时由该上限兜底。
const CLOSE_READY_TIMEOUT = 30000
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
let lifecycleDisposers: Array<() => void> = []
let residentSubscriptionIds: string[] = []

// 正常关闭流程状态（权威，优先级最高）
let closePromise: Promise<void> | null = null
let shutdownReadyReceived = false
let closeRequestedByBackend = false
let taskkillDone = false
let resolveShutdownReady: ((ready: boolean) => void) | null = null

// 后端自动重启状态
let restartPromise: Promise<void> | null = null
let disconnectRecoveryPromise: Promise<void> | null = null
let resumeRecoveryPromise: Promise<void> | null = null
let backendRestartAttempts = 0
let restartFailureShown = false
let disconnectIncidentShown = false
let closeDisconnectModal: (() => void) | null = null

// HTTP 快照与同时到达的 WS 事件使用单调序号协调：HTTP 是连接建立时的初始权威状态，
// 但请求发出后到达的 WS 事件必须覆盖该快照，不能被较旧的 HTTP 响应回滚。
let lifecycleSnapshotGeneration = 0
let powerMutationSequence = 0

const backendStatus: Ref<BackendStatus> = ref('unknown')
const powerCountdown: Ref<WSPowerCountdownData | null> = ref(null)

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
    stopReconnect()
    shutdownConnection('后端请求关闭异常')
    disposeAppLifecycle()
    return window.electronAPI?.appQuit?.()
  })
}

const handlePowerCountdownUpdated = (data: WSPowerCountdownData): void => {
  powerMutationSequence++
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
  powerMutationSequence++
  logger.info('电源倒计时已取消')
  if (powerCountdownStaleTimer !== undefined) {
    window.clearTimeout(powerCountdownStaleTimer)
    powerCountdownStaleTimer = undefined
  }
  powerCountdown.value = null
}

const refreshLifecycleSnapshots = async (): Promise<void> => {
  const generation = ++lifecycleSnapshotGeneration
  const powerSequenceAtStart = powerMutationSequence

  try {
    const snapshot = await realtimeSnapshotApi.getPowerCountdown()
    if (generation !== lifecycleSnapshotGeneration || isClosing()) return

    // 请求期间有更新/取消事件时，WS 后续事件优先，不能被初始快照回滚。
    if (powerMutationSequence === powerSequenceAtStart) {
      if (
        snapshot.active === true &&
        typeof snapshot.operation === 'string' &&
        typeof snapshot.remaining === 'number'
      ) {
        handlePowerCountdownUpdated({
          operation: snapshot.operation,
          remaining: snapshot.remaining,
        })
      } else {
        handlePowerCountdownCancelled()
      }
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.warn(`读取电源倒计时 HTTP 快照失败: ${errorMsg}`)
  }
}

const handleConnected = async (): Promise<void> => {
  backendRestartAttempts = 0
  restartFailureShown = false
  disconnectIncidentShown = false
  backendStatus.value = 'running'
  closeDisconnectModal?.()
  closeDisconnectModal = null
  await refreshLifecycleSnapshots()
}

// ==================== 正常关闭流程 ====================

const waitForShutdownReady = (timeoutMs: number): Promise<boolean> => {
  if (shutdownReadyReceived) return Promise.resolve(true)
  return new Promise<boolean>(resolve => {
    let settled = false
    let timer: number | undefined
    const settle = (ready: boolean): void => {
      if (settled) return
      settled = true
      if (timer !== undefined) window.clearTimeout(timer)
      resolveShutdownReady = null
      resolve(ready)
    }
    resolveShutdownReady = settle
    timer = window.setTimeout(() => settle(false), timeoutMs)
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
    // IPC 失败或返回结构异常时状态为 unknown，不能据此宣称进程已经退出。
    // 只有显式 false 才完成优雅退出确认；其余情况继续轮询并最终进入 taskkill。
    if (running === false) return true
    await delay(PROCESS_POLL_INTERVAL)
  }
  return false
}

const killBackend = async (): Promise<void> => {
  // taskkill 幂等：整个关闭流程仅执行一次
  if (taskkillDone) return
  taskkillDone = true
  // 开发模式后端由开发者独立管理（如 yarn dev:fullstack 单独启动），
  // 收到 ready 后仍会保持运行，绝不能被前端强杀
  if (isBackendDevMode()) {
    logger.info('开发模式：跳过 taskkill，保留开发者管理的后端进程')
    return
  }
  logger.warn('执行 taskkill 强制关闭后端')
  try {
    const result = await window.electronAPI?.killAllProcesses?.()
    if (!result?.success) {
      logger.error(`taskkill 执行失败: ${result?.error ?? '进程管理 IPC 不可用'}`)
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`taskkill 执行失败: ${errorMsg}`)
  }
}

/** 释放所有常驻订阅、连接事件和 Electron 生命周期监听器（幂等）。 */
export function disposeAppLifecycle(): void {
  if (!initialized && lifecycleDisposers.length === 0 && residentSubscriptionIds.length === 0) {
    return
  }

  initialized = false
  lifecycleSnapshotGeneration++
  for (const dispose of lifecycleDisposers.splice(0).reverse()) {
    try {
      dispose()
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.warn(`释放生命周期监听器失败: ${errorMsg}`)
    }
  }
  for (const subscriptionId of residentSubscriptionIds.splice(0)) {
    unsubscribe(subscriptionId)
  }
  disposeResidentResources()
  if (powerCountdownStaleTimer !== undefined) {
    window.clearTimeout(powerCountdownStaleTimer)
    powerCountdownStaleTimer = undefined
  }
  closeDisconnectModal?.()
  closeDisconnectModal = null
  logger.info('应用生命周期协调器已释放')
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
  let backendExitConfirmed = false
  if (isBackendDevMode()) {
    // 开发模式：后端由开发者独立管理，收到清理信号即视为关闭成功，
    // 不等待进程退出、不 taskkill，直接关闭前端
    logger.info('开发模式：后端保持运行，前端直接退出')
    backendExitConfirmed = true
  } else if (ready) {
    // ready 表示 teardown 已完成；从此刻起给进程完整的正常退出窗口，
    // 不能让 ready 到达较晚而把退出观察期压缩到接近 0。
    logger.info('等待后端进程正常退出')
    const exited = await waitForBackendExit(PROCESS_EXIT_TIMEOUT)
    backendExitConfirmed = exited
    if (!backendExitConfirmed) {
      logger.warn('后端进程未在规定时间内退出')
      await killBackend()
      backendExitConfirmed = await waitForBackendExit(PROCESS_EXIT_TIMEOUT)
    }
  } else {
    // 超时或等待期间连接断开且未收到 ready：不自动重启，直接 taskkill
    logger.warn('未在超时时间内收到 backend.shutdown.ready')
    await killBackend()
    backendExitConfirmed = await waitForBackendExit(PROCESS_EXIT_TIMEOUT)
  }

  shutdownConnection('应用关闭')
  disposeAppLifecycle()
  if (!backendExitConfirmed) {
    logger.error('taskkill 后仍无法确认后端退出，等待 Electron 主进程最终兜底')
    return
  }
  logger.info('后端已退出，关闭前端')
  await window.electronAPI?.appQuit?.()
}

const runBackendRequestedClose = async (): Promise<void> => {
  // 后端主动要求前端关闭：后端自行退出中，前端不再发 /close、不重启、不 taskkill
  const { showClosingOverlay } = useAppClosing()
  showClosingOverlay()
  stopReconnect()
  shutdownConnection('后端请求关闭')
  disposeAppLifecycle()
  await window.electronAPI?.appQuit?.()
}

/**
 * 退出并关闭后端（幂等）。
 * 状态优先级：关闭流程最高，期间不允许自动重启；重复调用返回同一流程。
 */
export function closeApp(): Promise<void> {
  if (closePromise) return closePromise
  closePromise = runCloseFlow().catch(async error => {
    // 关闭流程异常时只在确认后端已退出后通知主进程结束；否则保留遮罩，
    // 由 Electron 主进程的最终超时兜底再次执行串行 taskkill。
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`关闭流程异常: ${errorMsg}`)
    stopReconnect()
    const devMode = isBackendDevMode()
    if (!devMode) await killBackend()
    const backendExitConfirmed = devMode || (await waitForBackendExit(PROCESS_EXIT_TIMEOUT))
    shutdownConnection('关闭流程异常')
    disposeAppLifecycle()
    if (!backendExitConfirmed) {
      logger.error('异常关闭兜底仍无法确认后端退出，等待 Electron 主进程最终兜底')
      return
    }
    await window.electronAPI?.appQuit?.()
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

const restartBackendFlow = (allowDevMode: boolean = false): Promise<void> => {
  // 单飞行：断开、重连周期失败和系统恢复只能共享同一个后端重启流程。
  // 关闭流程具有最高优先级，任何异步步骤后都会重新检查并退出。
  if (restartPromise) return restartPromise
  if (restartFailureShown || isClosing()) return Promise.resolve()
  if (isBackendDevMode() && !allowDevMode) {
    logger.warn('开发模式后端由开发者管理，跳过自动重启并继续重连')
    scheduleReconnect(DEV_MODE_RETRY_DELAY)
    return Promise.resolve()
  }
  if (backendRestartAttempts >= MAX_BACKEND_RESTART_ATTEMPTS) {
    showRestartFailureModal()
    return Promise.resolve()
  }

  const run = async (): Promise<void> => {
    backendRestartAttempts++
    backendStatus.value = 'starting'
    logger.warn(`尝试恢复后端服务 (第 ${backendRestartAttempts} 次)`)

    try {
      let result: { success: boolean; error?: string; logs?: string } | undefined
      if (window.electronAPI?.backendRestart) {
        result = await window.electronAPI.backendRestart()
      } else {
        await window.electronAPI?.stopBackend?.()
        if (isClosing()) return
        result = await window.electronAPI?.startBackend?.()
      }
      if (isClosing()) return

      if (!result?.success) {
        backendStatus.value = 'error'
        logger.error(`后端恢复失败: ${result?.error ?? '未知错误'}`)
        if (backendRestartAttempts >= MAX_BACKEND_RESTART_ATTEMPTS) {
          showRestartFailureModal()
        } else if (!isClosing()) {
          scheduleReconnect(RESTART_DELAY)
        }
        return
      }

      logger.info('后端恢复成功，原子替换 WebSocket 连接')
      backendStatus.value = 'running'
      await delay(RESTART_DELAY)
      if (isClosing()) return
      const connected = await reconnectNow('后端恢复完成')
      if (!connected && !isClosing()) {
        backendStatus.value = 'error'
        scheduleReconnect(RESTART_DELAY)
      }
    } catch (error) {
      backendStatus.value = 'error'
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`后端恢复异常: ${errorMsg}`)
      if (backendRestartAttempts >= MAX_BACKEND_RESTART_ATTEMPTS) {
        showRestartFailureModal()
      } else if (!isClosing()) {
        scheduleReconnect(RESTART_DELAY)
      }
    }
  }

  restartPromise = run().finally(() => {
    restartPromise = null
  })
  return restartPromise
}

const showDisconnectIncident = (event: WSDisconnectEvent): void => {
  if (disconnectIncidentShown) return
  disconnectIncidentShown = true
  logger.error(`主 WebSocket 异常断开: code=${event.code}, reason=${event.reason || '无'}`)
  const modal = Modal.warning({
    title: '与后端的连接已中断',
    content: '正在检查后端状态并自动恢复。任务状态会在连接恢复后从 HTTP 快照重新同步。',
    okText: '知道了',
  })
  if (modal && typeof modal.destroy === 'function') {
    closeDisconnectModal = () => modal.destroy()
  }
}

const recoverAfterDisconnect = (): Promise<void> => {
  if (disconnectRecoveryPromise) return disconnectRecoveryPromise
  disconnectRecoveryPromise = (async () => {
    const running = await queryBackendRunning()
    if (isClosing() || restartFailureShown) return
    if (running === false) await restartBackendFlow()
  })().finally(() => {
    disconnectRecoveryPromise = null
  })
  return disconnectRecoveryPromise
}

const handleDisconnected = (event: WSDisconnectEvent): void => {
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
  showDisconnectIncident(event)
  void recoverAfterDisconnect()
}

const handleReconnectCycleFailed = async (): Promise<void> => {
  if (isClosing() || restartFailureShown) return

  const running = await queryBackendRunning()
  // IPC 查询期间关闭流程可能已开始：重查后再决策，避免在关闭态重建重连计时器
  // 或触发自动重启（与 taskkill 互斥）
  if (isClosing() || restartFailureShown) return

  if (running === false) {
    await restartBackendFlow()
  } else {
    // 后端进程存活或状态未知：延迟后继续下一轮重连
    logger.warn('后端进程仍在运行或状态未知，稍后继续重连')
    scheduleReconnect(isBackendDevMode() ? DEV_MODE_RETRY_DELAY : NEXT_CYCLE_DELAY)
  }
}

const handleSystemResume = (): Promise<void> => {
  if (resumeRecoveryPromise) return resumeRecoveryPromise
  resumeRecoveryPromise = (async () => {
    if (isClosing()) return
    logger.info('检测到系统恢复，检查后端和主 WebSocket')

    const running = await queryBackendRunning()
    let httpReachable = false
    try {
      await Service.getWsMetaApiCoreWsMetaGet()
      httpReachable = true
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.warn(`系统恢复后 ws_meta 检查失败: ${errorMsg}`)
    }
    if (isClosing()) return

    if (running === false || !httpReachable) {
      await restartBackendFlow()
      return
    }

    await reconnectNow('系统从睡眠恢复')
  })().finally(() => {
    resumeRecoveryPromise = null
  })
  return resumeRecoveryPromise
}

// ==================== 初始化与连接 ====================

/**
 * 初始化生命周期协调器：注册应用级常驻订阅与连接事件监听。
 * 幂等；必须在建立 WebSocket 连接前调用，重连不会重复注册，页面切换不会取消。
 */
export function initializeAppLifecycle(): void {
  if (initialized) return

  // 所有应用级业务订阅都必须早于主连接建立；该入口覆盖初始化向导、正常进入和手动连接。
  bootstrapResidentResources()
  initialized = true

  // 先注册所有应用级常驻订阅，再允许建立连接；所有监听器都有明确释放函数。
  residentSubscriptionIds = [
    subscribe({ id: WS_ID_MAIN, type: WS_BACKEND_SHUTDOWN_READY }, () => handleShutdownReady()),
    subscribe({ id: WS_ID_MAIN, type: WS_FRONTEND_CLOSE_REQUESTED }, () => handleCloseRequested()),
    subscribe({ id: WS_ID_MAIN, type: WS_POWER_COUNTDOWN_UPDATED }, message =>
      handlePowerCountdownUpdated(message.data)
    ),
    subscribe({ id: WS_ID_MAIN, type: WS_POWER_COUNTDOWN_CANCELLED }, () =>
      handlePowerCountdownCancelled()
    ),
  ]

  lifecycleDisposers = [
    onConnected(handleConnected),
    onDisconnected(handleDisconnected),
    onReconnectCycleFailed(() => {
      void handleReconnectCycleFailed()
    }),
  ]

  const disposeSystemResume = window.electronAPI?.onSystemResume?.(() => {
    void handleSystemResume()
  })
  if (disposeSystemResume) lifecycleDisposers.push(disposeSystemResume)

  const disposeCloseRequested = window.electronAPI?.onAppCloseRequested?.(() => {
    void closeApp()
  })
  if (disposeCloseRequested) lifecycleDisposers.push(disposeCloseRequested)

  // 防止极端启动竞态：如果调用者在连接刚 open 后才完成初始化，立即补一次快照。
  if (connectionState().value === 'open') void handleConnected()

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
  const connected = await reconnectNow('用户手动重连')
  if (connected) backendStatus.value = 'running'
  return connected
}

/** 手动重启后端（重置失败计数） */
export async function restartBackendManually(): Promise<void> {
  backendRestartAttempts = 0
  restartFailureShown = false
  await restartBackendFlow(true)
}

export function useAppLifecycle() {
  return {
    initializeAppLifecycle,
    disposeAppLifecycle,
    connectWithRetry,
    closeApp,
    manualReconnect,
    restartBackendManually,
    backendStatus,
    powerCountdown,
    connectionState: connectionState(),
  }
}
