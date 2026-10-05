import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ConfigProvider } from 'ant-design-vue'
import { createSSRApp, h } from 'vue'
import { renderToString } from '@vue/server-renderer'
import type { AppearanceCleanupResult, InstalledAppearance } from '@/types/appearance'

const saveConfig = vi.fn(async () => undefined)
const appearanceChanged = vi.fn(() => () => undefined)
const appearance: InstalledAppearance = {
  formatVersion: 1 as const,
  id: 'demo',
  name: 'Demo',
  mode: 'dark' as const,
  tokens: { colorPrimary: '#123456' },
  backgroundUrl: 'data:image/png;base64,AA==',
  mascotUrl: 'data:image/png;base64,AA==',
  cursors: {
    pointer: { path: 'assets/pointer.png', hotspotX: 2, hotspotY: 3 },
  },
  cursorUrls: { pointer: 'data:image/png;base64,AA==' },
}
const listAppearances = vi.fn(async () => [appearance])
const clearInvalidAppearance = vi.fn<(expectedId: string) => Promise<AppearanceCleanupResult>>()
const removeAppearance = vi.fn(async (_id: string) => ({ success: true }))
const getAppearance = vi.fn(async (id: string): Promise<InstalledAppearance | null> => ({
  ...appearance,
  id,
}))
let themeConfigCallback: ((config: unknown) => void) | undefined

const storage = new Map<string, string>()
const rootStyle = { setProperty: vi.fn<(property: string, value: string) => void>() }
const rootClassList = {
  add: vi.fn(),
  remove: vi.fn(),
}

vi.stubGlobal('localStorage', {
  getItem: (key: string) => storage.get(key) ?? null,
  setItem: (key: string, value: string) => storage.set(key, value),
  removeItem: (key: string) => storage.delete(key),
})
vi.stubGlobal('document', {
  createElement: () => ({ setAttribute: vi.fn() }),
  createElementNS: () => ({ setAttribute: vi.fn() }),
  getElementsByTagName: () => [],
  documentElement: { style: rootStyle, classList: rootClassList },
  body: {},
})
vi.stubGlobal('window', {
  matchMedia: () => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() }),
  electronAPI: {
    getLogger: () => ({ debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() }),
    loadConfig: async () => null,
    saveConfig,
    listAppearances,
    getAppearance,
    clearInvalidAppearance,
    removeAppearance,
    onAppearanceChanged: appearanceChanged,
    onThemeConfigChanged: (callback: (config: unknown) => void) => {
      themeConfigCallback = callback
      return () => undefined
    },
  },
})

const { useTheme } = await import('./useTheme')
const { default: ThemeTokenBridge } = await import('@/components/ThemeTokenBridge')

async function renderThemeTokens() {
  await renderToString(
    createSSRApp({
      render: () =>
        h(
          ConfigProvider,
          { theme: useTheme().antdTheme.value },
          {
            default: () => h(ThemeTokenBridge),
          }
        ),
    })
  )
}

