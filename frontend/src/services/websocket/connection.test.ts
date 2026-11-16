import { afterEach, beforeEach, describe, expect, it, vi } from 'vite-plus/test'

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
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('协商期间 shutdown 使在途连接尝试失效，不复活状态', async () => {
    vi.useFakeTimers()
    const conn = await loadConnection()
    const disconnected = vi.fn()
    conn.onDisconnected(disconnected)
    const connecting = conn.connect()
    const concurrent = conn.connect()
    await vi.advanceTimersByTimeAsync(0)
    expect(FakeWebSocket.instances).toHaveLength(1)
    latestSocket().triggerOpen()
    await expect(Promise.all([connecting, concurrent])).resolves.toEqual([true, true])

    latestSocket().triggerClose(4001, 'replaced-by-new-connection')
    expect(disconnected).toHaveBeenCalledExactlyOnceWith({
      code: 4001,
      reason: 'replaced-by-new-connection',
    })
    expect(conn.connectionState().value).toBe('superseded')
    conn.scheduleReconnect(0)
    await vi.advanceTimersByTimeAsync(60_000)
    expect(FakeWebSocket.instances).toHaveLength(1)
    expect(conn.connectionState().value).toBe('superseded')

    const takeover = conn.connect()
    await vi.advanceTimersByTimeAsync(0)
    expect(FakeWebSocket.instances).toHaveLength(2)
    const oldSocket = latestSocket()
    oldSocket.triggerOpen()
    await expect(takeover).resolves.toBe(true)

    const reconnecting = conn.reconnectNow('测试重连')
    await vi.advanceTimersByTimeAsync(0)
    expect(FakeWebSocket.instances).toHaveLength(3)
    oldSocket.triggerClose(4001, 'replaced-by-new-connection')
    latestSocket().triggerOpen()
    await expect(reconnecting).resolves.toBe(true)
    expect(disconnected).toHaveBeenCalledTimes(1)
    expect(conn.connectionState().value).toBe('open')

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
    const promise = conn.reconnectNow('协商期间关闭')
    const duplicate = conn.connect()

    conn.shutdown('协商期间关闭')
    releaseFetch!()

    await expect(Promise.all([promise, duplicate])).resolves.toEqual([false, false])
    await vi.advanceTimersByTimeAsync(60_000)
    expect(FakeWebSocket.instances).toHaveLength(3)
    expect(conn.connectionState().value).toBe('closed')
    await expect(conn.connect()).resolves.toBe(false)
  })
})
