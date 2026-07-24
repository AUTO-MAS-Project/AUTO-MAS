import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// 用 hoisted 句柄让 vi.mock 工厂可以引用到同一个 mock 函数，
// 测试体里再按需控制它的返回值。
const fetchMock = vi.hoisted(() => vi.fn())

vi.mock('@/utils/httpSecurity', () => ({
  authenticatedApiFetch: fetchMock,
}))

vi.mock('@/api', () => ({
  OpenAPI: { BASE: 'http://localhost:36163' },
}))

interface ImageInstance {
  onload: (() => void) | null
  onerror: (() => void) | null
  decoding: string
  src: string
}

// 模拟成功解码的 Image：设置 src 后在下一个 microtask 触发 onload。
const stubImageSuccess = (): ImageInstance[] => {
  vi.stubGlobal(
    'Image',
    class FakeImage {
      onload: (() => void) | null = null
      onerror: (() => void) | null = null
      decoding = ''
      private _src = ''
      get src() {
        return this._src
      }
      set src(value: string) {
        this._src = value
        queueMicrotask(() => this.onload?.())
      }
    }
  )
  return []
}

const okResponse = (payload: unknown) => ({
  ok: true,
  status: 200,
  json: async () => payload,
})

const logger = { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() }

const loadUseAppBackground = async () => {
  vi.resetModules()
  vi.stubGlobal('window', {
    electronAPI: { getLogger: () => logger },
  })
  return await import('./useAppBackground')
}

describe('useAppBackground cssVars surface', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    fetchMock.mockReset()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('exposes all eleven CSS variables derived from the default background', async () => {
    const { useAppBackground } = await loadUseAppBackground()
    const { cssVars } = useAppBackground()
    const keys = Object.keys(cssVars.value)

    expect(keys).toHaveLength(11)
    expect(keys).toContain('--app-background-image')
    expect(keys).toContain('--app-background-blur')
    expect(keys).toContain('--app-background-brightness')
    expect(keys).toContain('--app-background-opacity')
    expect(keys).toContain('--app-background-overlay-opacity')
    expect(keys).toContain('--app-background-card-opacity')
    expect(keys).toContain('--app-background-panel-opacity')
    expect(keys).toContain('--app-background-elevated-opacity')
    expect(keys).toContain('--app-background-sider-opacity')
    expect(keys).toContain('--app-background-position')
    expect(keys).toContain('--app-background-size')
    expect(cssVars.value['--app-background-image']).toBe('none')
  })
})

describe('useAppBackground loadBackground success and fallback', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    fetchMock.mockReset()
    stubImageSuccess()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('loads a safe plugin background and reflects it in cssVars', async () => {
    fetchMock.mockResolvedValueOnce(
      okResponse({
        enabled: true,
        image_url: '/api/plugins/frontend/background/image?success',
        blur_px: 8,
        opacity: 80,
      })
    )
    const { useAppBackground } = await loadUseAppBackground()
    const bg = useAppBackground()

    await bg.loadBackground()

    expect(fetchMock).toHaveBeenCalledOnce()
    expect(bg.background.value.enabled).toBe(true)
    expect(bg.background.value.source).toBe('plugin')
    expect(bg.background.value.imageUrl).toBe(
      'http://localhost:36163/api/plugins/frontend/background/image?success'
    )
    expect(bg.cssVars.value['--app-background-image']).toContain('image?success')
    expect(bg.cssVars.value['--app-background-blur']).toBe('8px')
    expect(bg.cssVars.value['--app-background-opacity']).toBe('0.8')
    expect(bg.loaded.value).toBe(true)
  })

  it('falls back to the default surface when the request throws', async () => {
    fetchMock.mockRejectedValueOnce(new Error('network down'))
    const { useAppBackground } = await loadUseAppBackground()
    const bg = useAppBackground()

    await bg.loadBackground()

    expect(bg.background.value.enabled).toBe(false)
    expect(bg.background.value.source).toBe('default')
    expect(bg.background.value.imageUrl).toBe('')
    expect(bg.loaded.value).toBe(true)
  })

  it('falls back to the default surface when the backend reports an error status', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 500,
      json: async () => ({ message: 'backend error' }),
    })
    const { useAppBackground } = await loadUseAppBackground()
    const bg = useAppBackground()

    await bg.loadBackground()

    expect(bg.background.value.enabled).toBe(false)
    expect(bg.background.value.source).toBe('default')
  })
})

describe('useAppBackground loadBackground race protection', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    fetchMock.mockReset()
    stubImageSuccess()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('keeps the newest response and ignores a stale in-flight response', async () => {
    let resolveFirst!: (response: unknown) => void
    const firstResponse = new Promise(resolve => {
      resolveFirst = resolve
    })
    fetchMock.mockImplementationOnce(async () => firstResponse)
    fetchMock.mockImplementationOnce(async () =>
      okResponse({
        enabled: true,
        image_url: '/api/plugins/frontend/background/image?new',
      })
    )

    const { useAppBackground } = await loadUseAppBackground()
    const bg = useAppBackground()

    const firstCall = bg.loadBackground()
    const secondCall = bg.loadBackground()

    await secondCall
    expect(bg.background.value.imageUrl).toContain('image?new')

    resolveFirst(
      okResponse({
        enabled: true,
        image_url: '/api/plugins/frontend/background/image?stale',
      })
    )
    await firstCall

    expect(bg.background.value.imageUrl).toContain('image?new')
    expect(bg.background.value.imageUrl).not.toContain('stale')
  })
})
