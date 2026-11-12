import { afterEach, beforeEach, describe, expect, it, vi } from 'vite-plus/test'
import { validateAnalyticsEvent } from '../../electron/services/analyticsPolicy'

let disk: Record<string, unknown>
const saveConfig = vi.fn()
const trackEvent = vi.fn()

beforeEach(() => {
  vi.resetModules()
  vi.resetAllMocks()
  disk = { confirmBeforeClose: false, lastCloseAction: 'tray' }
  saveConfig.mockImplementation(async (patch, defaults) => {
    disk = { ...defaults, ...disk, ...patch }
  })
  vi.stubGlobal('localStorage', { getItem: () => null, removeItem: vi.fn() })
  vi.stubGlobal('window', {
    appEnvironment: 'production',
    electronAPI: {
      loadConfig: async () => ({ ...disk }),
      saveConfig,
      getLogger: () => ({ info: vi.fn(), warn: vi.fn(), error: vi.fn() }),
      analytics: { getContext: async () => 1, trackEvent },
    },
  })
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('默认关闭动作的共享偏好', () => {
  it('修改记住的托盘动作后，重新加载使用新动作且不改关闭确认开关', async () => {
    const { useAppClosePreferences } = await import('./useAppClosePreferences')
    const preferences = useAppClosePreferences()
    await preferences.load()
    expect(preferences.lastAction.value).toBe('tray')

    await preferences.chooseAction('quit', false)
    expect(disk).toMatchObject({ confirmBeforeClose: false, lastCloseAction: 'quit' })
    expect(useAppClosePreferences().lastAction.value).toBe('quit')
    expect(preferences.confirmBeforeClose.value).toBe(false)

    vi.resetModules()
    const reloaded = (await import('./useAppClosePreferences')).useAppClosePreferences()
    await reloaded.load()
    expect(reloaded.lastAction.value).toBe('quit')
    expect(reloaded.confirmBeforeClose.value).toBe(false)

    expect(trackEvent.mock.calls.map(([, event]) => validateAnalyticsEvent(event, true))).toEqual([
      expect.objectContaining({
        name: 'settings_change_finished',
        props: expect.objectContaining({
          setting_kind: 'close',
          setting_key: 'close_to_tray',
          value_kind: 'disabled',
          outcome: 'success',
        }),
      }),
    ])
  })

  it('写入失败保留原动作，重试成功后关闭确认框与设置页读取同一选择', async () => {
    disk = { confirmBeforeClose: true, lastCloseAction: 'quit' }
    const { useAppClosePreferences } = await import('./useAppClosePreferences')
    const preferences = useAppClosePreferences()
    await preferences.load()
    saveConfig.mockRejectedValueOnce(new Error('disk unavailable'))

    await expect(preferences.chooseAction('tray', false)).rejects.toThrow('disk unavailable')
    expect(preferences.lastAction.value).toBe('quit')
    expect(preferences.saving.value).toBe(false)
    expect(disk).toMatchObject({ confirmBeforeClose: true, lastCloseAction: 'quit' })

    await preferences.chooseAction('tray', false)
    expect(preferences.lastAction.value).toBe('tray')
    expect(preferences.confirmBeforeClose.value).toBe(true)
    await preferences.chooseAction('quit', true)
    expect(useAppClosePreferences().lastAction.value).toBe('quit')
    expect(preferences.confirmBeforeClose.value).toBe(false)
    expect(disk).toMatchObject({ confirmBeforeClose: false, lastCloseAction: 'quit' })
  })
})
