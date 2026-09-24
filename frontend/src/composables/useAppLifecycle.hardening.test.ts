import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

// issue #443：断线关闭、恢复失败终态、自动重启计数、断线期间电源倒计时

// ==================== 全局桩 ====================

const logger = { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() }

const modalError = vi.fn()
const modalErrorDestroy = vi.fn()

vi.mock('ant-design-vue', () => ({
  Modal: {
    warning: () => ({ destroy: vi.fn() }),
    error: (...args: unknown[]) => {
      modalError(...args)
      return { destroy: modalErrorDestroy }
    },
  },
  notification: { warning: vi.fn(), info: vi.fn(), close: vi.fn() },
}))

vi.mock('@/i18n', () => ({ translate: (key: string) => key }))

const closePost = vi.hoisted(() => vi.fn())
const getWsMeta = vi.hoisted(() => vi.fn())
const cancelPowerPost = vi.hoisted(() => vi.fn())
vi.mock('@/api', () => ({
  Service: {
    closeApiCoreClosePost: closePost,
    getWsMetaApiCoreWsMetaGet: getWsMeta,
    cancelPowerTaskApiDispatchCancelPowerPost: cancelPowerPost,
  },
}))

vi.mock('@/composables/useAppClosing', () => ({
  useAppClosing: () => ({ showClosingOverlay: vi.fn() }),
}))

vi.mock('@/services/realtimeSnapshotApi', () => ({
  realtimeSnapshotApi: { getPowerCountdown: vi.fn(async () => ({ active: false })) },
}))

vi.mock('@/services/websocket/residentResources', () => ({
  bootstrapResidentResources: vi.fn(),
  disposeResidentResources: vi.fn(),
}))

// 常驻订阅按消息类型记下处理函数，测试里据此模拟后端推送
type Handler = (message: { id: string; type: string; data: unknown }) => void
const subscriptionHandlers = vi.hoisted(() => new Map<string, Handler>())
vi.mock('@/services/websocket/subscriptions', () => ({
  subscribe: (filter: { id: string; type: string }, handler: Handler) => {
    subscriptionHandlers.set(filter.type, handler)
    return `sub_${filter.type}`
  },
  unsubscribe: vi.fn(),
}))

type DisconnectListener = (event: { code: number; reason: string }) => void
const listeners: {
  connected: Array<() => void | Promise<void>>
  disconnected: DisconnectListener[]
  cycleFailed: Array<() => void>
} = { connected: [], disconnected: [], cycleFailed: [] }
let devMode = false
const connectionStateRef = ref<'idle' | 'connecting' | 'open' | 'reconnecting' | 'closed'>('idle')

const connectionMocks = vi.hoisted(() => ({
  reconnectNow: vi.fn(async () => true),
  scheduleReconnect: vi.fn(),
  shutdown: vi.fn(),
  stopReconnect: vi.fn(),
}))

vi.mock('@/services/websocket/connection', () => ({
  connect: vi.fn(async () => true),
  connectionState: () => connectionStateRef,
  isBackendDevMode: () => devMode,
  onConnected: (listener: () => void | Promise<void>) => {
    listeners.connected.push(listener)
    return () => {}
  },
  onDisconnected: (listener: DisconnectListener) => {
    listeners.disconnected.push(listener)
    return () => {}
  },
  onReconnectCycleFailed: (listener: () => void) => {
    listeners.cycleFailed.push(listener)
    return () => {}
  },
  ...connectionMocks,
}))

const backendStatus = vi.fn()
const backendRestart = vi.fn()
const killAllProcesses = vi.fn()
const appQuit = vi.fn()
let systemResumeListener: (() => void) | null = null

const DISCONNECT_EVENT = { code: 1006, reason: '' }

const loadLifecycle = async () => {
  vi.resetModules()
  listeners.connected = []
  listeners.disconnected = []
  listeners.cycleFailed = []
  subscriptionHandlers.clear()
  systemResumeListener = null
  const mod = await import('./useAppLifecycle')
  mod.initializeAppLifecycle()
  return mod
}