describe('useTheme custom appearance persistence', () => {
  beforeEach(() => {
    saveConfig.mockClear()
    listAppearances.mockReset()
    listAppearances.mockResolvedValue([appearance])
    clearInvalidAppearance.mockReset()
    clearInvalidAppearance.mockResolvedValue({ success: true, cleared: true, appearanceId: null })
    removeAppearance.mockReset()
    removeAppearance.mockResolvedValue({ success: true })
    storage.clear()
    rootStyle.setProperty.mockClear()
    rootClassList.add.mockClear()
    rootClassList.remove.mockClear()
  })

  it('restores a valid package and falls back when the saved package is missing', async () => {
    const theme = useTheme()
    await theme.initTheme({ themeMode: 'light', themeColor: 'blue', appearanceId: 'demo' })
    expect(theme.appearanceId.value).toBe('demo')
    expect(theme.activeAppearance.value?.name).toBe('Demo')
    expect(theme.isDark.value).toBe(true)

    await theme.initTheme({ themeMode: 'dark', themeColor: 'blue', appearanceId: 'missing' })
    expect(theme.appearanceId.value).toBe(null)
    expect(theme.activeAppearance.value).toBe(null)
    expect(clearInvalidAppearance).toHaveBeenCalledWith('missing')
    expect(saveConfig).not.toHaveBeenCalled()
  })

  it('theme config echo reuses cached packages instead of re-listing them', async () => {
    const theme = useTheme()
    await theme.initTheme({ themeMode: 'light', themeColor: 'blue', appearanceId: null })
    listAppearances.mockClear()

    themeConfigCallback?.({ themeMode: 'light', themeColor: 'red', appearanceId: 'demo' })
    expect(theme.activeAppearance.value?.id).toBe('demo')
    themeConfigCallback?.({ themeMode: 'dark', themeColor: 'red', appearanceId: null })
    expect(theme.activeAppearance.value).toBe(null)
    expect(listAppearances).not.toHaveBeenCalled()

    themeConfigCallback?.({ themeMode: 'dark', themeColor: 'red', appearanceId: 'unknown' })
    expect(listAppearances).toHaveBeenCalledTimes(1)
    await vi.waitFor(() => expect(clearInvalidAppearance).toHaveBeenCalledWith('unknown'))
  })

  it('late invalid-package cleanup preserves another window selecting a valid package', async () => {
    let releaseCleanup!: (result: AppearanceCleanupResult) => void
    clearInvalidAppearance.mockReturnValueOnce(
      new Promise(resolve => {
        releaseCleanup = resolve
      })
    )
    listAppearances.mockResolvedValueOnce([])
    const theme = useTheme()
    const startup = theme.initTheme({
      themeMode: 'light',
      themeColor: 'blue',
      appearanceId: 'missing',
    })
    await vi.waitFor(() => expect(clearInvalidAppearance).toHaveBeenCalledWith('missing'))

    const other = { ...appearance, id: 'other' }
    listAppearances.mockResolvedValue([other])
    themeConfigCallback?.({ themeMode: 'light', themeColor: 'blue', appearanceId: 'other' })
    await theme.loadAppearances()
    releaseCleanup({ success: true, cleared: false, appearanceId: 'other' })
    await startup

    expect(theme.appearanceId.value).toBe('other')
    expect(theme.activeAppearance.value?.id).toBe('other')
    expect(saveConfig).not.toHaveBeenCalled()
  })

  it('an old cleanup response cannot clear a newer choice made in the same window', async () => {
    const theme = useTheme()
    await theme.initTheme({ themeMode: 'light', themeColor: 'blue', appearanceId: 'demo' })
    let releaseCleanup!: (result: AppearanceCleanupResult) => void
    clearInvalidAppearance.mockReturnValueOnce(
      new Promise(resolve => {
        releaseCleanup = resolve
      })
    )
    listAppearances.mockResolvedValueOnce([])
    const refreshing = theme.loadAppearances()
    await vi.waitFor(() => expect(clearInvalidAppearance).toHaveBeenCalledWith('demo'))

    await theme.setAppearance('other')
    releaseCleanup({ success: true, cleared: true, appearanceId: null })
    await refreshing

    expect(theme.appearanceId.value).toBe('other')
    expect(theme.activeAppearance.value?.id).toBe('other')
    expect(saveConfig).toHaveBeenCalledWith({ appearanceId: 'other' }, expect.any(Object))
    expect(saveConfig).not.toHaveBeenCalledWith({ appearanceId: null }, expect.any(Object))
  })

  it('finishing removal does not queue a null write after a newer package choice', async () => {
    const theme = useTheme()
    await theme.initTheme({ themeMode: 'light', themeColor: 'blue', appearanceId: 'demo' })
    let releaseRemoval!: (result: { success: boolean }) => void
    removeAppearance.mockReturnValueOnce(
      new Promise(resolve => {
        releaseRemoval = resolve
      })
    )
    const removal = theme.removeAppearance('demo')
    await theme.setAppearance('other')
    listAppearances.mockResolvedValue([{ ...appearance, id: 'other' }])
    releaseRemoval({ success: true })
    await removal

    expect(theme.appearanceId.value).toBe('other')
    expect(theme.activeAppearance.value?.id).toBe('other')
    expect(clearInvalidAppearance).not.toHaveBeenCalled()
    expect(saveConfig).not.toHaveBeenCalledWith({ appearanceId: null }, expect.any(Object))
  })

  it('persists applying and clearing a package while updating CSS variables', async () => {
    const theme = useTheme()
    await theme.initTheme({ themeMode: 'light', themeColor: 'blue', appearanceId: null })
    await theme.setAppearance('demo')
    await renderThemeTokens()
    expect(saveConfig).toHaveBeenCalledWith({ appearanceId: 'demo' }, expect.any(Object))
    expect(rootStyle.setProperty).toHaveBeenCalledWith('--ant-color-primary', expect.any(String))
    expect(rootStyle.setProperty).toHaveBeenCalledWith(
      '--app-appearance-cursor-pointer',
      'url("data:image/png;base64,AA==") 2 3, pointer'
    )
    expect(rootClassList.add).toHaveBeenCalledWith('appearance-cursor-custom')
    expect(rootClassList.add).toHaveBeenCalledWith('appearance-background-custom')
    expect(rootStyle.setProperty).toHaveBeenCalledWith('--app-appearance-background-opacity', '1')
    expect(rootStyle.setProperty).toHaveBeenCalledWith('--app-appearance-cursor-default', 'auto')
    expect(rootStyle.setProperty).toHaveBeenCalledWith('--app-appearance-cursor-text', 'text')

    await theme.setAppearance(null)
    expect(saveConfig).toHaveBeenCalledWith({ appearanceId: null }, expect.any(Object))
    expect(theme.activeAppearance.value).toBe(null)
    expect(rootStyle.setProperty).toHaveBeenCalledWith('--app-appearance-cursor-pointer', 'pointer')
    expect(rootClassList.remove).toHaveBeenCalledWith('appearance-cursor-custom')
    expect(rootClassList.remove).toHaveBeenCalledWith('appearance-background-custom')
    expect(rootStyle.setProperty).toHaveBeenCalledWith('--app-appearance-background-image', 'none')
  })

  it('uses the same final background and text tokens as ConfigProvider', async () => {
    const custom = {
      ...appearance,
      tokens: {
        colorPrimary: '#976300',
        colorBgLayout: '#eeeeaa',
        colorBgContainer: '#ffeecc',
        colorText: '#804000',
      },
    }
    listAppearances.mockResolvedValueOnce([custom])
    const theme = useTheme()
    await theme.initTheme({ themeMode: 'light', themeColor: 'blue', appearanceId: 'demo' })
    await renderThemeTokens()
    expect(rootStyle.setProperty).toHaveBeenCalledWith('--ant-color-bg-layout', '#eeeeaa')
    expect(rootStyle.setProperty).toHaveBeenCalledWith('--ant-color-bg-container', '#ffeecc')
    expect(rootStyle.setProperty).toHaveBeenCalledWith('--ant-color-text', '#804000')
    expect(rootStyle.setProperty).toHaveBeenCalledWith(
      '--app-appearance-surface-bg',
      'color-mix(in srgb, #ffeecc 72%, transparent)'
    )
  })

  it('uses native opaque surfaces for a color-only package', async () => {
    listAppearances.mockResolvedValueOnce([
      { ...appearance, backgroundUrl: undefined, tokens: { colorPrimary: '#976300' } },
    ])
    const theme = useTheme()
    await theme.initTheme({ themeMode: 'light', themeColor: 'blue', appearanceId: 'demo' })
    await renderThemeTokens()
    expect(rootClassList.remove).toHaveBeenCalledWith('appearance-background-custom')
    const container = rootStyle.setProperty.mock.calls
      .slice()
      .reverse()
      .find(([name]) => name === '--ant-color-bg-container')?.[1]
    expect(rootStyle.setProperty).toHaveBeenCalledWith('--app-appearance-surface-bg', container)
  })

  it('falls back to the built-in mode when package listing fails', async () => {
    listAppearances.mockRejectedValueOnce(new Error('appearance directory unavailable'))
    const theme = useTheme()

    await expect(
      theme.initTheme({ themeMode: 'dark', themeColor: 'blue', appearanceId: 'demo' })
    ).resolves.toBeUndefined()
    expect(theme.appearanceId.value).toBe('demo')
    expect(theme.activeAppearance.value).toBe(null)
    expect(theme.isDark.value).toBe(true)
  })

  it('clears the active package when another window selects a built-in mode', async () => {
    const theme = useTheme()
    await theme.initTheme({ themeMode: 'light', themeColor: 'blue', appearanceId: 'demo' })
    expect(theme.activeAppearance.value?.id).toBe('demo')

    themeConfigCallback?.({ themeMode: 'light', themeColor: 'blue', appearanceId: null })
    await Promise.resolve()

    expect(theme.appearanceId.value).toBe(null)
    expect(theme.activeAppearance.value).toBe(null)
    expect(theme.isDark.value).toBe(false)
  })

  it('keeps the latest theme state when concurrent persistence fails', async () => {
    const theme = useTheme()
    await theme.initTheme({ themeMode: 'light', themeColor: 'blue', appearanceId: null })
    saveConfig.mockRejectedValueOnce(new Error('first write failed'))
    saveConfig.mockRejectedValueOnce(new Error('second write failed'))

    await Promise.allSettled([theme.setThemeMode('dark'), theme.setThemeMode('light')])

    expect(theme.themeMode.value).toBe('light')
    expect(theme.isDark.value).toBe(false)
  })

  it('uses the first successful write as the rollback base when the second fails', async () => {
    const theme = useTheme()
    await theme.initTheme({ themeMode: 'light', themeColor: 'blue', appearanceId: null })
    saveConfig.mockResolvedValueOnce(undefined)
    saveConfig.mockRejectedValueOnce(new Error('second write failed'))

    await Promise.allSettled([theme.setThemeMode('dark'), theme.setThemeMode('light')])

    expect(theme.themeMode.value).toBe('dark')
    expect(theme.isDark.value).toBe(true)
  })

  it('keeps the second successful write when the first fails', async () => {
    const theme = useTheme()
    await theme.initTheme({ themeMode: 'light', themeColor: 'blue', appearanceId: null })
    saveConfig.mockRejectedValueOnce(new Error('first write failed'))
    saveConfig.mockResolvedValueOnce(undefined)

    await Promise.allSettled([theme.setThemeMode('dark'), theme.setThemeMode('light')])

    expect(theme.themeMode.value).toBe('light')
    expect(theme.isDark.value).toBe(false)
  })

  it('rolls back a failed mode before saving a different theme field', async () => {
    const theme = useTheme()
    await theme.initTheme({ themeMode: 'system', themeColor: 'blue', appearanceId: null })
    saveConfig.mockRejectedValueOnce(new Error('mode write failed'))
    saveConfig.mockResolvedValueOnce(undefined)

    await Promise.allSettled([theme.setThemeMode('dark'), theme.setThemeColor('green')])

    expect(theme.themeMode.value).toBe('system')
    expect(theme.themeColor.value).toBe('green')
    expect(theme.isDark.value).toBe(false)
  })
})
