import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// ==================== 全局桩 ====================

const websocketAuthMocks = vi.hoisted(() => ({
  fetchAuthenticatedWebSocketHandshake: vi.fn(),
}))

const subscriptionMocks = vi.hoisted(() => ({
  dispatchMessage: vi.fn(() => true),
  subscribe: vi.fn(
    (_filter: { id?: string; type: string }, _handler: (message: any) => void) => 'sub_1'
  ),
  unsubscribe: vi.fn(),
}))

vi.mock('@/utils/websocketAuth', () => websocketAuthMocks)

const logger = { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() }

class FakeWebSocket {
  static readonly CONNECTING = 0
  static readonly OPEN = 1
  static readonly CLOSING = 2
  static readonly CLOSED = 3
  static instances: FakeWebSocket[] = []

  readyState = FakeWebSocket.CONNECTING
  url: string
  protocols?: string | string[]
  onopen: (() => void) | null = null
  onclose: ((ev: { code: number; reason: string }) => void) | null = null
  onmessage: ((ev: { data: string }) => void) | null = null
  onerror: (() => void) | null = null

  constructor(url: string, protocols?: string | string[]) {
    this.url = url
    this.protocols = protocols
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

vi.mock('./subscriptions', () => subscriptionMocks)

const loadConnection = async () => {
  vi.resetModules()
  FakeWebSocket.instances = []
  return await import('./connection')
}

const latestSocket = () => FakeWebSocket.instances.at(-1)!

describe('websocket connection 状态机', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    websocketAuthMocks.fetchAuthenticatedWebSocketHandshake.mockResolvedValue({
      authProtocol: 'auto-mas-auth.test-token',
      devMode: false,
      wsPath: '/api/core/ws',
    })
    vi.stubGlobal('WebSocket', FakeWebSocket)
    vi.stubGlobal('window', {
      electronAPI: { getLogger: () => logger },
      location: { hostname: 'localhost' },
      setTimeout: (fn: () => void, ms?: number) => setTimeout(fn, ms),
      clearTimeout: (id: number) => clearTimeout(id),
    })
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
    expect(latestSocket().protocols).toBe('auto-mas-auth.test-token')
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
    let releaseHandshake: (() => void) | null = null
    websocketAuthMocks.fetchAuthenticatedWebSocketHandshake.mockImplementationOnce(
      () =>
        new Promise(resolve => {
          releaseHandshake = () =>
            resolve({
              authProtocol: 'auto-mas-auth.test-token',
              devMode: false,
              wsPath: '/api/core/ws',
            })
        })
    )
    const conn = await loadConnection()
    const promise = conn.connect() // 卡在认证协商

    conn.shutdown('协商期间关闭') // 代次递增 + closed
    releaseHandshake!() // 协商完成，旧协程恢复

    await expect(promise).resolves.toBe(false)
    // 不创建 WebSocket，状态保持 closed（未被 onopen 复活）
    expect(FakeWebSocket.instances.length).toBe(0)
    expect(conn.connectionState().value).toBe('closed')
  })

