import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// ==================== 全局桩 ====================

const logger = { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() }
vi.stubGlobal('window', { electronAPI: { getLogger: () => logger } })

const getSettingsMock = vi.fn()
vi.mock('@/api', () => ({
  Service: {
    checkUpdateApiUpdateCheckPost: vi.fn(),
    getScriptsApiSettingGetPost: (...args: unknown[]) => getSettingsMock(...args),
  },
}))
vi.mock('ant-design-vue', () => ({
  message: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}))
vi.mock('@/i18n', () => ({ translate: (key: string) => key }))
vi.mock('@/composables/useAudioPlayer', () => ({
  useAudioPlayer: () => ({ playSound: vi.fn(async () => true) }),
}))

const { useUpdateChecker } = await import('./useUpdateChecker')
const { Service } = await import('@/api')

const autoUpdate = (enabled: boolean) =>
  getSettingsMock.mockResolvedValue({ code: 200, data: { Update: { IfAutoUpdate: enabled } } })

// 暂停中：自动更新开着，但截止日期在未来（用远期日期避免依赖墙钟）
const pausedUpdate = (pauseUntil: string) =>
  getSettingsMock.mockResolvedValue({
    code: 200,
    data: { Update: { IfAutoUpdate: true, PauseUntil: pauseUntil } },
  })

const checkUpdateMock = vi.mocked(Service.checkUpdateApiUpdateCheckPost)

beforeEach(() => {
  vi.useFakeTimers()
  vi.spyOn(globalThis, 'setInterval')
  vi.spyOn(globalThis, 'clearInterval')
})

afterEach(() => {
  useUpdateChecker().stopPolling()
  vi.restoreAllMocks()
  vi.useRealTimers()
})

describe('useUpdateChecker 定时检查', () => {
  it('并发 startPolling 只建立一个定时器', async () => {
    autoUpdate(true)
    const { startPolling } = useUpdateChecker()
    // appEntry 与初始化面板会几乎同时各起一次
    await Promise.all([startPolling(), startPolling()])
    expect(vi.mocked(setInterval)).toHaveBeenCalledTimes(1)

    // 已经在跑时再起也不重复
    await startPolling()
    expect(vi.mocked(setInterval)).toHaveBeenCalledTimes(1)
  })

  it('关闭自动更新时不起定时器', async () => {
    autoUpdate(false)
    await useUpdateChecker().startPolling()
    expect(vi.mocked(setInterval)).not.toHaveBeenCalled()
  })

  it('stopPolling 后可以重新启动', async () => {
    autoUpdate(true)
    const { startPolling, stopPolling } = useUpdateChecker()
    await startPolling()
    stopPolling()
    expect(vi.mocked(clearInterval)).toHaveBeenCalledTimes(1)
    await startPolling()
    expect(vi.mocked(setInterval)).toHaveBeenCalledTimes(2)
  })
})

describe('useUpdateChecker 暂停更新', () => {
  beforeEach(() => {
    // 计数断言只关心本用例内的调用，避免受前序用例影响
    checkUpdateMock.mockClear()
  })

  it('暂停中跳过定时检查（3 秒首查不发起更新检查）', async () => {
    pausedUpdate('2999-12-31')
    await useUpdateChecker().startPolling()
    expect(vi.mocked(setInterval)).toHaveBeenCalledTimes(1)

    await vi.advanceTimersByTimeAsync(3000)
    expect(checkUpdateMock).not.toHaveBeenCalled()
  })

  it('暂停中仍启动定时器，截止日过后下个 tick 自动恢复检查', async () => {
    pausedUpdate('2999-12-31')
    const { startPolling } = useUpdateChecker()
    await startPolling()
    // 暂停不阻止起定时器，否则到期后永远无法自愈
    expect(vi.mocked(setInterval)).toHaveBeenCalledTimes(1)

    await vi.advanceTimersByTimeAsync(4 * 60 * 60 * 1000)
    expect(checkUpdateMock).not.toHaveBeenCalled()

    // 截止日已过（等价于到期或系统日期越过截止日）
    pausedUpdate('2000-01-01')
    await vi.advanceTimersByTimeAsync(4 * 60 * 60 * 1000)
    expect(checkUpdateMock).toHaveBeenCalledTimes(1)
  })

  it('暂停中手动检查不被拦截', async () => {
    pausedUpdate('2999-12-31')
    await useUpdateChecker().checkUpdate(false, true)
    expect(checkUpdateMock).toHaveBeenCalledTimes(1)
  })

  it('更新设置读取失败时失败关闭：不起定时器、定时检查跳过', async () => {
    // 启动时读取失败 → 状态未知，不起定时器
    getSettingsMock.mockRejectedValue(new Error('network down'))
    await useUpdateChecker().startPolling()
    expect(vi.mocked(setInterval)).not.toHaveBeenCalled()

    // 运行中读取失败 → 该 tick 跳过检查，不误判为"未暂停"
    autoUpdate(true)
    await useUpdateChecker().startPolling()
    getSettingsMock.mockRejectedValue(new Error('network down'))
    await vi.advanceTimersByTimeAsync(3000)
    expect(checkUpdateMock).not.toHaveBeenCalled()
  })
})
