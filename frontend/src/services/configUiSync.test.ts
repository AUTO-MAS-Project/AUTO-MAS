import { QueryObserver } from '@tanstack/vue-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vite-plus/test'
import { queryClient } from './queryClient'
import { bootstrapConfigUiSync, disposeConfigUiSync } from './configUiSync'

const socket = vi.hoisted(() => ({
  state: { value: 'open' },
  push: undefined as ((message: { data: { nodeUids: string[] } }) => void) | undefined,
  connect: undefined as (() => void) | undefined,
  disconnect: undefined as (() => void) | undefined,
}))

vi.mock('./queryClient', async () => {
  const { QueryClient } = await import('@tanstack/vue-query')
  return { queryClient: new QueryClient({ defaultOptions: { queries: { gcTime: Infinity } } }) }
})
vi.mock('./websocket/connection', () => ({
  connectionState: () => socket.state,
  onConnected: (listener: () => void) => {
    socket.connect = listener
    return () => (socket.connect = undefined)
  },
  onDisconnected: (listener: () => void) => {
    socket.disconnect = listener
    return () => (socket.disconnect = undefined)
  },
}))
vi.mock('./websocket/subscriptions', () => ({
  subscribe: (_key: unknown, handler: typeof socket.push) => {
    socket.push = handler
    return 'test'
  },
  unsubscribe: () => (socket.push = undefined),
}))

const observers: (() => void)[] = []
const visibility = Object.assign(new EventTarget(), { hidden: false })

function watchSnapshot(key: string, uid: string) {
  const request = vi.fn(async () => ({ uiSources: [uid] }))
  const observer = new QueryObserver(queryClient, {
    queryKey: [key],
    queryFn: request,
    meta: { configSnapshot: true },
  })
  const dispose = observer.subscribe(() => {})
  observers.push(dispose)
  return { observer, request, dispose }
}

describe('configuration snapshot synchronization', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.stubGlobal('window', globalThis)
    vi.stubGlobal('document', visibility)
    visibility.hidden = false
    socket.state.value = 'open'
    bootstrapConfigUiSync()
  })

  afterEach(() => {
    disposeConfigUiSync()
    for (const dispose of observers.splice(0)) dispose()
    queryClient.clear()
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  it('refreshes shared active dependencies and only invalidates inactive snapshots', async () => {
    const a = watchSnapshot('settings', 'shared')
    const b = watchSnapshot('dialog', 'shared')
    const other = watchSnapshot('other', 'other')
    const closed = watchSnapshot('closed', 'shared')
    await Promise.all([a, b, other, closed].map(item => item.observer.refetch()))
    closed.dispose()
    socket.push?.({ data: { nodeUids: ['shared', 'shared'] } })
    socket.push?.({ data: { nodeUids: ['shared'] } })
    await vi.advanceTimersByTimeAsync(25)
    expect(a.request).toHaveBeenCalledTimes(2)
    expect(b.request).toHaveBeenCalledTimes(2)
    expect(other.request).toHaveBeenCalledTimes(1)
    expect(closed.request).toHaveBeenCalledTimes(1)
    expect(queryClient.getQueryState(['closed'])?.isInvalidated).toBe(true)
  })

  it('polls the visible page only while disconnected and reconciles on reconnect', async () => {
    const first = watchSnapshot('first', 'first')
    await first.observer.refetch()
    socket.state.value = 'closed'
    socket.disconnect?.()
    await vi.advanceTimersByTimeAsync(5000)
    expect(first.request).toHaveBeenCalledTimes(2)
    first.dispose()
    const second = watchSnapshot('second', 'second')
    await second.observer.refetch()
    await vi.advanceTimersByTimeAsync(5000)
    expect(first.request).toHaveBeenCalledTimes(2)
    expect(second.request).toHaveBeenCalledTimes(2)
    visibility.hidden = true
    visibility.dispatchEvent(new Event('visibilitychange'))
    await vi.advanceTimersByTimeAsync(10000)
    expect(second.request).toHaveBeenCalledTimes(2)
    visibility.hidden = false
    socket.state.value = 'open'
    socket.connect?.()
    await vi.advanceTimersByTimeAsync(10000)
    expect(second.request).toHaveBeenCalledTimes(3)
  })

  it('rechecks dependencies discovered by a response after a concurrent notification', async () => {
    let release!: (snapshot: { uiSources: string[] }) => void
    const first = new Promise<{ uiSources: string[] }>(resolve => {
      release = resolve
    })
    const request = vi.fn(async () => ({ uiSources: ['new-source'] })).mockReturnValueOnce(first)
    const observer = new QueryObserver(queryClient, {
      queryKey: ['initial'],
      queryFn: request,
      meta: { configSnapshot: true },
    })
    observers.push(observer.subscribe(() => {}))
    socket.push?.({ data: { nodeUids: ['new-source'] } })
    await vi.advanceTimersByTimeAsync(25)
    expect(request).toHaveBeenCalledTimes(1)
    release({ uiSources: ['new-source'] })
    await vi.advanceTimersByTimeAsync(0)
    expect(request).toHaveBeenCalledTimes(2)
  })
})
