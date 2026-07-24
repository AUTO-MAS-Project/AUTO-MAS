import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// ant-design-vue 仅在 antdTheme computed 中使用 theme.darkAlgorithm/defaultAlgorithm，
// 这里替换为稳定占位，避免在 node 测试环境中拉起完整 AntD 运行时。
vi.mock('ant-design-vue', () => ({
  theme: { darkAlgorithm: 'dark-algorithm', defaultAlgorithm: 'default-algorithm' },
}))

interface DomStub {
  window: { matchMedia: ReturnType<typeof vi.fn> }
  document: Document
  localStorage: Storage
  styleMap: Map<string, string>
  dataset: Record<string, string>
  classSet: Set<string>
  storage: Map<string, string>
  mediaHandlers: Array<() => void>
}

const createDomStub = (prefersDark: boolean): DomStub => {
  const styleMap = new Map<string, string>()
  const dataset: Record<string, string> = {}
  const classSet = new Set<string>()
  const mediaHandlers: Array<() => void> = []
  const storage = new Map<string, string>()

  const documentElement = {
    classList: {
      add: (cls: string) => {
        classSet.add(cls)
      },
      remove: (cls: string) => {
        classSet.delete(cls)
      },
      contains: (cls: string) => classSet.has(cls),
    },
    style: {
      setProperty: (key: string, value: string) => {
        styleMap.set(key, value)
      },
      getPropertyValue: (key: string) => styleMap.get(key) ?? '',
    },
    dataset,
  } as unknown as HTMLElement

  // Vue runtime-dom 在模块加载时执行 doc.createElement("template")，
  // 必须提供 createElement/createTextNode/createComment 以满足其能力检测。
  const createFakeElement = () => ({
    content: {},
    style: { setProperty: vi.fn(), getPropertyValue: vi.fn() },
    setAttribute: vi.fn(),
    removeAttribute: vi.fn(),
    appendChild: vi.fn(),
    removeChild: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    classList: { add: vi.fn(), remove: vi.fn(), contains: () => false },
    dataset: {},
    tagName: 'TEMPLATE',
    parentNode: null,
  })

  const documentStub = {
    documentElement,
    createElement: vi.fn(() => createFakeElement()),
    createElementNS: vi.fn(() => createFakeElement()),
    createTextNode: vi.fn(() => ({})),
    createComment: vi.fn(() => ({})),
    querySelector: vi.fn(() => null),
  } as unknown as Document

  const matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: /dark/.test(query) ? prefersDark : false,
    addEventListener: (_event: string, handler: () => void) => {
      mediaHandlers.push(handler)
    },
    removeEventListener: vi.fn(),
  }))

  const localStorageStub = {
    getItem: (key: string) => storage.get(key) ?? null,
    setItem: (key: string, value: string) => {
      storage.set(key, value)
    },
    removeItem: (key: string) => {
      storage.delete(key)
    },
    clear: () => {
      storage.clear()
    },
  } as unknown as Storage

  return {
    window: { matchMedia },
    document: documentStub,
    localStorage: localStorageStub,
    styleMap,
    dataset,
    classSet,
    storage,
    mediaHandlers,
  }
}

const loadUseTheme = async (stub: DomStub) => {
  vi.resetModules()
  vi.stubGlobal('window', stub.window)
  vi.stubGlobal('document', stub.document)
  vi.stubGlobal('localStorage', stub.localStorage)
  const mod = await import('./useTheme')
  // watch 默认 flush:'pre' 异步，需要返回 nextTick 供测试 await
  const { nextTick } = await import('vue')
  return { ...mod, nextTick }
}

const parseHex = (hex: string) => {
  const match = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex)
  if (!match) return null
  return {
    r: parseInt(match[1], 16),
    g: parseInt(match[2], 16),
    b: parseInt(match[3], 16),
  }
}

const luminance = (hex: string) => {
  const rgb = parseHex(hex)
  if (!rgb) return 0
  const transform = (v: number) => {
    const srgb = v / 255
    return srgb <= 0.03928 ? srgb / 12.92 : Math.pow((srgb + 0.055) / 1.055, 2.4)
  }
  return 0.2126 * transform(rgb.r) + 0.7152 * transform(rgb.g) + 0.0722 * transform(rgb.b)
}

const contrastRatio = (hex1: string, hex2: string) => {
  const l1 = luminance(hex1)
  const l2 = luminance(hex2)
  const light = Math.max(l1, l2)
  const dark = Math.min(l1, l2)
  return (light + 0.05) / (dark + 0.05)
}

const textToHex = (rgba: string) => (rgba.includes('255,255,255') ? '#ffffff' : '#000000')

