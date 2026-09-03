import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

// ==================== 全局桩 ====================

const logger = { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() }

const modalWarning = vi.fn()
const modalError = vi.fn()
const modalDestroy = vi.fn()
const notificationWarning = vi.fn()
const notificationClose = vi.fn()

vi.mock('ant-design-vue', () => ({
  Modal: {
    warning: (...args: unknown[]) => {
      modalWarning(...args)
      return { destroy: modalDestroy }
    },
    error: (...args: unknown[]) => modalError(...args),
  },
  notification: {
    warning: (...args: unknown[]) => notificationWarning(...args),
    close: (...args: unknown[]) => notificationClose(...args),
  },
}))

vi.mock('@/i18n', () => ({ translate: (key: string) => key }))

vi.mock('@/api', () => ({
  Service: {
    closeApiCoreClosePost: vi.fn(async () => ({})),
    getWsMetaApiCoreWsMetaGet: vi.fn(async () => ({})),
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

vi.mock('@/services/websocket/subscriptions', () => ({
  subscribe: vi.fn(() => 'sub_1'),
  unsubscribe: vi.fn(),
}))

// 连接层桩：捕获生命周期协调器注册的监听器，由测试直接触发
type DisconnectListener = (event: { code: number; reason: string }) => void
const listeners: {
  connected: Array<() => void | Promise<void>>
  disconnected: DisconnectListener[]
  cycleFailed: Array<() => void>
} = { connected: [], disconnected: [], cycleFailed: [] }
let devMode = false
const connectionStateRef = ref<'idle' | 'open' | 'closed'>('idle')

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
  reconnectNow: vi.fn(async () => true),
  scheduleReconnect: vi.fn(),
  shutdown: vi.fn(),
  stopReconnect: vi.fn(),
}))

const DISCONNECT_EVENT = { code: 1006, reason: '' }

const loadLifecycle = async () => {
  vi.resetModules()
  listeners.connected = []
  listeners.disconnected = []
  listeners.cycleFailed = []
  const mod = await import('./useAppLifecycle')
  mod.initializeAppLifecycle()
  return mod
}

const emitDisconnected = () => listeners.disconnected.forEach(l => l(DISCONNECT_EVENT))
const emitConnected = async () => {
  await Promise.all(listeners.connected.map(l => l()))
}
const emitCycleFailed = async () => {
  listeners.cycleFailed.forEach(l => l())
  // handleReconnectCycleFailed 内部先 await 进程状态查询再决策，等微任务队列排空
  await new Promise(resolve => setTimeout(resolve, 0))
}

describe('useAppLifecycle 断开提示', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    devMode = false
    connectionStateRef.value = 'idle'
    vi.stubGlobal('window', {
      electronAPI: {
        getLogger: () => logger,
        backendStatus: vi.fn(async () => ({ isRunning: true })),
      },
      setTimeout: (fn: () => void, ms?: number) => setTimeout(fn, ms),
      clearTimeout: (id: number) => clearTimeout(id),
    })
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('开发模式断开只出非阻塞通知，不出模态框，重连成功后按 key 收起', async () => {
    devMode = true
    await loadLifecycle()

    emitDisconnected()
    expect(notificationWarning).toHaveBeenCalledTimes(1)
    expect(notificationWarning.mock.calls[0][0]).toMatchObject({
      key: 'app-lifecycle-disconnect',
      message: 'misc.lostConnectionBackend',
      description: 'misc.devBackendReconnecting',
      duration: null,
    })
    expect(modalWarning).not.toHaveBeenCalled()

    // 同一次断开重复触发不再重复提示；一轮重连失败在开发模式下也不升级
    emitDisconnected()
    await emitCycleFailed()
    expect(notificationWarning).toHaveBeenCalledTimes(1)
    expect(modalWarning).not.toHaveBeenCalled()

    await emitConnected()
    expect(notificationClose).toHaveBeenCalledWith('app-lifecycle-disconnect')

    // 重连成功后再次断开属于新的一次事故，允许再次提示
    emitDisconnected()
    expect(notificationWarning).toHaveBeenCalledTimes(2)
    expect(modalWarning).not.toHaveBeenCalled()
  })

  it('生产模式首次断开不出模态框，一轮重连失败后才升级并只升级一次', async () => {
    await loadLifecycle()

    emitDisconnected()
    expect(notificationWarning).toHaveBeenCalledTimes(1)
    expect(notificationWarning.mock.calls[0][0]).toMatchObject({
      description: 'misc.checkingBackendRecoveringAutomatically',
    })
    expect(modalWarning).not.toHaveBeenCalled()

    await emitCycleFailed()
    expect(modalWarning).toHaveBeenCalledTimes(1)
    expect(modalWarning.mock.calls[0][0]).toMatchObject({
      title: 'misc.lostConnectionBackend',
      content: 'misc.checkingBackendRecoveringAutomatically',
      okText: 'misc.gotIt',
    })
    // 升级时先收起非阻塞通知，不让两者叠在一起
    expect(notificationClose).toHaveBeenCalledWith('app-lifecycle-disconnect')

    await emitCycleFailed()
    expect(modalWarning).toHaveBeenCalledTimes(1)

    await emitConnected()
    expect(modalDestroy).toHaveBeenCalledTimes(1)
  })

  it('生产模式下没有断开事件的重连周期失败不弹模态框', async () => {
    await loadLifecycle()

    await emitCycleFailed()
    expect(modalWarning).not.toHaveBeenCalled()
    expect(notificationWarning).not.toHaveBeenCalled()
  })

  it('关闭流程期间断开与重连周期失败都不提示', async () => {
    vi.useFakeTimers()
    const mod = await loadLifecycle()

    // 不等待关闭流程完成（它会等 backend.shutdown.ready 或超时），只需进入关闭态
    void mod.closeApp()
    await Promise.resolve()

    emitDisconnected()
    listeners.cycleFailed.forEach(l => l())
    await Promise.resolve()

    expect(notificationWarning).not.toHaveBeenCalled()
    expect(modalWarning).not.toHaveBeenCalled()
    expect(modalError).not.toHaveBeenCalled()
  })
})