  it('认证协商失败时绝不创建未认证连接', async () => {
    websocketAuthMocks.fetchAuthenticatedWebSocketHandshake.mockRejectedValueOnce(
      new Error('missing token')
    )
    const conn = await loadConnection()

    await expect(conn.connect()).resolves.toBe(false)
    expect(FakeWebSocket.instances).toHaveLength(0)
    expect(conn.connectionState().value).toBe('reconnecting')

    conn.shutdown()
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

  it('request 只接受 requestId 匹配的响应并清理全部临时订阅', async () => {
    const handlers = new Map<string, (message: any) => void>()
    subscriptionMocks.subscribe.mockImplementation((filter, handler) => {
      handlers.set(filter.type, handler)
      return `sub_${filter.type}`
    })

    const conn = await loadConnection()
    const connecting = conn.connect()
    await vi.waitFor(() => expect(FakeWebSocket.instances.length).toBe(1))
    latestSocket().triggerOpen()
    await connecting

    const pending = conn.request(
      'PluginMarket',
      'market.snapshot.request',
      ['market.snapshot.response', 'market.error'],
      { perPrefixLimit: 60 },
      1000
    )
    const sent = JSON.parse(latestSocket().send.mock.calls.at(-1)![0])
    expect(sent.data.requestId).toMatch(/^req_/)
    expect(sent.data.perPrefixLimit).toBe(60)

    handlers.get('market.snapshot.response')?.({
      id: 'PluginMarket',
      type: 'market.snapshot.response',
      data: { requestId: 'unrelated' },
    })
    handlers.get('market.snapshot.response')?.({
      id: 'PluginMarket',
      type: 'market.snapshot.response',
      data: { requestId: sent.data.requestId, payload: { total: 1 } },
    })

    await expect(pending).resolves.toMatchObject({
      type: 'market.snapshot.response',
      data: { requestId: sent.data.requestId, payload: { total: 1 } },
    })
    expect(subscriptionMocks.unsubscribe).toHaveBeenCalledWith('sub_market.snapshot.response')
    expect(subscriptionMocks.unsubscribe).toHaveBeenCalledWith('sub_market.error')
  })

  it('request 发送失败时立即拒绝并撤销临时订阅', async () => {
    subscriptionMocks.subscribe.mockImplementation(filter => `sub_${filter.type}`)
    const conn = await loadConnection()

    await expect(
      conn.request('PluginMarket', 'market.snapshot.request', ['market.error'], {}, 1000)
    ).rejects.toThrow('PluginMarket/market.snapshot.request')
    expect(subscriptionMocks.unsubscribe).toHaveBeenCalledWith('sub_market.error')
  })

  it('request 超时后拒绝并撤销临时订阅', async () => {
    subscriptionMocks.subscribe.mockImplementation(filter => `sub_${filter.type}`)
    const conn = await loadConnection()
    const connecting = conn.connect()
    await vi.waitFor(() => expect(FakeWebSocket.instances.length).toBe(1))
    latestSocket().triggerOpen()
    await connecting

    vi.useFakeTimers()
    try {
      const pending = conn.request(
        'PluginMarket',
        'market.snapshot.request',
        ['market.snapshot.response'],
        {},
        25
      )
      const rejection = expect(pending).rejects.toThrow('PluginMarket/market.snapshot.request')
      await vi.advanceTimersByTimeAsync(25)
      await rejection
      expect(subscriptionMocks.unsubscribe).toHaveBeenCalledWith('sub_market.snapshot.response')
    } finally {
      vi.useRealTimers()
    }
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

    conn.stopReconnect()
    conn.shutdown()
  })

  it('Main/snapshot.response 按原始 id/type 展开并重新分发，记录 revision', async () => {
    const conn = await loadConnection()
    const p = conn.connect()
    await vi.waitFor(() => expect(FakeWebSocket.instances.length).toBe(1))
    latestSocket().triggerOpen()
    await p

    latestSocket().onmessage?.({
      data: JSON.stringify({
        id: 'Main',
        type: 'snapshot.response',
        data: {
          revision: 7,
          states: {
            'task.info.updated': {
              'task-1': { task_info: [] },
              'task-2': { task_info: [{ name: 'x' }] },
            },
            'power.sign.updated': {
              Main: { signal: 'Shutdown' },
            },
          },
        },
      }),
    })

    // 快照信封本身也分发一次（供请求-响应关联/诊断订阅者观察）
    expect(subscriptionMocks.dispatchMessage).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'Main', type: 'snapshot.response' })
    )
    // 每条状态按原始 id/type 重新分发给现有订阅者
    expect(subscriptionMocks.dispatchMessage).toHaveBeenCalledWith({
      id: 'task-1',
      type: 'task.info.updated',
      data: { task_info: [] },
    })
    expect(subscriptionMocks.dispatchMessage).toHaveBeenCalledWith({
      id: 'task-2',
      type: 'task.info.updated',
      data: { task_info: [{ name: 'x' }] },
    })
    expect(subscriptionMocks.dispatchMessage).toHaveBeenCalledWith({
      id: 'Main',
      type: 'power.sign.updated',
      data: { signal: 'Shutdown' },
    })
    expect(conn.connectionInfo().snapshotRevision).toBe(7)

    conn.shutdown()
  })

  it('快照 states 形状异常时安全忽略并告警，不影响后续消息', async () => {
    const conn = await loadConnection()
    const p = conn.connect()
    await vi.waitFor(() => expect(FakeWebSocket.instances.length).toBe(1))
    latestSocket().triggerOpen()
    await p

    // states 不是对象：整体忽略，只分发过快照信封本身
    subscriptionMocks.dispatchMessage.mockClear()
    latestSocket().onmessage?.({
      data: JSON.stringify({
        id: 'Main',
        type: 'snapshot.response',
        data: { revision: 1, states: 'broken' },
      }),
    })
    expect(logger.warn).toHaveBeenCalledWith(expect.stringContaining('states 形状异常'))
    expect(subscriptionMocks.dispatchMessage).toHaveBeenCalledTimes(1)

    // 部分条目异常：合法条目仍被重分发
    subscriptionMocks.dispatchMessage.mockClear()
    latestSocket().onmessage?.({
      data: JSON.stringify({
        id: 'Main',
        type: 'snapshot.response',
        data: {
          revision: 2,
          states: {
            'task.info.updated': [1, 2],
            'power.sign.updated': { Main: 'not-a-record', Other: { signal: 'Ok' } },
          },
        },
      }),
    })
    expect(subscriptionMocks.dispatchMessage).toHaveBeenCalledWith({
      id: 'Other',
      type: 'power.sign.updated',
      data: { signal: 'Ok' },
    })
    expect(subscriptionMocks.dispatchMessage).not.toHaveBeenCalledWith(
      expect.objectContaining({ id: 'Main', type: 'power.sign.updated' })
    )

    // 快照异常不影响后续普通消息分发
    latestSocket().onmessage?.({
      data: JSON.stringify({ id: 'Main', type: 'dialog.request', data: { requestId: 'r1' } }),
    })
    expect(subscriptionMocks.dispatchMessage).toHaveBeenCalledWith({
      id: 'Main',
      type: 'dialog.request',
      data: { requestId: 'r1' },
    })

    conn.shutdown()
  })

  // 1009（消息超限）与 4001（连接被替换）只停止**自动**重连，进入可恢复的
  // suspended 挂起态；只有 shutdown() 才是不可恢复终态 closed。
  const openConnection = async () => {
    const conn = await loadConnection()
    const pending = conn.connect()
    await vi.waitFor(() => expect(FakeWebSocket.instances.length).toBe(1))
    latestSocket().triggerOpen()
    await pending
    return conn
  }

  it('1009 消息过大进入 suspended 挂起态，不进入自动重连循环', async () => {
    const conn = await loadConnection()
    const onDisc = vi.fn()
    conn.onDisconnected(onDisc)

    const pending = conn.connect()
    await vi.waitFor(() => expect(FakeWebSocket.instances.length).toBe(1))
    latestSocket().triggerOpen()
    await pending

    latestSocket().triggerClose(1009, 'message too big')

    expect(onDisc).toHaveBeenCalledWith({ code: 1009, reason: 'message too big' })
    expect(conn.connectionState().value).toBe('suspended')
    expect(conn.connectionInfo().hasReconnectTimer).toBe(false)
    expect(logger.error).toHaveBeenCalledWith(
      '主 WebSocket 消息超过协议上限，停止自动重连以避免连接风暴'
    )
  })

  it('4001 连接被替换同样进入 suspended 且不自动重连', async () => {
    const conn = await openConnection()

    latestSocket().triggerClose(4001, 'connection replaced')

    expect(conn.connectionState().value).toBe('suspended')
    expect(conn.connectionInfo().hasReconnectTimer).toBe(false)
    expect(FakeWebSocket.instances.length).toBe(1)
  })

  it('suspended 后普通 connect 被拒绝，不新建连接', async () => {
    const conn = await openConnection()
    latestSocket().triggerClose(1009, 'message too big')
    expect(conn.connectionState().value).toBe('suspended')

    await expect(conn.connect()).resolves.toBe(false)
    expect(FakeWebSocket.instances.length).toBe(1)
    expect(conn.connectionState().value).toBe('suspended')
  })

  it('connect({ force: true }) 可从 suspended 恢复并重新建连', async () => {
    const conn = await openConnection()
    latestSocket().triggerClose(1009, 'message too big')
    expect(conn.connectionState().value).toBe('suspended')

    const resumed = conn.connect({ force: true })
    await vi.waitFor(() => expect(FakeWebSocket.instances.length).toBe(2))
    latestSocket().triggerOpen()

    await expect(resumed).resolves.toBe(true)
    expect(conn.connectionState().value).toBe('open')
  })

  it('shutdown 后即使 force 也拒绝连接（不可恢复终态）', async () => {
    const conn = await openConnection()

    conn.shutdown('测试关闭')
    expect(conn.connectionState().value).toBe('closed')

    await expect(conn.connect({ force: true })).resolves.toBe(false)
    expect(FakeWebSocket.instances.length).toBe(1)
    expect(conn.connectionState().value).toBe('closed')
  })

  it('suspended 恢复后再 shutdown 仍不可被 force 复活', async () => {
    const conn = await openConnection()
    latestSocket().triggerClose(1009, 'message too big')

    const resumed = conn.connect({ force: true })
    await vi.waitFor(() => expect(FakeWebSocket.instances.length).toBe(2))
    latestSocket().triggerOpen()
    await resumed

    conn.shutdown('测试关闭')
    await expect(conn.connect({ force: true })).resolves.toBe(false)
    expect(FakeWebSocket.instances.length).toBe(2)
  })
})