const emitDisconnected = () => listeners.disconnected.forEach(l => l(DISCONNECT_EVENT))
const emitConnected = async () => {
  await Promise.all(listeners.connected.map(l => l()))
}
const emitCycleFailed = () => listeners.cycleFailed.forEach(l => l())
const pushMessage = (type: string, data: unknown = {}) => {
  const handler = subscriptionHandlers.get(type)
  if (!handler) throw new Error(`未注册常驻订阅: ${type}`)
  handler({ id: 'Main', type, data })
}

beforeEach(() => {
  vi.useFakeTimers()
  vi.clearAllMocks()
  devMode = false
  connectionStateRef.value = 'idle'
  closePost.mockResolvedValue({})
  getWsMeta.mockResolvedValue({})
  killAllProcesses.mockResolvedValue({ success: true })
  appQuit.mockResolvedValue(undefined)
  vi.stubGlobal('window', {
    electronAPI: {
      getLogger: () => logger,
      backendStatus,
      backendRestart,
      killAllProcesses,
      appQuit,
      onSystemResume: (listener: () => void) => {
        systemResumeListener = listener
        return () => {}
      },
    },
    setTimeout: (fn: () => void, ms?: number) => setTimeout(fn, ms),
    clearTimeout: (id: number) => clearTimeout(id),
  })
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

// ==================== #3 / #6 断线或从未连上时关闭 ====================

describe('主连接不在 open 时关闭不空等 ready', () => {
  it('后端已退出（断线）：不等 30 秒，立即确认退出并关闭前端，不 taskkill', async () => {
    connectionStateRef.value = 'reconnecting'
    backendStatus.mockResolvedValue({ isRunning: false, runtimeSupervised: false })
    const mod = await loadLifecycle()

    const closing = mod.closeApp()
    await vi.advanceTimersByTimeAsync(0)
    await closing

    expect(closePost).toHaveBeenCalledTimes(1)
    expect(killAllProcesses).not.toHaveBeenCalled()
    expect(appQuit).toHaveBeenCalledTimes(1)
  })

  it('断线但后端仍在收尾：等它自行退出，不提前 taskkill 打断停止任务的收尾', async () => {
    connectionStateRef.value = 'reconnecting'
    backendStatus.mockResolvedValue({ isRunning: true, runtimeSupervised: false })
    const mod = await loadLifecycle()

    void mod.closeApp()
    // 收尾（关模拟器、关游戏）耗时超过进程退出时限 5 秒
    await vi.advanceTimersByTimeAsync(12000)
    expect(killAllProcesses).not.toHaveBeenCalled()

    // teardown 完成后后端自行退出
    backendStatus.mockResolvedValue({ isRunning: false, runtimeSupervised: false })
    await vi.advanceTimersByTimeAsync(1000)
    expect(killAllProcesses).not.toHaveBeenCalled()
    expect(appQuit).toHaveBeenCalledTimes(1)
  })

  it('WS 从未建立而后端始终不退出：等满 ready 的时限后 taskkill', async () => {
    connectionStateRef.value = 'idle'
    backendStatus.mockResolvedValue({ isRunning: true, runtimeSupervised: false })
    killAllProcesses.mockImplementation(async () => {
      backendStatus.mockResolvedValue({ isRunning: false, runtimeSupervised: false })
      return { success: true }
    })
    const mod = await loadLifecycle()

    void mod.closeApp()
    await vi.advanceTimersByTimeAsync(29000)
    expect(killAllProcesses).not.toHaveBeenCalled()

    await vi.advanceTimersByTimeAsync(1500)
    expect(killAllProcesses).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(1000)
    expect(appQuit).toHaveBeenCalledTimes(1)
  })

  it('开发模式断线时关闭：前端直接退出，保留后端', async () => {
    devMode = true
    connectionStateRef.value = 'reconnecting'
    backendStatus.mockResolvedValue({ isRunning: true, runtimeSupervised: false })
    const mod = await loadLifecycle()

    const closing = mod.closeApp()
    await vi.advanceTimersByTimeAsync(0)
    await closing

    expect(killAllProcesses).not.toHaveBeenCalled()
    expect(appQuit).toHaveBeenCalledTimes(1)
  })

  it('连接正常时仍等待 ready，超时前不 taskkill', async () => {
    connectionStateRef.value = 'open'
    backendStatus.mockResolvedValue({ isRunning: true, runtimeSupervised: false })
    const mod = await loadLifecycle()

    void mod.closeApp()
    await vi.advanceTimersByTimeAsync(29000)
    expect(killAllProcesses).not.toHaveBeenCalled()
    expect(appQuit).not.toHaveBeenCalled()

    await vi.advanceTimersByTimeAsync(1000)
    expect(killAllProcesses).toHaveBeenCalledTimes(1)
  })
})

// ==================== #4 恢复失败终态与失败弹窗 ====================

describe('恢复失败终态', () => {
  const driveToTerminal = async () => {
    backendStatus.mockResolvedValue({ isRunning: false })
    backendRestart.mockResolvedValue({ success: false, error: '启动失败' })
    emitDisconnected()
    await vi.advanceTimersByTimeAsync(0)
    emitCycleFailed()
    await vi.advanceTimersByTimeAsync(0)
    emitCycleFailed()
    await vi.advanceTimersByTimeAsync(0)
  }

  it('睡眠唤醒后后端可达并重新连上：撤掉残留的失败弹窗', async () => {
    const mod = await loadLifecycle()
    const { backendStatus: status } = mod.useAppLifecycle()
    await driveToTerminal()
    expect(backendRestart).toHaveBeenCalledTimes(3)
    expect(modalError).toHaveBeenCalledTimes(1)
    expect(status.value).toBe('error')

    // 系统恢复：后端进程在、HTTP 可达，照常重连
    backendStatus.mockResolvedValue({ isRunning: true })
    systemResumeListener?.()
    await vi.advanceTimersByTimeAsync(0)
    expect(connectionMocks.reconnectNow).toHaveBeenCalledWith('系统从睡眠恢复')
    await emitConnected()

    expect(modalErrorDestroy).toHaveBeenCalledTimes(1)
    expect(status.value).toBe('running')
  })

  it('终态下睡眠唤醒但后端仍不可用：不再自动重启，失败弹窗保留', async () => {
    const mod = await loadLifecycle()
    await driveToTerminal()
    expect(backendRestart).toHaveBeenCalledTimes(3)

    getWsMeta.mockRejectedValue(new Error('ECONNREFUSED'))
    systemResumeListener?.()
    await vi.advanceTimersByTimeAsync(0)

    expect(backendRestart).toHaveBeenCalledTimes(3)
    expect(modalError).toHaveBeenCalledTimes(1)
    expect(modalErrorDestroy).not.toHaveBeenCalled()
    expect(mod.useAppLifecycle().backendStatus.value).toBe('error')
  })
})

// ==================== #17 自动重启按时间窗累计 ====================

describe('自动重启计数', () => {
  // 一次「能连上随即崩溃」：断开 → 进程不在 → 重启成功 → 延时后重连 → 连上
  const crashAndRecover = async () => {
    emitDisconnected()
    await vi.advanceTimersByTimeAsync(0)
    await vi.advanceTimersByTimeAsync(2000)
    await emitConnected()
  }

  it('连上即崩溃的循环在时间窗内达到上限后进入终态，不再无限重启', async () => {
    backendStatus.mockResolvedValue({ isRunning: false })
    backendRestart.mockResolvedValue({ success: true })
    await loadLifecycle()

    await crashAndRecover()
    await crashAndRecover()
    await crashAndRecover()
    expect(backendRestart).toHaveBeenCalledTimes(3)
    expect(modalError).not.toHaveBeenCalled()

    emitDisconnected()
    await vi.advanceTimersByTimeAsync(0)
    expect(backendRestart).toHaveBeenCalledTimes(3)
    expect(modalError).toHaveBeenCalledTimes(1)
  })

  it('间隔超过时间窗的偶发崩溃不累计', async () => {
    backendStatus.mockResolvedValue({ isRunning: false })
    backendRestart.mockResolvedValue({ success: true })
    await loadLifecycle()

    for (let i = 0; i < 5; i++) {
      await crashAndRecover()
      await vi.advanceTimersByTimeAsync(300000)
    }

    expect(backendRestart).toHaveBeenCalledTimes(5)
    expect(modalError).not.toHaveBeenCalled()
  })

  it('手动重连重新给满自动恢复次数', async () => {
    backendStatus.mockResolvedValue({ isRunning: false })
    backendRestart.mockResolvedValue({ success: true })
    const mod = await loadLifecycle()

    await crashAndRecover()
    await crashAndRecover()
    await crashAndRecover()
    await mod.manualReconnect()
    await crashAndRecover()

    expect(backendRestart).toHaveBeenCalledTimes(4)
    expect(modalError).not.toHaveBeenCalled()
  })
})

// ==================== #14 断线期间电源倒计时 ====================

describe('电源倒计时', () => {
  const COUNTDOWN = { operation: 'Shutdown', remaining: 42 }

  it('连接正常时推送停止 3 秒后清除弹窗', async () => {
    connectionStateRef.value = 'open'
    const mod = await loadLifecycle()
    const { powerCountdown, powerCountdownDisconnected } = mod.useAppLifecycle()

    pushMessage('power.countdown.updated', COUNTDOWN)
    expect(powerCountdown.value).toEqual(COUNTDOWN)

    await vi.advanceTimersByTimeAsync(3000)
    expect(powerCountdown.value).toBeNull()
    expect(powerCountdownDisconnected.value).toBe(false)
  })

  it('主连接断开时保留弹窗并标记连接中断，重新连上后由推送接管', async () => {
    connectionStateRef.value = 'open'
    const mod = await loadLifecycle()
    const { powerCountdown, powerCountdownDisconnected } = mod.useAppLifecycle()

    pushMessage('power.countdown.updated', COUNTDOWN)
    connectionStateRef.value = 'reconnecting'
    await vi.advanceTimersByTimeAsync(30000)

    // 断开期间一直保留，剩余秒数停在最后一次推送
    expect(powerCountdown.value).toEqual(COUNTDOWN)
    expect(powerCountdownDisconnected.value).toBe(true)

    connectionStateRef.value = 'open'
    pushMessage('power.countdown.updated', { operation: 'Shutdown', remaining: 10 })
    expect(powerCountdown.value).toEqual({ operation: 'Shutdown', remaining: 10 })
    expect(powerCountdownDisconnected.value).toBe(false)
  })

  it('断线期间经 HTTP 取消成功后本地立即关闭弹窗，不依赖收不到的取消事件', async () => {
    connectionStateRef.value = 'open'
    cancelPowerPost.mockResolvedValue({ code: 200 })
    const mod = await loadLifecycle()
    const { powerCountdown, powerCountdownDisconnected, cancelPowerCountdown } =
      mod.useAppLifecycle()

    pushMessage('power.countdown.updated', COUNTDOWN)
    connectionStateRef.value = 'reconnecting'
    await vi.advanceTimersByTimeAsync(6000)
    expect(powerCountdownDisconnected.value).toBe(true)

    await cancelPowerCountdown()
    expect(cancelPowerPost).toHaveBeenCalledTimes(1)
    expect(powerCountdown.value).toBeNull()
    expect(powerCountdownDisconnected.value).toBe(false)

    // 之后不会被残留的计时器重新标记
    await vi.advanceTimersByTimeAsync(10000)
    expect(powerCountdown.value).toBeNull()
    expect(powerCountdownDisconnected.value).toBe(false)
  })

  it('取消请求失败时保留弹窗并把错误抛给调用方', async () => {
    connectionStateRef.value = 'open'
    cancelPowerPost.mockRejectedValue(new Error('ECONNREFUSED'))
    const mod = await loadLifecycle()
    const { powerCountdown, cancelPowerCountdown } = mod.useAppLifecycle()

    pushMessage('power.countdown.updated', COUNTDOWN)
    await expect(cancelPowerCountdown()).rejects.toThrow('ECONNREFUSED')
    expect(powerCountdown.value).toEqual(COUNTDOWN)
  })

  it('重新连上后没有新推送时按正常时限清除，不永久残留', async () => {
    connectionStateRef.value = 'open'
    const mod = await loadLifecycle()
    const { powerCountdown, powerCountdownDisconnected } = mod.useAppLifecycle()

    pushMessage('power.countdown.updated', COUNTDOWN)
    connectionStateRef.value = 'reconnecting'
    await vi.advanceTimersByTimeAsync(6000)
    expect(powerCountdownDisconnected.value).toBe(true)

    connectionStateRef.value = 'open'
    await vi.advanceTimersByTimeAsync(3000)
    expect(powerCountdown.value).toBeNull()
    expect(powerCountdownDisconnected.value).toBe(false)
  })
})
