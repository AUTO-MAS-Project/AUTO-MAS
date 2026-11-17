import { CancelablePromise, McpStatusData, type OutBase } from '@/api'
import { VueQueryPlugin } from '@tanstack/vue-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vite-plus/test'
import { createApp, effectScope } from 'vue'

const boundaries = vi.hoisted(() => ({
  connected: null as (() => Promise<void>) | null,
  disconnected: null as (() => void) | null,
  receive: null as ((message: { data: McpStatusData }) => void) | null,
  unsubscribe: vi.fn(),
  disconnect: vi.fn(),
  disconnectedCleanup: vi.fn(),
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
  observeFeature: (_name: string, _props: unknown, run: () => Promise<unknown>) => run(),
}))
vi.mock('@/i18n', () => ({ translate: (key: string) => key }))

const snapshot = (revision = 1, overrides: Partial<McpStatusData> = {}): McpStatusData => ({
  enabled: true,
  environmentEnabled: true,
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

const notification = () =>
  new CancelablePromise<OutBase>(resolve => resolve({ code: 200, status: 'success', message: '' }))

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
    vi.useFakeTimers()
    const frames: FrameRequestCallback[] = []
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) =>
      frames.push(callback)
    )
    vi.stubGlobal('cancelAnimationFrame', vi.fn())
    const stalled = new CancelablePromise<OutBase>(() => {})
    const release = vi
      .spyOn(backend, 'notifyMcpHomePaintedApiCoreMcpHomePaintedPost')
      .mockReturnValueOnce(stalled)
      .mockImplementation(() => notification())
    vi.spyOn(backend, 'getMcpStatusApiCoreMcpStatusGet').mockResolvedValue({
      code: 200,
      data: snapshot(0, { state: McpStatusData.state.PENDING }),
    } as never)
    await boundaries.connected!()
    expect(release).not.toHaveBeenCalled()
    module.scheduleMcpAfterPaint()
    frames.shift()!(0)
    boundaries.connection.value = 'open'
    await boundaries.connected!()
    expect(release).not.toHaveBeenCalled()
    boundaries.connection.value = 'idle'
    boundaries.disconnected!()
    frames.shift()!(16)
    expect(release).not.toHaveBeenCalled()
    boundaries.connection.value = 'open'
    await boundaries.connected!()
    expect(release).toHaveBeenCalledTimes(1)
    module.notifyMcpHomePainted()
    await api.refresh()
    expect(release).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(4999)
    expect(stalled.isCancelled).toBe(false)
    expect(release).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(1001)
    expect(stalled.isCancelled).toBe(true)
    expect(release).toHaveBeenCalledTimes(2)
    await boundaries.connected!()
    expect(release).toHaveBeenCalledTimes(3)
  })

  it('restores the new backend after reconnect and rejects old responses and runs', async () => {
    const first = deferred<{ code: number; data: McpStatusData }>()
    const older = deferred<{ code: number; data: McpStatusData }>()
    vi.spyOn(backend, 'getMcpStatusApiCoreMcpStatusGet')
      .mockReturnValueOnce(first.promise as never)
      .mockResolvedValueOnce({
        code: 200,
        data: snapshot(0, { instanceId: 'process-2', runId: 'run-2' }),
      })
      .mockReturnValueOnce(older.promise as never)
    boundaries.receive!({ data: snapshot(5) })
    const refresh = api.refresh()
    await boundaries.connected!()
    first.resolve({ code: 200, data: snapshot(6) })
    await refresh
    expect(current().instanceId).toBe('process-2')
    boundaries.receive!({ data: snapshot(8) })
    expect(current().instanceId).toBe('process-2')
    const sameInstanceRefresh = api.refresh()
    boundaries.receive!({ data: snapshot(2, { instanceId: 'process-2', runId: 'retry-2' }) })
    older.resolve({ code: 200, data: snapshot(1, { instanceId: 'process-2', runId: 'run-2' }) })
    await sameInstanceRefresh
    expect(current()).toMatchObject({ instanceId: 'process-2', revision: 2, runId: 'retry-2' })
    boundaries.receive!({ data: snapshot(1, { instanceId: 'process-2' }) })
    expect(current().runId).toBe('retry-2')
  })
})
