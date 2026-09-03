import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// ==================== 全局桩 ====================

const logger = { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() }

class FakeWebSocket {
  static readonly CONNECTING = 0
  static readonly OPEN = 1
  static readonly CLOSING = 2
  static readonly CLOSED = 3
  static instances: FakeWebSocket[] = []

  readyState = FakeWebSocket.CONNECTING
  url: string
  onopen: (() => void) | null = null
  onclose: ((ev: { code: number; reason: string }) => void) | null = null
  onmessage: ((ev: { data: string }) => void) | null = null
  onerror: (() => void) | null = null

  constructor(url: string) {
    this.url = url
    FakeWebSocket.instances.push(this)
  }

  triggerOpen() {
    this.readyState = FakeWebSocket.OPEN
    this.onopen?.()
  }

  triggerClose(code = 1000, reason = '') {
    this.readyState = FakeWebSocket.CLOSED
    this.onclose?.({ code, reason })
  }

  send = vi.fn()

  close(code = 1000, reason = '') {
    if (this.readyState === FakeWebSocket.CLOSED) return
    this.readyState = FakeWebSocket.CLOSED
    this.onclose?.({ code, reason })
  }
}

vi.mock('@/api', () => ({
  OpenAPI: { BASE: 'http://localhost:36163' },
}))

vi.mock('./subscriptions', () => ({
  dispatchMessage: vi.fn(() => true),
  subscribe: vi.fn(() => 'sub_1'),
  unsubscribe: vi.fn(),
}))

const loadConnection = async () => {
  vi.resetModules()
  FakeWebSocket.instances = []
  return await import('./connection')
}

const latestSocket = () => FakeWebSocket.instances.at(-1)!

