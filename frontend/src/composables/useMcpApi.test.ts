import { afterEach, beforeEach, describe, expect, it, vi } from 'vite-plus/test'
import { createApp, effectScope, nextTick } from 'vue'
import { VueQueryPlugin } from '@tanstack/vue-query'
import { CancelablePromise, McpStatusData, type OutBase } from '@/api'

const boundaries = vi.hoisted(() => ({
  connected: null as (() => Promise<void>) | null,
  disconnected: null as (() => void) | null,
  receive: null as ((message: { data: McpStatusData }) => void) | null,
  unsubscribe: vi.fn(),
  disconnect: vi.fn(),
  disconnectedCleanup: vi.fn(),
  observe: vi.fn(),
  connection: { value: 'idle' },
}))
vi.mock('@/services/websocket/connection', () => ({
  connectionState: () => boundaries.connection,
  onConnected: (callback: () => Promise<void>) => {
    boundaries.connected = callback
    return boundaries.disconnect
  },
  onDisconnected: (callback: () => void) => {
    boundaries.disconnected = callback
    return boundaries.disconnectedCleanup
  },
}))
vi.mock('@/services/websocket/subscriptions', () => ({
  subscribe: (_filter: unknown, callback: (message: { data: McpStatusData }) => void) => {
    boundaries.receive = callback
    return 'mcp'
  },
  unsubscribe: boundaries.unsubscribe,
}))
vi.mock('@/utils/featureAnalytics', () => ({
  observeFeature: (
    name: string,
    _props: unknown,
    run: () => Promise<unknown>,
    outcome: (result: unknown) => string
  ) => {
    const request = run()
    void request.then(
      result => boundaries.observe(name, outcome(result)),
      () => undefined
    )
    return request
  },
}))
vi.mock('@/i18n', () => ({ translate: (key: string) => key }))

const snapshot = (revision = 1, overrides: Partial<McpStatusData> = {}): McpStatusData => ({
  enabled: true,
  state: McpStatusData.state.RUNNING,
  stage: 'building',
  startedAt: null,
  finishedAt: null,
  elapsedMs: 10,
  toolCount: 0,
  error: null,
  instanceId: 'process-1',
  runId: 'run-1',
  revision,
  ...overrides,
})
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(finish => {
    resolve = finish
  })
  return { promise, resolve }
}

const notification = (error?: Error) =>
  new CancelablePromise<OutBase>((resolve, reject) => {
    if (error) reject(error)
    else resolve({ code: 200, status: 'success', message: '' })
  })

