import { afterEach, beforeEach, describe, expect, it, vi } from 'vite-plus/test'
import { useNativeGuiSession } from './useNativeGuiSession'

const mocks = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
  warning: vi.fn(),
  start: vi.fn(),
  stop: vi.fn(),
  status: vi.fn(),
}))
vi.mock('ant-design-vue', () => ({ message: mocks }))
vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (key: string) => key }) }))
vi.mock('@/composables/useTaskApi', () => ({
  requestTaskStart: mocks.start,
  stopNativeConfig: mocks.stop,
}))
vi.mock('@/api/services/Service', () => ({
  Service: { getTaskStatusApiDispatchTaskTaskIdGet: mocks.status },
}))
vi.mock('@/composables/useWebSocket', () => ({
  useWebSocket: () => ({ subscribe: () => 'id', unsubscribe: vi.fn() }),
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

describe('plan native configuration save', () => {
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
  })

  it('reports an unconfirmed result when the HTTP query fails', async () => {
    mocks.status.mockRejectedValue(new Error('offline'))
    const session = useNativeGuiSession({ loggerName: 'test', keys })
    await session.startSession('script', false, 'unknown', { planId: 'plan' })
    const saving = session.saveSession()
    await vi.advanceTimersByTimeAsync(300)
    await saving
    expect(mocks.success).not.toHaveBeenCalledWith('saved')
    expect(mocks.warning).toHaveBeenCalledWith('saveUnknown')
  })

  it.each([
    ['saved', 'saved'],
    ['failed', 'saveFailed'],
    [null, 'saveUnknown'],
  ])(
    'reports %s from the HTTP result without a WebSocket notification',
    async (result, expected) => {
      mocks.status.mockResolvedValue({ code: 200, planSaveResult: result })
      const session = useNativeGuiSession({ loggerName: 'test', keys })
      await session.startSession('script', false, 'unknown', { planId: 'plan' })
      const saving = session.saveSession()
      await vi.advanceTimersByTimeAsync(300)
      await saving
      if (expected === 'saved') expect(mocks.success).toHaveBeenCalledWith('saved')
      else {
        expect(mocks.success).not.toHaveBeenCalledWith('saved')
        expect(expected === 'saveFailed' ? mocks.error : mocks.warning).toHaveBeenCalledWith(
          expected
        )
      }
    }
  )
})
