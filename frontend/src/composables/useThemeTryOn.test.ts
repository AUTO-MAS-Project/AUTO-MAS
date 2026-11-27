import { beforeEach, describe, expect, it, vi } from 'vite-plus/test'
import type { InstalledAppearance } from '@/types/appearance'

const saveConfigMock = vi.fn((..._args: unknown[]) => Promise.resolve())
const getConfigMock = vi.fn(() =>
  Promise.resolve({ themeMode: 'light', themeColor: 'blue', appearanceId: 'orig-theme' })
)

const origAppearance: InstalledAppearance = {
  formatVersion: 1,
  id: 'orig-theme',
  name: 'Original Theme',
  mode: 'light',
  tokens: { colorPrimary: '#1677ff' },
}

const tryOnA: InstalledAppearance = {
  formatVersion: 1,
  id: 'try-a',
  name: 'Try-On Dark A',
  mode: 'dark',
  tokens: { colorPrimary: '#e11d48' },
}

const tryOnB: InstalledAppearance = {
  formatVersion: 1,
  id: 'try-b',
  name: 'Try-On Light B',
  mode: 'light',
  tokens: { colorPrimary: '#10b981' },
}

vi.mock('@/utils/config', () => ({
  getConfig: () => getConfigMock(),
  saveConfig: (...args: unknown[]) => saveConfigMock(...args),
}))

vi.mock('@/utils/preferenceAnalytics', () => ({
  observePreference: (_key: string, _val: string, run: () => Promise<void>) => run(),
}))

vi.mock('@/utils/featureAnalytics', () => ({
  observeFeature: (_event: string, _props: unknown, run: () => Promise<void>) => run(),
}))

function installDomStubs(): void {
  const classSet = new Set<string>()
  const styleProps = new Map<string, string>()
  const root = {
    classList: {
      add: (cls: string) => classSet.add(cls),
      remove: (cls: string) => classSet.delete(cls),
      toggle: (cls: string, force?: boolean) => {
        if (force === undefined) {
          if (classSet.has(cls)) classSet.delete(cls)
          else classSet.add(cls)
        } else if (force) classSet.add(cls)
        else classSet.delete(cls)
      },
      contains: (cls: string) => classSet.has(cls),
    },
    style: {
      setProperty: (key: string, val: string) => styleProps.set(key, val),
      getPropertyValue: (key: string) => styleProps.get(key) ?? '',
      removeProperty: (key: string) => styleProps.delete(key),
    },
  }
  ;(globalThis as unknown as Record<string, unknown>).document = {
    documentElement: root,
    createElement: () => ({ style: {} }),
    getElementsByTagName: () => [],
  }
  ;(globalThis as unknown as Record<string, unknown>).window = {
    matchMedia: () => ({
      matches: false,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
    }),
    electronAPI: {
      getLogger: () => ({ info: () => undefined, warn: () => undefined, error: () => undefined }),
      listAppearances: () => Promise.resolve([origAppearance]),
      getAppearance: (id: string) =>
        Promise.resolve(id === origAppearance.id ? origAppearance : null),
      onAppearanceChanged: () => () => undefined,
      onThemeConfigChanged: () => () => undefined,
    },
  }
}

describe('useTheme try-on sandbox boundaries', () => {
  beforeEach(() => {
    vi.resetModules()
    saveConfigMock.mockClear()
    installDomStubs()
  })

  it('连续试穿多个主题不写盘，按住对比始终对照本机原外观，退出后完整还原', async () => {
    const { useTheme } = await import('./useTheme')
    const theme = useTheme()
    await theme.initTheme()

    expect(theme.persistedAppearance.value?.id).toBe('orig-theme')
    expect(theme.activeAppearance.value?.id).toBe('orig-theme')
    expect(theme.isDark.value).toBe(false)

    // 连续试穿 A → B
    theme.startAppearanceTryOn(tryOnA)
    expect(theme.activeAppearance.value?.id).toBe('try-a')
    expect(theme.isDark.value).toBe(true)
    expect(theme.persistedAppearance.value?.id).toBe('orig-theme')

    theme.startAppearanceTryOn(tryOnB)
    expect(theme.activeAppearance.value?.id).toBe('try-b')
    expect(theme.isDark.value).toBe(false)
    expect(theme.persistedAppearance.value?.id).toBe('orig-theme')

    // 按住对比始终回到本机原外观 orig-theme（不是 tryOnA）
    theme.setAppearanceTryOnCompare(true)
    expect(theme.activeAppearance.value?.id).toBe('orig-theme')
    theme.setAppearanceTryOnCompare(false)
    expect(theme.activeAppearance.value?.id).toBe('try-b')

    // 退出试穿恢复原外观
    theme.stopAppearanceTryOn()
    expect(theme.tryOnAppearance.value).toBeNull()
    expect(theme.activeAppearance.value?.id).toBe('orig-theme')

    // 全程零落盘
    expect(saveConfigMock).not.toHaveBeenCalled()
  })
})
