import { afterEach, beforeEach, describe, expect, it, vi } from 'vite-plus/test'
import {
  WS_BETTERGI_INSTALL_DECISION,
  WS_BETTERGI_INSTALL_PROMPT,
  WS_BETTERGI_INSTALL_PROMPT_CLOSED,
  WS_ID_TASK_MANAGER,
} from './websocket/types'

const boundary = vi.hoisted(() => ({
  callbacks: new Map<string, (event: { data: Record<string, unknown> }) => void>(),
  send: vi.fn(),
  warn: vi.fn(),
  connected: true,
  disconnected: null as (() => void) | null,
}))

vi.mock('@/services/websocket/subscriptions', () => ({
  subscribe: (
    key: { id: string; type: string },
    handler: (event: { data: Record<string, unknown> }) => void
  ) => {
    const id = key.id + ':' + key.type
    boundary.callbacks.set(id, handler)
    return id
  },
  unsubscribe: (id: string) => boundary.callbacks.delete(id),
}))
vi.mock('@/services/websocket/connection', () => ({
  send: (id: string, type: string, data: unknown) => {
    boundary.send(id, type, data)
    return boundary.connected
  },
  onDisconnected: (listener: () => void) => {
    boundary.disconnected = listener
    return () => {
      boundary.disconnected = null
    }
  },
}))

const deliver = (type: string, data: Record<string, unknown>) => {
  boundary.callbacks.get(WS_ID_TASK_MANAGER + ':' + type)?.({ data })
}

const promptData = (requestId: string, taskId: string) => ({
  requestId,
  taskId,
  channel: 'stable',
  takeoverEnabled: false,
  installedVersion: '0.67.0',
  targetVersion: '0.67.0',
})

let recovery: typeof import('./bettergiInstallRecovery')

describe('BetterGI install recovery prompts', () => {
  beforeEach(async () => {
    vi.resetModules()
    vi.clearAllMocks()
    boundary.callbacks.clear()
    boundary.connected = true
    boundary.disconnected = null
    vi.stubGlobal('window', {
      electronAPI: { getLogger: () => ({ warn: boundary.warn }) },
    })
    recovery = await import('./bettergiInstallRecovery')
    recovery.bootstrapBetterGIInstallRecovery()
  })

  afterEach(() => {
    recovery.disposeBetterGIInstallRecovery()
    vi.unstubAllGlobals()
  })

  it('deduplicates requests and opens the next prompt only after closure', () => {
    deliver(WS_BETTERGI_INSTALL_PROMPT, promptData('req-a', 'task-a'))
    deliver(WS_BETTERGI_INSTALL_PROMPT, promptData('req-a', 'task-a'))
    deliver(WS_BETTERGI_INSTALL_PROMPT, promptData('req-b', 'task-b'))
    expect(recovery.bettergiInstallPrompts.value).toHaveLength(2)

    expect(recovery.respondToBetterGIInstallRecovery('skip')).toBe(true)
    expect(boundary.send).toHaveBeenCalledWith(
      WS_ID_TASK_MANAGER,
      WS_BETTERGI_INSTALL_DECISION,
      { requestId: 'req-a', taskId: 'task-a', action: 'skip' }
    )
    expect(recovery.respondToBetterGIInstallRecovery('retry')).toBe(false)

    deliver(WS_BETTERGI_INSTALL_PROMPT_CLOSED, { requestId: 'req-a' })
    expect(recovery.bettergiInstallPrompts.value[0].requestId).toBe('req-b')
    expect(recovery.respondToBetterGIInstallRecovery('retry')).toBe(true)
  })

  it('keeps prompt open when the websocket cannot send', () => {
    deliver(WS_BETTERGI_INSTALL_PROMPT, promptData('req-c', 'task-c'))
    boundary.connected = false
    expect(recovery.respondToBetterGIInstallRecovery('stop')).toBe(false)
    expect(recovery.bettergiInstallPrompts.value).toHaveLength(1)
    expect(recovery.bettergiInstallDecisionPending.value).toBeNull()

    boundary.connected = true
    expect(recovery.respondToBetterGIInstallRecovery('stop')).toBe(true)
    expect(boundary.send).toHaveBeenLastCalledWith(
      WS_ID_TASK_MANAGER,
      WS_BETTERGI_INSTALL_DECISION,
      { requestId: 'req-c', taskId: 'task-c', action: 'stop' }
    )
  })

  it('discards stale prompts on disconnect or backend closure', () => {
    deliver(WS_BETTERGI_INSTALL_PROMPT, promptData('req-d', 'task-d'))
    deliver(WS_BETTERGI_INSTALL_PROMPT_CLOSED, { requestId: 'req-d' })
    expect(recovery.bettergiInstallPrompts.value).toHaveLength(0)

    deliver(WS_BETTERGI_INSTALL_PROMPT, promptData('req-e', 'task-e'))
    boundary.disconnected?.()
    expect(recovery.bettergiInstallPrompts.value).toHaveLength(0)
    expect(recovery.bettergiInstallDecisionPending.value).toBeNull()
  })
})
