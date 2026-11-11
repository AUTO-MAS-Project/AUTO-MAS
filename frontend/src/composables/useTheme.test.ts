import type { InstalledAppearance } from '@/types/appearance'
import { readability } from '@ctrl/tinycolor'
import { theme } from 'ant-design-vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vite-plus/test'

vi.mock('@/utils/config', () => ({ getConfig: vi.fn(), saveConfig: vi.fn() }))
vi.mock('@/utils/preferenceAnalytics', () => ({ observePreference: vi.fn() }))
vi.mock('@/utils/featureAnalytics', () => ({ observeFeature: vi.fn() }))

let appearance: InstalledAppearance

beforeEach(() => {
  vi.resetModules()
  appearance = {
    formatVersion: 1,
    id: 'mixed-surfaces',
    name: 'Mixed surfaces',
    mode: 'light',
    tokens: {
      colorPrimary: '#00f700',
      colorBgLayout: '#000000',
      colorBgContainer: '#ffffff',
      colorBgElevated: '#ffffff',
    },
    background: { path: 'assets/black.png', surfaceOpacity: 0 },
    backgroundUrl:
      'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGD4DwABBAEAX+XDSwAAAABJRU5ErkJggg==',
  }
  const properties = new Map<string, string>()
  vi.stubGlobal('document', {
    documentElement: {
      classList: { add: vi.fn(), remove: vi.fn(), toggle: vi.fn() },
      style: {
        setProperty: (name: string, value: string) => properties.set(name, value),
        getPropertyValue: (name: string) => properties.get(name) ?? '',
        removeProperty: (name: string) => properties.delete(name),
      },
    },
  })
  vi.stubGlobal('window', {
    matchMedia: () => ({ matches: false, addEventListener: vi.fn() }),
    electronAPI: {
      getLogger: () => ({ warn: vi.fn(), error: vi.fn() }),
      listAppearances: async () => [appearance],
    },
  })
})

afterEach(() => vi.unstubAllGlobals())

async function themeTokens(mode: 'light' | 'dark', appearanceId: string | null = appearance.id) {
  const { useTheme } = await import('./useTheme')
  const state = useTheme()
  await state.initTheme({ themeMode: mode, appearanceId })
  const config = state.antdTheme.value
  return { ...config.algorithm({ ...theme.defaultSeed, ...config.token }), ...config.token }
}

describe('theme link contrast', () => {
  it.each(['#00f700', '#003300'])('finds the shared black/white range from %s', async primary => {
    appearance.tokens.colorPrimary = primary
    const tokens = await themeTokens('light')
    for (const color of [tokens.colorLink, tokens.colorLinkHover, tokens.colorLinkActive]) {
      expect(readability(color, '#000000')).toBeGreaterThanOrEqual(4.5)
      expect(readability(color, '#ffffff')).toBeGreaterThanOrEqual(4.5)
    }
  })

  it.each(['light', 'dark'] as const)('keeps built-in %s links readable', async mode => {
    const tokens = await themeTokens(mode, null)
    for (const color of [tokens.colorLink, tokens.colorLinkHover, tokens.colorLinkActive]) {
      for (const background of [
        tokens.colorBgLayout,
        tokens.colorBgContainer,
        tokens.colorBgElevated,
      ]) {
        expect(readability(color, background)).toBeGreaterThanOrEqual(4.5)
      }
    }
  })
})

describe('cursor size across windows', () => {
  it('updates an already open log window and keeps newer local previews until save completes', async () => {
    const listeners: ((config: { cursorSizePx: number | null }) => void)[] = []
    const { saveConfig } = await import('@/utils/config')
    const { observePreference } = await import('@/utils/preferenceAnalytics')
    vi.mocked(observePreference).mockImplementation((_kind, _preset, save) => save())
    vi.mocked(saveConfig).mockImplementation(async patch => {
      for (const listener of listeners) listener({ cursorSizePx: patch.cursorSizePx ?? null })
    })
    Object.assign(window.electronAPI, {
      onThemeConfigChanged: (listener: (typeof listeners)[number]) => listeners.push(listener),
    })

    vi.useFakeTimers()
    try {
      const main = (await import('./useTheme')).useTheme()
      await main.initTheme({ cursorSizePx: 24 })
      vi.resetModules()
      const logs = (await import('./useTheme')).useTheme()
      await logs.initTheme({ cursorSizePx: 24 })
      const onError = vi.fn()

      main.previewCursorSize(48, onError)
      expect(main.cursorSizePx.value).toBe(48)
      expect(logs.cursorSizePx.value).toBe(24)
      await vi.advanceTimersByTimeAsync(300)
      expect(logs.cursorSizePx.value).toBe(48)

      main.previewCursorSize(null, onError)
      await vi.advanceTimersByTimeAsync(300)
      expect(main.cursorSizePx.value).toBeNull()
      expect(logs.cursorSizePx.value).toBeNull()

      main.previewCursorSize(32, onError)
      await saveConfig({ cursorSizePx: 48 })
      expect(main.cursorSizePx.value).toBe(32)
      expect(logs.cursorSizePx.value).toBe(48)
      vi.mocked(saveConfig).mockRejectedValueOnce(new Error('write failed'))
      await vi.advanceTimersByTimeAsync(300)
      expect(main.cursorSizePx.value).toBe(48)
      expect(onError).toHaveBeenCalledOnce()
    } finally {
      vi.useRealTimers()
    }
  })
})