describe('useTheme dark/light switching', () => {
  let stub: DomStub

  beforeEach(() => {
    stub = createDomStub(false)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('marks the document as dark when the system prefers dark at import time', async () => {
    stub = createDomStub(true)
    const { useTheme } = await loadUseTheme(stub)
    const theme = useTheme()

    expect(theme.isDark.value).toBe(true)
    expect(stub.dataset.theme).toBe('dark')
    expect(stub.classSet.has('dark')).toBe(true)
  })

  it('switches to light and back to dark via setThemeMode', async () => {
    const { useTheme, nextTick } = await loadUseTheme(stub)
    const theme = useTheme()

    theme.setThemeMode('dark')
    await nextTick()
    expect(theme.isDark.value).toBe(true)
    expect(stub.dataset.theme).toBe('dark')

    theme.setThemeMode('light')
    await nextTick()
    expect(theme.isDark.value).toBe(false)
    expect(stub.dataset.theme).toBe('light')
    expect(stub.classSet.has('dark')).toBe(false)
  })
})

describe('useTheme accessible color derivation', () => {
  let stub: DomStub

  beforeEach(() => {
    stub = createDomStub(false)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('picks a light menu text on the dark sider background and clears the 4.5 contrast bar', async () => {
    stub = createDomStub(true)
    const { useTheme } = await loadUseTheme(stub)
    const theme = useTheme()

    theme.setThemeMode('dark')
    const siderBg = stub.styleMap.get('--app-sider-bg') ?? ''
    const menuText = stub.styleMap.get('--app-menu-text-color') ?? ''

    expect(siderBg).toMatch(/^#[0-9a-f]{6}$/i)
    expect(menuText).toContain('255,255,255')
    expect(contrastRatio(textToHex(menuText), siderBg)).toBeGreaterThanOrEqual(4.5)
  })

  it('picks a dark menu text on the light sider background and clears the 4.5 contrast bar', async () => {
    const { useTheme } = await loadUseTheme(stub)
    const theme = useTheme()

    theme.setThemeMode('light')
    const siderBg = stub.styleMap.get('--app-sider-bg') ?? ''
    const menuText = stub.styleMap.get('--app-menu-text-color') ?? ''
    const siderBorder = stub.styleMap.get('--app-sider-border-color') ?? ''

    expect(siderBg).toMatch(/^#[0-9a-f]{6}$/i)
    expect(siderBorder).toMatch(/^#[0-9a-f]{6}$/i)
    expect(menuText).toContain('0,0,0')
    expect(contrastRatio(textToHex(menuText), siderBg)).toBeGreaterThanOrEqual(4.5)
  })
})

describe('useTheme persistence and scaling', () => {
  let stub: DomStub

  beforeEach(() => {
    stub = createDomStub(false)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('clamps the UI scale, persists preferences and reflects the primary color', async () => {
    const { useTheme, nextTick } = await loadUseTheme(stub)
    const theme = useTheme()

    theme.setUiScale(2)
    await nextTick()
    expect(theme.uiScale.value).toBe(1.4)
    expect(stub.storage.get('ui-scale')).toBe('1.4')
    expect(stub.dataset.uiScale).toBe('1.4')

    theme.setThemeColor('red')
    await nextTick()
    expect(theme.themeColor.value).toBe('red')
    expect(stub.storage.get('theme-color')).toBe('red')
    expect(stub.styleMap.get('--ant-color-primary')).toBe('#ff4d4f')
  })

  it('restores saved preferences and the explicit perf mode in initTheme', async () => {
    stub.storage.set('theme-mode', 'dark')
    stub.storage.set('theme-color', 'green')
    stub.storage.set('ui-scale', '1.2')
    stub.storage.set('perf-mode', 'low')

    const { useTheme } = await loadUseTheme(stub)
    const theme = useTheme()
    theme.initTheme()

    expect(theme.themeMode.value).toBe('dark')
    expect(theme.themeColor.value).toBe('green')
    expect(theme.uiScale.value).toBe(1.2)
    expect(theme.perfMode.value).toBe('low')
    expect(stub.dataset.perfMode).toBe('low')
  })

  it('restores auto perf detection when setPerfMode receives null', async () => {
    const { useTheme } = await loadUseTheme(stub)
    const theme = useTheme()

    theme.setPerfMode('low')
    expect(stub.storage.get('perf-mode')).toBe('low')

    theme.setPerfMode(null)
    expect(stub.storage.has('perf-mode')).toBe(false)
    expect(theme.perfMode.value).toBe('normal')
    expect(stub.dataset.perfMode).toBe('normal')
  })
})
