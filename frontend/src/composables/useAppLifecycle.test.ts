import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

type Envelope = { id: string; type: string; data: Record<string, unknown> }
type EnvelopeHandler = (message: Envelope) => void

const serviceMocks = vi.hoisted(() => ({
  close: vi.fn(),
}))

const closingMocks = vi.hoisted(() => ({
  showClosingOverlay: vi.fn(),
}))

const modalMocks = vi.hoisted(() => ({
  error: vi.fn(),
}))

const subscriptionMocks = vi.hoisted(() => ({
  handlers: new Map<string, EnvelopeHandler>(),
  subscribe: vi.fn(),
}))

const connectionMocks = vi.hoisted(() => ({
  connect: vi.fn(),
  stopReconnect: vi.fn(),
  scheduleReconnect: vi.fn(),
  send: vi.fn(),
  shutdown: vi.fn(),
  disconnectedHandlers: [] as Array<() => void>,
  reconnectFailedHandlers: [] as Array<() => void>,
  devMode: false,
  // 由 connection mock 工厂注入的连接状态 ref，供测试模拟连接成功（open）
  state: null as { value: string } | null,
}))

vi.mock('@/api', () => ({
  Service: {
    closeApiCoreClosePost: serviceMocks.close,
  },
}))

vi.mock('@/composables/useAppClosing', () => ({
  useAppClosing: () => ({
    showClosingOverlay: closingMocks.showClosingOverlay,
  }),
}))

vi.mock('ant-design-vue', () => ({
  Modal: { error: modalMocks.error },
}))

vi.mock('@/services/websocket/subscriptions', () => ({
  subscribe: subscriptionMocks.subscribe.mockImplementation(
    (key: { id?: string; type?: string }, handler: EnvelopeHandler) => {
      subscriptionMocks.handlers.set(`${key.id ?? '*'}\u0000${key.type ?? '*'}`, handler)
      return `sub_${subscriptionMocks.handlers.size}`
    }
  ),
}))

vi.mock('@/services/websocket/connection', async () => {
  const { ref } = await import('vue')
  const state = ref('idle')
  connectionMocks.state = state
  return {
    connect: connectionMocks.connect,
    connectionState: () => state,
    isBackendDevMode: () => connectionMocks.devMode,
    onDisconnected: (handler: () => void) => connectionMocks.disconnectedHandlers.push(handler),
    onReconnectCycleFailed: (handler: () => void) =>
      connectionMocks.reconnectFailedHandlers.push(handler),
    scheduleReconnect: connectionMocks.scheduleReconnect,
    send: connectionMocks.send,
    shutdown: connectionMocks.shutdown,
    stopReconnect: connectionMocks.stopReconnect,
  }
})

const logger = {
  debug: vi.fn(),
  info: vi.fn(),
  warn: vi.fn(),
  error: vi.fn(),
}

const electronMocks = {
  appQuit: vi.fn(),
  backendStatus: vi.fn(),
  killAllProcesses: vi.fn(),
  stopBackend: vi.fn(),
  startBackend: vi.fn(),
}

const emit = (type: string, data: Record<string, unknown> = {}): void => {
  const handler = subscriptionMocks.handlers.get(`Main\u0000${type}`)
  if (!handler) throw new Error(`missing lifecycle subscription for ${type}`)
  handler({ id: 'Main', type, data })
}

const loadLifecycle = async () => {
  vi.resetModules()
  const lifecycle = await import('./useAppLifecycle')
  lifecycle.initializeAppLifecycle()
  return lifecycle
}

