import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
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

const autoUpdate = (enabled: boolean) =>
  getSettingsMock.mockResolvedValue({ code: 200, data: { Update: { IfAutoUpdate: enabled } } })

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
  it('是应用级定时器：composable 里不再注册 onUnmounted', () => {
    const source = readFileSync(
      join(dirname(fileURLToPath(import.meta.url)), 'useUpdateChecker.ts'),
      'utf8'
    )
    expect(source).not.toContain('onUnmounted')
  })

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
