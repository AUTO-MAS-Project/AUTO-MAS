import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

type Handler = (message: { id: string; type: string; data: Record<string, unknown> }) => void

const subscriptionMocks = vi.hoisted(() => ({
  subscribe: vi.fn(),
  handlers: new Map<string, Handler>(),
}))

vi.mock('@/services/websocket/subscriptions', () => ({
  subscribe: subscriptionMocks.subscribe.mockImplementation(
    (key: { id?: string; type?: string }, handler: Handler) => {
      subscriptionMocks.handlers.set(`${key.id}\u0000${key.type}`, handler)
      return `sub_${subscriptionMocks.handlers.size}`
    }
  ),
}))

vi.mock('@/composables/useAppClosing', () => ({
  useAppClosing: () => ({ showClosingOverlay: vi.fn() }),
}))

const logger = { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() }
const appQuit = vi.fn()
let storage = new Map<string, string>()

const loadHandlers = async () => {
  vi.resetModules()
  return await import('./schedulerHandlers')
}

describe('调度中心常驻 WS 订阅', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    subscriptionMocks.handlers.clear()
    storage = new Map()
    appQuit.mockResolvedValue(undefined)

    vi.stubGlobal('localStorage', {
      getItem: (key: string) => storage.get(key) ?? null,
      setItem: (key: string, value: string) => storage.set(key, value),
      removeItem: (key: string) => storage.delete(key),
    })
    vi.stubGlobal('window', {
      electronAPI: {
        getLogger: () => logger,
        appQuit,
      },
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('在连接前幂等注册 task.created 与 power.sign.updated 精确路由', async () => {
    const handlers = await loadHandlers()

    handlers.bootstrapSchedulerSubscriptions()
    handlers.bootstrapSchedulerSubscriptions()

    expect(subscriptionMocks.subscribe).toHaveBeenCalledTimes(2)
    expect(subscriptionMocks.handlers.has('TaskManager\u0000task.created')).toBe(true)
    expect(subscriptionMocks.handlers.has('Main\u0000power.sign.updated')).toBe(true)
  })

  it('canonical task.created 在 UI 未加载时进入可回放队列', async () => {
    const handlers = await loadHandlers()
    handlers.bootstrapSchedulerSubscriptions()

    subscriptionMocks.handlers.get('TaskManager\u0000task.created')?.({
      id: 'TaskManager',
      type: 'task.created',
      data: { taskId: 'task-1', queueId: 'queue-1' },
    })

    expect(handlers.consumePendingTabIds()).toEqual([{ taskId: 'task-1', queueId: 'queue-1' }])
    expect(handlers.consumePendingTabIds()).toEqual([])
  })

  it('canonical power.sign.updated 保存显示状态但不走旧关闭逻辑', async () => {
    const handlers = await loadHandlers()
    handlers.handleMainMessage({
      id: 'Main',
      type: 'power.sign.updated',
      data: { signal: 'Reboot' },
    })
    handlers.handleMainMessage({
      id: 'Main',
      type: 'frontend.close.requested',
      data: {},
    })

    expect(storage.get('scheduler-power-action')).toBe('Reboot')
    expect(appQuit).not.toHaveBeenCalled()
  })

  it('迁移期仍接受旧 TaskManager Signal/newTask', async () => {
    const handlers = await loadHandlers()
    handlers.handleTaskManagerMessage({
      id: 'TaskManager',
      type: 'Signal',
      data: { newTask: 'legacy-task', queueId: 'legacy-queue' },
    })

    expect(handlers.consumePendingTabIds()).toEqual([
      { taskId: 'legacy-task', queueId: 'legacy-queue' },
    ])
  })
})