describe('应用生命周期关闭与重启竞态', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.clearAllMocks()
    subscriptionMocks.handlers.clear()
    connectionMocks.disconnectedHandlers = []
    connectionMocks.reconnectFailedHandlers = []
    connectionMocks.devMode = false

    electronMocks.appQuit.mockResolvedValue(undefined)
    electronMocks.backendStatus.mockResolvedValue({ isRunning: false })
    electronMocks.killAllProcesses.mockResolvedValue({ success: true })
    electronMocks.stopBackend.mockResolvedValue({ success: true })
    electronMocks.startBackend.mockResolvedValue({ success: true })
    connectionMocks.connect.mockResolvedValue(true)
    connectionMocks.send.mockReturnValue(true)
    serviceMocks.close.mockResolvedValue({})

    vi.stubGlobal('window', {
      electronAPI: {
        getLogger: () => logger,
        appQuit: electronMocks.appQuit,
        backendStatus: electronMocks.backendStatus,
        killAllProcesses: electronMocks.killAllProcesses,
        stopBackend: electronMocks.stopBackend,
        startBackend: electronMocks.startBackend,
      },
      location: { reload: vi.fn() },
      setTimeout,
      clearTimeout,
    })
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('关闭请求单飞行，并在 ready 后才退出前端', async () => {
    const order: string[] = []
    electronMocks.backendStatus.mockImplementation(async () => {
      order.push('process-exited')
      return { isRunning: false }
    })
    electronMocks.appQuit.mockImplementation(async () => {
      order.push('app-quit')
    })
    serviceMocks.close.mockImplementation(async () => {
      order.push('post-close')
      emit('backend.shutdown.ready')
      order.push('ready-delivered')
      return {}
    })

    const lifecycle = await loadLifecycle()
    const first = lifecycle.closeApp()
    const second = lifecycle.closeApp()

    expect(second).toBe(first)
    await first

    expect(serviceMocks.close).toHaveBeenCalledTimes(1)
    expect(electronMocks.killAllProcesses).not.toHaveBeenCalled()
    expect(order).toEqual(['post-close', 'ready-delivered', 'process-exited', 'app-quit'])
  })

  it('ready 超时后只执行一次受控后端兜底停止', async () => {
    const lifecycle = await loadLifecycle()
    const closing = lifecycle.closeApp()

    await vi.advanceTimersByTimeAsync(10_000)
    await closing

    expect(serviceMocks.close).toHaveBeenCalledTimes(1)
    expect(electronMocks.killAllProcesses).toHaveBeenCalledTimes(1)
    expect(electronMocks.appQuit).toHaveBeenCalledTimes(1)
  })

  it('开发模式收到 ready 后不停止开发者管理的后端', async () => {
    connectionMocks.devMode = true
    serviceMocks.close.mockImplementation(async () => {
      emit('backend.shutdown.ready')
      return {}
    })

    const lifecycle = await loadLifecycle()
    await lifecycle.closeApp()

    expect(electronMocks.backendStatus).not.toHaveBeenCalled()
    expect(electronMocks.killAllProcesses).not.toHaveBeenCalled()
    expect(electronMocks.appQuit).toHaveBeenCalledTimes(1)
  })

  it('后端主动关闭前端时不重复 POST、重启或强杀后端', async () => {
    await loadLifecycle()
    emit('frontend.close.requested')
    await Promise.resolve()
    await Promise.resolve()

    expect(serviceMocks.close).not.toHaveBeenCalled()
    expect(electronMocks.stopBackend).not.toHaveBeenCalled()
    expect(electronMocks.startBackend).not.toHaveBeenCalled()
    expect(electronMocks.killAllProcesses).not.toHaveBeenCalled()
    expect(electronMocks.appQuit).toHaveBeenCalledTimes(1)
  })

  it('重连状态查询期间开始关闭时，不再启动后端或安排重连', async () => {
    let resolveReconnectProbe!: (value: { isRunning: boolean }) => void
    const reconnectProbe = new Promise<{ isRunning: boolean }>(resolve => {
      resolveReconnectProbe = resolve
    })
    electronMocks.backendStatus
      .mockImplementationOnce(() => reconnectProbe)
      .mockResolvedValue({ isRunning: false })
    serviceMocks.close.mockImplementation(async () => {
      emit('backend.shutdown.ready')
      return {}
    })

    const lifecycle = await loadLifecycle()
    connectionMocks.reconnectFailedHandlers[0]?.()
    await Promise.resolve()

    const closing = lifecycle.closeApp()
    resolveReconnectProbe({ isRunning: false })
    await closing
    await Promise.resolve()

    expect(electronMocks.stopBackend).not.toHaveBeenCalled()
    expect(electronMocks.startBackend).not.toHaveBeenCalled()
    expect(connectionMocks.scheduleReconnect).not.toHaveBeenCalled()
  })

  it('关闭期间连接先断开会立即走兜底，不等待完整超时', async () => {
    const lifecycle = await loadLifecycle()
    const closing = lifecycle.closeApp()
    connectionMocks.disconnectedHandlers[0]?.()
    await closing

    expect(electronMocks.killAllProcesses).toHaveBeenCalledTimes(1)
    expect(electronMocks.appQuit).toHaveBeenCalledTimes(1)
  })
  it('后端重启成功后使用 force 重新连接，可恢复 suspended 传输状态', async () => {
    const lifecycle = await loadLifecycle()
    const restarting = lifecycle.restartBackendManually()

    await vi.advanceTimersByTimeAsync(2_000)
    await restarting

    expect(electronMocks.stopBackend).toHaveBeenCalledTimes(1)
    expect(electronMocks.startBackend).toHaveBeenCalledTimes(1)
    expect(connectionMocks.connect).toHaveBeenCalledWith({ force: true })
  })
})