describe('MCP status reconciliation', () => {
  let backend: (typeof import('@/api'))['Service']
  let module: typeof import('./useMcpApi')
  let cache: (typeof import('@/services/queryClient'))['queryClient']
  let scope: ReturnType<typeof effectScope>
  let api: ReturnType<(typeof import('./useMcpApi'))['useMcpApi']>
  beforeEach(async () => {
    vi.stubGlobal('window', {
      electronAPI: { getLogger: () => ({ warn: vi.fn(), info: vi.fn() }) },
    })
    vi.resetModules()
    vi.clearAllMocks()
    boundaries.connection.value = 'idle'
    cache = (await import('@/services/queryClient')).queryClient
    backend = (await import('@/api')).Service
    module = await import('./useMcpApi')
    const app = createApp({})
    app.use(VueQueryPlugin, { queryClient: cache })
    scope = effectScope()
    api = scope.run(() => app.runWithContext(() => module.useMcpApi()))!
    module.bootstrapMcpStatus()
  }, 30_000)
  afterEach(() => {
    api.dispose()
    scope.stop()
    module.disposeMcpStatus()
    cache.clear()
    vi.restoreAllMocks()
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })
  const current = () => cache.getQueryData<McpStatusData>(['core', 'mcp-status'])!

  it('releases MCP only after home paint, including a later backend connection', async () => {
    const release = vi
      .spyOn(backend, 'notifyMcpHomePaintedApiCoreMcpHomePaintedPost')
      .mockImplementation(() => notification())
    vi.spyOn(backend, 'getMcpStatusApiCoreMcpStatusGet').mockResolvedValue({
      code: 200,
      data: snapshot(),
    } as never)
    await boundaries.connected!()
    expect(release).not.toHaveBeenCalled()
    module.notifyMcpHomePainted()
    expect(release).not.toHaveBeenCalled()
    boundaries.connection.value = 'open'
    await boundaries.connected!()
    expect(release).toHaveBeenCalledTimes(1)
    module.notifyMcpHomePainted()
    expect(release).toHaveBeenCalledTimes(1)
    await boundaries.connected!()
    expect(release).toHaveBeenCalledTimes(2)
  })

  it('releases MCP immediately when the home frame follows the backend connection', () => {
    const release = vi
      .spyOn(backend, 'notifyMcpHomePaintedApiCoreMcpHomePaintedPost')
      .mockImplementation(() => notification())
    boundaries.connection.value = 'open'
    module.notifyMcpHomePainted()
    module.notifyMcpHomePainted()
    expect(release).toHaveBeenCalledTimes(1)
  })

  it('automatically recovers after more than three failures without a websocket reconnect', async () => {
    vi.useFakeTimers()
    let failures = 5
    const release = vi
      .spyOn(backend, 'notifyMcpHomePaintedApiCoreMcpHomePaintedPost')
      .mockImplementation(() =>
        notification(failures-- > 0 ? new Error('network unavailable') : undefined)
      )
    boundaries.connection.value = 'open'
    module.notifyMcpHomePainted()
    await vi.advanceTimersByTimeAsync(40_000)
    expect(release).toHaveBeenCalledTimes(6)
    await vi.advanceTimersByTimeAsync(60_000)
    expect(release).toHaveBeenCalledTimes(6)
  })

  it('cancels a stalled request on timeout and recovers without overlapping requests', async () => {
    vi.useFakeTimers()
    const stalled = new CancelablePromise<OutBase>(() => {})
    const cancel = vi.spyOn(stalled, 'cancel')
    const release = vi
      .spyOn(backend, 'notifyMcpHomePaintedApiCoreMcpHomePaintedPost')
      .mockReturnValueOnce(stalled)
      .mockImplementation(() => notification())
    boundaries.connection.value = 'open'
    module.notifyMcpHomePainted()
    await vi.advanceTimersByTimeAsync(4999)
    expect(release).toHaveBeenCalledTimes(1)
    expect(cancel).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(1001)
    expect(cancel).toHaveBeenCalledOnce()
    expect(release).toHaveBeenCalledTimes(2)
  })

  it('cancels outstanding work on disconnect and dispose', async () => {
    vi.useFakeTimers()
    const stalled = new CancelablePromise<OutBase>(() => {})
    const release = vi
      .spyOn(backend, 'notifyMcpHomePaintedApiCoreMcpHomePaintedPost')
      .mockReturnValueOnce(stalled)
      .mockImplementation(() => notification(new Error('offline')))
    vi.spyOn(backend, 'getMcpStatusApiCoreMcpStatusGet').mockResolvedValue({
      code: 200,
      data: snapshot(0, { state: McpStatusData.state.PENDING }),
    } as never)
    boundaries.connection.value = 'open'
    module.notifyMcpHomePainted()
    boundaries.connection.value = 'idle'
    boundaries.disconnected!()
    expect(stalled.isCancelled).toBe(true)
    await vi.advanceTimersByTimeAsync(60_000)
    expect(release).toHaveBeenCalledTimes(1)
    boundaries.connection.value = 'open'
    await boundaries.connected!()
    expect(release).toHaveBeenCalledTimes(2)
    module.disposeMcpStatus()
    await vi.advanceTimersByTimeAsync(60_000)
    expect(release).toHaveBeenCalledTimes(2)
  })

  it('continues paint coordination after a route cancels the previous frame', async () => {
    let nextId = 0
    const frames = new Map<number, FrameRequestCallback>()
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
      frames.set(++nextId, callback)
      return nextId
    })
    vi.stubGlobal('cancelAnimationFrame', (id: number) => frames.delete(id))
    const frame = () => {
      const callbacks = [...frames.values()]
      frames.clear()
      callbacks.forEach(callback => callback(0))
    }
    const release = vi
      .spyOn(backend, 'notifyMcpHomePaintedApiCoreMcpHomePaintedPost')
      .mockImplementation(() => notification())
    boundaries.connection.value = 'open'
    module.scheduleMcpAfterPaint()
    frame()
    expect(release).not.toHaveBeenCalled()
    module.cancelMcpPaint()
    module.scheduleMcpAfterPaint()
    frame()
    expect(release).not.toHaveBeenCalled()
    frame()
    expect(release).toHaveBeenCalledOnce()
    await Promise.resolve()
  })

  it('preserves a newer WS update when an older snapshot arrives', async () => {
    const request = deferred<{ code: number; data: McpStatusData }>()
    vi.spyOn(backend, 'getMcpStatusApiCoreMcpStatusGet').mockReturnValue(request.promise as never)
    const refresh = api.refresh()
    boundaries.receive!({ data: snapshot(5) })
    request.resolve({ code: 200, data: snapshot(2) })
    await refresh
    expect(current().revision).toBe(5)
    boundaries.receive!({ data: snapshot(4) })
    expect(current().revision).toBe(5)
  })

  it('restores the new backend after reconnect and rejects old responses and runs', async () => {
    const first = deferred<{ code: number; data: McpStatusData }>()
    vi.spyOn(backend, 'getMcpStatusApiCoreMcpStatusGet')
      .mockReturnValueOnce(first.promise as never)
      .mockResolvedValueOnce({
        code: 200,
        data: snapshot(0, { instanceId: 'process-2', runId: 'run-2' }),
      })
    boundaries.receive!({ data: snapshot(5) })
    const refresh = api.refresh()
    await boundaries.connected!()
    first.resolve({ code: 200, data: snapshot(6) })
    await refresh
    expect(current().instanceId).toBe('process-2')
    boundaries.receive!({ data: snapshot(8) })
    expect(current().instanceId).toBe('process-2')
    boundaries.receive!({ data: snapshot(2, { instanceId: 'process-2', runId: 'retry-2' }) })
    boundaries.receive!({ data: snapshot(1, { instanceId: 'process-2' }) })
    expect(current().runId).toBe('retry-2')
  })

  it('deduplicates retry and tracks the actual ready result over its acceptance snapshot', async () => {
    boundaries.receive!({ data: snapshot(5, { state: McpStatusData.state.FAILED }) })
    await nextTick()
    const response = deferred<{ code: number; accepted: boolean; data: McpStatusData }>()
    const request = vi
      .spyOn(backend, 'retryMcpApiCoreMcpRetryPost')
      .mockReturnValue(response.promise as never)
    const retry = api.retry()
    await api.retry()
    expect(request).toHaveBeenCalledTimes(1)
    expect(api.retrying.value).toBe(true)
    boundaries.receive!({ data: snapshot(9, { state: McpStatusData.state.READY, runId: 'retry' }) })
    response.resolve({ code: 200, accepted: true, data: snapshot(6, { runId: 'retry' }) })
    await retry
    expect(current().state).toBe('ready')
    expect(api.retrying.value).toBe(false)
    expect(boundaries.observe).toHaveBeenCalledWith('mcp_retry_requested', 'accepted')
    await api.retry()
    expect(request).toHaveBeenCalledTimes(1)
  })

  it('does not restore disposed data or duplicate resident subscriptions', async () => {
    const request = deferred<{ code: number; data: McpStatusData }>()
    vi.spyOn(backend, 'getMcpStatusApiCoreMcpStatusGet').mockReturnValue(request.promise as never)
    const receive = boundaries.receive
    module.bootstrapMcpStatus()
    expect(boundaries.receive).toBe(receive)
    const refresh = api.refresh()
    api.dispose()
    module.disposeMcpStatus()
    request.resolve({ code: 200, data: snapshot() })
    await refresh
    expect(current()).toBeUndefined()
    expect(boundaries.unsubscribe).toHaveBeenCalledTimes(1)
    expect(boundaries.disconnect).toHaveBeenCalledTimes(1)
  })
})