describe('websocket connection 状态机', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.stubGlobal('WebSocket', FakeWebSocket)
    vi.stubGlobal('window', {
      electronAPI: { getLogger: () => logger },
      location: { hostname: 'localhost' },
      setTimeout: (fn: () => void, ms?: number) => setTimeout(fn, ms),
      clearTimeout: (id: number) => clearTimeout(id),
    })
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: true,
        status: 200,
        json: async () => ({ devMode: false, wsPath: '/api/core/ws' }),
      }))
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('connect 成功后进入 open 且退避计数清零', async () => {
    const conn = await loadConnection()
    const promise = conn.connect()
    await vi.waitFor(() => expect(FakeWebSocket.instances.length).toBe(1))
    latestSocket().triggerOpen()

    await expect(promise).resolves.toBe(true)
    expect(conn.connectionState().value).toBe('open')
  })

  it('并发 connect 只建立一个连接尝试（单飞行）', async () => {
    const conn = await loadConnection()
    const p1 = conn.connect()
    const p2 = conn.connect()
    await vi.waitFor(() => expect(FakeWebSocket.instances.length).toBe(1))
    latestSocket().triggerOpen()

    await Promise.all([p1, p2])
    expect(FakeWebSocket.instances.length).toBe(1)
  })

  it('已连接时 connect 直接返回 true 不重复建连', async () => {
    const conn = await loadConnection()
    const p = conn.connect()
    await vi.waitFor(() => expect(FakeWebSocket.instances.length).toBe(1))
    latestSocket().triggerOpen()
    await p

    await expect(conn.connect()).resolves.toBe(true)
    expect(FakeWebSocket.instances.length).toBe(1)
  })

  it('shutdown 后进入 closed 且拒绝新的 connect', async () => {
    const conn = await loadConnection()
    const p = conn.connect()
    await vi.waitFor(() => expect(FakeWebSocket.instances.length).toBe(1))
    latestSocket().triggerOpen()
    await p

    conn.shutdown('测试关闭')
    expect(conn.connectionState().value).toBe('closed')
    await expect(conn.connect()).resolves.toBe(false)
    // 拒绝的连接不新建 WebSocket
    expect(FakeWebSocket.instances.length).toBe(1)
  })

  it('协商期间 shutdown 使在途连接尝试失效，不复活状态', async () => {
    let releaseFetch: (() => void) | null = null
    vi.stubGlobal(
      'fetch',
      vi.fn(
        () =>
          new Promise(resolve => {
            releaseFetch = () =>
              resolve({
                ok: true,
                status: 200,
                json: async () => ({ devMode: false, wsPath: '/api/core/ws' }),
              })
          })
      )
    )
    const conn = await loadConnection()
    const promise = conn.connect() // 卡在协商 fetch

    conn.shutdown('协商期间关闭') // 代次递增 + closed
    releaseFetch!() // 协商完成，旧协程恢复

    await expect(promise).resolves.toBe(false)
    // 不创建 WebSocket，状态保持 closed（未被 onopen 复活）
    expect(FakeWebSocket.instances.length).toBe(0)
    expect(conn.connectionState().value).toBe('closed')
  })

  it('send 未连接返回 false，连接后返回 true', async () => {
    const conn = await loadConnection()
    expect(conn.send('Main', 'x', {})).toBe(false)

    const p = conn.connect()
    await vi.waitFor(() => expect(FakeWebSocket.instances.length).toBe(1))
    latestSocket().triggerOpen()
    await p

    expect(conn.send('Main', 'x', { a: 1 })).toBe(true)
    expect(latestSocket().send).toHaveBeenCalledWith(
      JSON.stringify({ id: 'Main', type: 'x', data: { a: 1 } })
    )
  })

  it('连接断开触发断开监听并进入 reconnecting', async () => {
    const conn = await loadConnection()
    const onDisc = vi.fn()
    conn.onDisconnected(onDisc)

    const p = conn.connect()
    await vi.waitFor(() => expect(FakeWebSocket.instances.length).toBe(1))
    latestSocket().triggerOpen()
    await p

    latestSocket().triggerClose(1006, '异常断开')
    expect(onDisc).toHaveBeenCalledWith({ code: 1006, reason: '异常断开' })
    expect(conn.connectionState().value).toBe('reconnecting')
    // 普通异常断开照常安排自动重连
    expect(conn.connectionInfo()).toMatchObject({
      hasReconnectTimer: true,
      automaticReconnectEnabled: true,
    })

    conn.stopReconnect()
    conn.shutdown()
  })

  it('收到被替换关闭码进入 superseded 终态：通知监听但不自动重连，显式 connect 仍可接管', async () => {
    const conn = await loadConnection()
    const onDisc = vi.fn()
    const onCycleFailed = vi.fn()
    conn.onDisconnected(onDisc)
    conn.onReconnectCycleFailed(onCycleFailed)

    const p = conn.connect()
    await vi.waitFor(() => expect(FakeWebSocket.instances.length).toBe(1))
    latestSocket().triggerOpen()
    await p

    latestSocket().triggerClose(4001, 'replaced-by-new-connection')
    expect(onDisc).toHaveBeenCalledWith({ code: 4001, reason: 'replaced-by-new-connection' })
    expect(conn.connectionState().value).toBe('superseded')
    expect(conn.connectionInfo()).toMatchObject({
      hasReconnectTimer: false,
      automaticReconnectEnabled: false,
      reconnectAttempts: 0,
    })
    expect(onCycleFailed).not.toHaveBeenCalled()

    // 协调器安排的自动重连在 superseded 下也不生效
    conn.scheduleReconnect(0)
    expect(conn.connectionState().value).toBe('superseded')
    expect(conn.connectionInfo()).toMatchObject({ hasReconnectTimer: false })
    await new Promise(resolve => setTimeout(resolve, 10))
    expect(FakeWebSocket.instances.length).toBe(1)

    // 显式 connect 允许本窗口重新接管
    const p2 = conn.connect()
    await vi.waitFor(() => expect(FakeWebSocket.instances.length).toBe(2))
    latestSocket().triggerOpen()
    await expect(p2).resolves.toBe(true)
    expect(conn.connectionState().value).toBe('open')

    conn.shutdown()
  })

  it('自己 reconnectNow 后旧连接收到被替换关闭码不影响当前连接', async () => {
    const conn = await loadConnection()
    const onDisc = vi.fn()
    conn.onDisconnected(onDisc)

    const p = conn.connect()
    await vi.waitFor(() => expect(FakeWebSocket.instances.length).toBe(1))
    const oldSocket = latestSocket()
    oldSocket.triggerOpen()
    await p

    const p2 = conn.reconnectNow('测试重连')
    await vi.waitFor(() => expect(FakeWebSocket.instances.length).toBe(2))
    const newSocket = latestSocket()
    expect(newSocket).not.toBe(oldSocket)

    // 新连接在后端把旧连接顶掉：旧 socket 的 close 事件带被替换码，但已不是当前 socket
    oldSocket.triggerClose(4001, 'replaced-by-new-connection')
    expect(onDisc).not.toHaveBeenCalledWith(expect.objectContaining({ code: 4001 }))
    expect(conn.connectionState().value).not.toBe('superseded')

    newSocket.triggerOpen()
    await expect(p2).resolves.toBe(true)
    expect(conn.connectionState().value).toBe('open')

    conn.shutdown()
  })

  it('shutdown 后收到被替换关闭码保持 closed 终态', async () => {
    const conn = await loadConnection()
    const onDisc = vi.fn()
    conn.onDisconnected(onDisc)

    const p = conn.connect()
    await vi.waitFor(() => expect(FakeWebSocket.instances.length).toBe(1))
    const ws = latestSocket()
    ws.triggerOpen()
    await p

    conn.shutdown('应用关闭')
    ws.triggerClose(4001, 'replaced-by-new-connection')
    expect(conn.connectionState().value).toBe('closed')
    expect(onDisc).not.toHaveBeenCalled()
  })
})
