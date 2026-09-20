import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  WS_BACKEND_SHUTDOWN_READY,
  WS_FRONTEND_CLOSE_REQUESTED,
  type WSJsonObject,
} from '@/services/websocket/types'

// ==================== 全局桩 ====================

const logger = { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() }

const closePost = vi.fn()
const backendStatus = vi.fn()
const stopBackend = vi.fn()
const killAllProcesses = vi.fn()
const appQuit = vi.fn()

const connectionMocks = vi.hoisted(() => ({
  connect: vi.fn(async () => true),
  connectionState: vi.fn(() => ({ value: 'open' })),
  isBackendDevMode: vi.fn(() => false),
  onConnected: vi.fn(() => () => undefined),
  onDisconnected: vi.fn(() => () => undefined),
  onReconnectCycleFailed: vi.fn(() => () => undefined),
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

const pushMessage = (type: string): void => {
  const handler = subscriptionHandlers.get(type)
  if (!handler) throw new Error(`未注册常驻订阅: ${type}`)
  handler({ id: 'Main', type, data: {} })
}

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
    connectionMocks.isBackendDevMode.mockReturnValue(false)
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
        onSystemResume: vi.fn(() => () => undefined),
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
      connectionMocks.isBackendDevMode.mockReturnValue(true)
      const { closeApp } = await loadLifecycle()

      await closeApp()

      expect(closePost).not.toHaveBeenCalled()
      expect(killAllProcesses).not.toHaveBeenCalled()
      expect(stopBackend).toHaveBeenCalledTimes(1)
      expect(appQuit).toHaveBeenCalledTimes(1)
      // Runtime 存活期间 isRunning 恒为 true：关闭流程只能查一次链路，不能轮询等它变 false。
      expect(backendStatus).toHaveBeenCalledTimes(1)
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

    it('后端主动请求前端关闭时同样经 Runtime 收口，避免后端自行退出后被 Runtime 重启', async () => {
      const { closeApp } = await loadLifecycle()

      pushMessage(WS_FRONTEND_CLOSE_REQUESTED)
      // closeApp 返回在途的关闭流程
      await closeApp()

      expect(closePost).not.toHaveBeenCalled()
      expect(stopBackend).toHaveBeenCalledTimes(1)
      expect(appQuit).toHaveBeenCalledTimes(1)
      expect(callOrder(stopBackend)).toBeLessThan(callOrder(appQuit))
    })
  })

  describe('旧链路（AUTO_MAS_RUNTIME_MODE=off）', () => {
    it('仍由渲染进程 POST /close、等 ready 与进程退出，不经 Runtime 停止', async () => {
      backendStatus.mockResolvedValue({ isRunning: true, runtimeSupervised: false })
      closePost.mockImplementation(async () => {
        // 后端清理完成后广播 ready，随后进程退出
        pushMessage(WS_BACKEND_SHUTDOWN_READY)
        backendStatus.mockResolvedValue({ isRunning: false, runtimeSupervised: false })
      })
      const { closeApp } = await loadLifecycle()

      await closeApp()

      expect(closePost).toHaveBeenCalledTimes(1)
      expect(stopBackend).not.toHaveBeenCalled()
      expect(killAllProcesses).not.toHaveBeenCalled()
      expect(appQuit).toHaveBeenCalledTimes(1)
      expect(connectionMocks.shutdown).toHaveBeenCalledWith('应用关闭')
      // 先 POST /close 收 ready，再确认进程退出，最后才收连接、退前端。
      expect(callOrder(closePost)).toBeLessThan(callOrder(connectionMocks.shutdown))
      expect(callOrder(connectionMocks.shutdown)).toBeLessThan(callOrder(appQuit))
    })

    it('开发模式后端收到 ready 即直接退出前端，不 taskkill、不经 Runtime', async () => {
      connectionMocks.isBackendDevMode.mockReturnValue(true)
      backendStatus.mockResolvedValue({ isRunning: true, runtimeSupervised: false })
      closePost.mockImplementation(async () => {
        pushMessage(WS_BACKEND_SHUTDOWN_READY)
      })
      const { closeApp } = await loadLifecycle()

      await closeApp()

      expect(closePost).toHaveBeenCalledTimes(1)
      expect(stopBackend).not.toHaveBeenCalled()
      expect(killAllProcesses).not.toHaveBeenCalled()
      expect(appQuit).toHaveBeenCalledTimes(1)
    })

    it('后端主动请求前端关闭时直接退出，不再停止后端', async () => {
      backendStatus.mockResolvedValue({ isRunning: true, runtimeSupervised: false })
      const { closeApp } = await loadLifecycle()

      pushMessage(WS_FRONTEND_CLOSE_REQUESTED)
      await closeApp()

      expect(closePost).not.toHaveBeenCalled()
      expect(stopBackend).not.toHaveBeenCalled()
      expect(killAllProcesses).not.toHaveBeenCalled()
      expect(appQuit).toHaveBeenCalledTimes(1)
    })

    it('查询链路的 IPC 失败时按旧链路处理', async () => {
      backendStatus.mockRejectedValueOnce(new Error('IPC 不可用'))
      backendStatus.mockResolvedValue({ isRunning: false, runtimeSupervised: false })
      closePost.mockImplementation(async () => {
        pushMessage(WS_BACKEND_SHUTDOWN_READY)
      })
      const { closeApp } = await loadLifecycle()

      await closeApp()

      expect(closePost).toHaveBeenCalledTimes(1)
      expect(stopBackend).not.toHaveBeenCalled()
      expect(appQuit).toHaveBeenCalledTimes(1)
    })
  })
})
