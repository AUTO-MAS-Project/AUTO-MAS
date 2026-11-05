import { afterEach, beforeEach, describe, expect, it, vi } from 'vite-plus/test'

import { type WSDisconnectEvent, type WSJsonObject } from '@/services/websocket/types'

// ==================== 全局桩 ====================

const logger = { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() }

const closePost = vi.fn()
const backendStatus = vi.fn()
const stopBackend = vi.fn()
const killAllProcesses = vi.fn()
const appQuit = vi.fn()
const backendRestart = vi.fn()
const systemResume = vi.fn((_handler: () => void) => () => undefined)

const connectionMocks = vi.hoisted(() => ({
  connect: vi.fn(async () => true),
  connectionState: vi.fn(() => ({ value: 'open' })),
  onConnected: vi.fn(() => () => undefined),
  onDisconnected: vi.fn((_handler: (event: WSDisconnectEvent) => void) => () => undefined),
  onReconnectCycleFailed: vi.fn((_handler: () => void) => () => undefined),
  reconnectNow: vi.fn(async () => true),
  scheduleReconnect: vi.fn(),
  shutdown: vi.fn(),
  stopReconnect: vi.fn(),
}))

// 常驻订阅按消息类型记下处理函数，测试里据此模拟后端推送。
type Handler = (message: { id: string; type: string; data: WSJsonObject }) => void
const subscriptionHandlers = vi.hoisted(() => new Map<string, Handler>())
const subscriptionMocks = vi.hoisted(() => ({
  subscribe: vi.fn(),
  unsubscribe: vi.fn(),
}))

vi.mock('@/i18n', () => ({ translate: (key: string) => key }))
vi.mock('ant-design-vue', () => ({
  Modal: { error: vi.fn(), warning: vi.fn(() => ({ destroy: vi.fn() })) },
  // 断开提示走非阻塞 notification，关闭流程用例本身不断言它，但协调器会调用
  notification: { warning: vi.fn(), info: vi.fn(), close: vi.fn() },
}))
vi.mock('@/api', () => ({
  Service: {
    closeApiCoreClosePost: closePost,
    getWsMetaApiCoreWsMetaGet: vi.fn(async () => ({ devMode: false })),
  },
}))
vi.mock('@/composables/useAppClosing', () => ({
  useAppClosing: () => ({ showClosingOverlay: vi.fn(), hideClosingOverlay: vi.fn() }),
}))
vi.mock('@/services/realtimeSnapshotApi', () => ({
  realtimeSnapshotApi: { getPowerCountdown: vi.fn(async () => ({ active: false })) },
}))
vi.mock('@/services/websocket/residentResources', () => ({
  bootstrapResidentResources: vi.fn(),
  disposeResidentResources: vi.fn(),
}))
vi.mock('@/services/websocket/connection', () => connectionMocks)
vi.mock('@/services/websocket/subscriptions', () => subscriptionMocks)

const loadLifecycle = async () => {
  vi.resetModules()
  const module = await import('./useAppLifecycle')
  module.initializeAppLifecycle()
  return module
}

const callOrder = (fn: { mock: { invocationCallOrder: number[] } }): number =>
  fn.mock.invocationCallOrder[0]

describe('useAppLifecycle 关闭流程', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    subscriptionHandlers.clear()
    subscriptionMocks.subscribe.mockImplementation(
      (filter: { id: string; type: string }, handler: Handler) => {
        subscriptionHandlers.set(filter.type, handler)
        return `sub_${filter.type}`
      }
    )
    connectionMocks.connectionState.mockReturnValue({ value: 'open' })
    closePost.mockResolvedValue(undefined)
    stopBackend.mockResolvedValue({ success: true })
    killAllProcesses.mockResolvedValue({ success: true })
    appQuit.mockResolvedValue(undefined)
    vi.stubGlobal('window', {
      electronAPI: {
        getLogger: () => logger,
        backendStatus,
        stopBackend,
        killAllProcesses,
        appQuit,
        backendRestart,
        onSystemResume: systemResume,
        onAppCloseRequested: vi.fn(() => () => undefined),
      },
      setTimeout: (fn: () => void, ms?: number) => setTimeout(fn, ms),
      clearTimeout: (id: number) => clearTimeout(id),
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  describe('Runtime 监督链路', () => {
    beforeEach(() => {
      backendStatus.mockResolvedValue({ isRunning: true, runtimeSupervised: true })
    })

    it('不发 POST /close、不等后端进程消失，只请求 Electron 经 Runtime 关闭后再退出', async () => {
      // 页面先于后端起来时 ws_meta 可能回退成 devMode=true；Runtime 链路下它不能左右关闭方式。
      const { closeApp } = await loadLifecycle()

      await closeApp()

      expect(closePost).not.toHaveBeenCalled()
      expect(killAllProcesses).not.toHaveBeenCalled()
      expect(stopBackend).toHaveBeenCalledTimes(1)
      expect(appQuit).toHaveBeenCalledTimes(1)
      // Electron 始终由 Runtime 关闭，不依赖状态 IPC 成功或 ws_meta 的开发标记。
      expect(backendStatus).not.toHaveBeenCalled()
      expect(connectionMocks.stopReconnect).toHaveBeenCalled()
      expect(connectionMocks.shutdown).toHaveBeenCalledWith('应用关闭')
      // 先收连接，再让 Runtime 关后端，最后退前端。
      expect(callOrder(connectionMocks.shutdown)).toBeLessThan(callOrder(stopBackend))
      expect(callOrder(stopBackend)).toBeLessThan(callOrder(appQuit))
    })

    it('Electron 未能确认后端关闭时保留前端，交给主进程最终兜底', async () => {
      stopBackend.mockResolvedValue({ success: false, error: 'Runtime 关闭后端失败' })
      const { closeApp } = await loadLifecycle()

      await closeApp()

      expect(stopBackend).toHaveBeenCalledTimes(1)
      expect(appQuit).not.toHaveBeenCalled()
      expect(killAllProcesses).not.toHaveBeenCalled()
      expect(closePost).not.toHaveBeenCalled()
    })
  })

  it('状态 IPC 失败时仍经 Runtime 关闭，不能改发后端 close 请求', async () => {
    backendStatus.mockRejectedValue(new Error('IPC unavailable'))
    const { closeApp } = await loadLifecycle()
    await closeApp()
    expect(stopBackend).toHaveBeenCalledOnce()
    expect(closePost).not.toHaveBeenCalled()
    expect(killAllProcesses).not.toHaveBeenCalled()
    expect(appQuit).toHaveBeenCalledOnce()
  })

  describe.each(['browser', 'desktop'] as const)('%s 只连接外部后端', surface => {
    beforeEach(() => {
      Object.assign(
        window,
        surface === 'browser'
          ? { __AUTO_MAS_BROWSER_DEV_MODE__: true }
          : { backendOwnership: 'external' }
      )
    })

    it.each(['open', 'closed'])('%s 时退出只断开连接，保留后端任务', async state => {
      connectionMocks.connectionState.mockReturnValue({ value: state })
      const { closeApp } = await loadLifecycle()
      await closeApp()
      expect(closePost).not.toHaveBeenCalled()
      expect(stopBackend).not.toHaveBeenCalled()
      expect(killAllProcesses).not.toHaveBeenCalled()
      expect(connectionMocks.shutdown).toHaveBeenCalled()
      expect(appQuit).toHaveBeenCalledOnce()
    })
  })
})
