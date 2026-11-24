import { afterEach, beforeEach, describe, expect, it, vi } from 'vite-plus/test'
import { useNativeGuiSession } from './useNativeGuiSession'
import { WS_TASK_NOTICE } from '@/services/websocket/types'

const mocks = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
  warning: vi.fn(),
  start: vi.fn(),
  stop: vi.fn(),
  status: vi.fn(),
  listeners: new Map<string, (frame: unknown) => void>(),
}))
vi.mock('ant-design-vue', () => ({ message: mocks }))
vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (key: string) => key }) }))
vi.mock('@/composables/useTaskApi', () => ({
  requestScriptConfigStart: mocks.start,
  stopNativeConfig: mocks.stop,
}))
vi.mock('@/api/services/Service', () => ({
  Service: { getTaskStatusApiDispatchTaskTaskIdGet: mocks.status },
}))
vi.mock('@/composables/useWebSocket', () => ({
  useWebSocket: () => ({
    subscribe: (request: { type: string }, listener: (frame: unknown) => void) => {
      mocks.listeners.set(request.type, listener)
      return request.type
    },
    unsubscribe: (type: string) => mocks.listeners.delete(type),
  }),
}))
vi.mock('@/utils/configSessionDiscard', () => ({ showConfigDiscardWarning: vi.fn() }))

const keys = {
  stopFailed: 'stopFailed',
  startFailed: 'startFailed',
  setupFailed: 'setupFailed',
  opened: 'opened',
  viewOpened: 'viewOpened',
  timeoutWarn: 'timeoutWarn',
  saved: 'saved',
  saveFailed: 'saveFailed',
  saveUnknown: 'saveUnknown',
}

describe('native configuration session during scheduler migration', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.stubGlobal('window', {
      setTimeout,
      clearTimeout,
      electronAPI: { getLogger: () => ({ error: vi.fn() }) },
    })
    mocks.start.mockResolvedValue({ code: 200, taskId: 'task' })
    mocks.stop.mockResolvedValue({ code: 200 })
  })
  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
    vi.clearAllMocks()
    mocks.listeners.clear()
  })

  it('uses the requirement-tree entry for a native session', async () => {
    const session = useNativeGuiSession({ loggerName: 'test', keys })
    expect(
      await session.startSession('script', false, 'script', { params: { instance_idx: 2 } })
    ).toBe(true)
    expect(mocks.start).toHaveBeenCalledWith('script', false, 'script', { instance_idx: 2 })
    await session.dispose()
  })

  it('does not query a deferred plan result when saving a normal session', async () => {
    const session = useNativeGuiSession({ loggerName: 'test', keys })
    await session.startSession('script')
    const saving = session.saveSession()
    await vi.advanceTimersByTimeAsync(300)
    await saving
    expect(mocks.status).not.toHaveBeenCalled()
    expect(mocks.success).toHaveBeenCalledWith('saved')
  })

  it('keeps a failed save from reporting success and resets for the next session', async () => {
    const session = useNativeGuiSession({ loggerName: 'test', keys })
    await session.startSession('script')
    mocks.success.mockClear()
    mocks.stop.mockImplementationOnce(async () => {
      mocks.listeners.get(WS_TASK_NOTICE)?.({
        data: { level: 'error', message: 'configuration write failed' },
      })
      return { code: 200 }
    })
    const failedSave = session.saveSession()
    await vi.advanceTimersByTimeAsync(300)
    await failedSave
    expect(mocks.error).toHaveBeenCalledWith('setupFailed')
    expect(mocks.success).not.toHaveBeenCalledWith('saved')

    await session.startSession('script')
    const successfulSave = session.saveSession()
    await vi.advanceTimersByTimeAsync(300)
    await successfulSave
    expect(mocks.success).toHaveBeenCalledWith('saved')
  })
})
