import { afterEach, expect, it, vi } from 'vite-plus/test'

const boundary = vi.hoisted(() => ({
  subscriptions: new Map<string, (message: { data: Record<string, unknown> }) => void>(),
  connected: [] as Array<() => void>,
  disconnected: [] as Array<() => void>,
  send: vi.fn(() => true),
}))

vi.mock('@/services/websocket/subscriptions', () => ({
  subscribe: (
    criteria: { id: string; type: string },
    handler: (message: { data: Record<string, unknown> }) => void
  ) => {
    const key = `${criteria.id}:${criteria.type}`
    boundary.subscriptions.set(key, handler)
    return key
  },
  unsubscribe: (id: string) => {
    boundary.subscriptions.delete(id)
  },
}))

vi.mock('@/services/websocket/connection', () => ({
  send: boundary.send,
  onConnected: (listener: () => void) => {
    boundary.connected.push(listener)
    return () => {
      const at = boundary.connected.indexOf(listener)
      if (at >= 0) boundary.connected.splice(at, 1)
    }
  },
  onDisconnected: (listener: () => void) => {
    boundary.disconnected.push(listener)
    return () => {
      const at = boundary.disconnected.indexOf(listener)
      if (at >= 0) boundary.disconnected.splice(at, 1)
    }
  },
}))

afterEach(() => {
  vi.unstubAllGlobals()
  boundary.subscriptions.clear()
  boundary.connected.length = 0
  boundary.disconnected.length = 0
  boundary.send.mockClear()
})

it('drops stale BetterGI install prompt after active websocket reconnect without close event', async () => {
  vi.stubGlobal('window', {
    electronAPI: { getLogger: () => ({ warn: vi.fn() }) },
  })
  const module = await import('./bettergiInstallRecovery')
  module.bootstrapBetterGIInstallRecovery()
  const prompt = boundary.subscriptions.get('TaskManager:bettergi.install.prompt')
  expect(prompt).toBeTruthy()

  prompt!({
    data: {
      requestId: 'old-request',
      taskId: 'task-one',
      managedName: 'Example',
      installPath: '/sandbox/one',
    },
  })
  expect(module.bettergiInstallPrompts.value).toHaveLength(1)
  expect(boundary.connected).toHaveLength(1)

  // Simulate reconnectNow successful: stale socket close was intentionally ignored,
  // and backend's final prompt-closed frame never arrived.
  boundary.connected[0]()
  expect(module.bettergiInstallPrompts.value).toHaveLength(0)
  expect(module.bettergiInstallDecisionPending.value).toBeNull()
  expect(module.respondToBetterGIInstallRecovery('skip')).toBe(false)
  expect(boundary.send).not.toHaveBeenCalled()

  // A new prompt from the new transport remains actionable.
  prompt!({ data: { requestId: 'new-request', taskId: 'task-two' } })
  expect(module.respondToBetterGIInstallRecovery('stop')).toBe(true)
  expect(boundary.send).toHaveBeenCalledOnce()

  module.disposeBetterGIInstallRecovery()
  expect(boundary.connected).toHaveLength(0)
  expect(boundary.disconnected).toHaveLength(0)
})
