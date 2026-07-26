import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

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

const stubImageFail = (): ImageInstance[] => {
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
        queueMicrotask(() => this.onerror?.())
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

function createMockIndexedDB() {
  const store: Record<string, string> = {}
  const createdStores = new Set<string>()
  const mockStore = {
    put: vi.fn((value: string, key: string) => {
      store[key] = value
      const req = {
        onsuccess: null as (() => void) | null,
        onerror: null as (() => void) | null,
      }
      queueMicrotask(() => req.onsuccess?.())
      return req
    }),
    get: vi.fn((key: string) => {
      const req = {
        onsuccess: null as ((e: { target: { result: string | undefined } }) => void) | null,
        onerror: null as (() => void) | null,
      }
      queueMicrotask(() => req.onsuccess?.({ target: { result: store[key] } }))
      return req
    }),
    delete: vi.fn((key: string) => {
      delete store[key]
      const req = {
        onsuccess: null as (() => void) | null,
        onerror: null as (() => void) | null,
      }
      queueMicrotask(() => req.onsuccess?.())
      return req
    }),
  }
  const mockTx = {
    oncomplete: null as (() => void) | null,
    onerror: null as ((e: Event) => void) | null,
    objectStore: vi.fn(() => {
      queueMicrotask(() => mockTx.oncomplete?.())
      return mockStore
    }),
  }
  const mockDB = {
    transaction: vi.fn(() => mockTx),
    objectStoreNames: {
      contains: vi.fn((name: string) => createdStores.has(name)),
    },
    createObjectStore: vi.fn((name: string) => {
      createdStores.add(name)
      return mockStore
    }),
    close: vi.fn(),
  }
  const mockOpenRequest = {
    onupgradeneeded: null as (() => void) | null,
    onsuccess: null as ((e: { target: { result: typeof mockDB } }) => void) | null,
    onerror: null as (() => void) | null,
    error: null,
    result: mockDB,
  }

  vi.stubGlobal('indexedDB', {
    open: vi.fn(() => {
      queueMicrotask(() => {
        mockOpenRequest.onupgradeneeded?.()
        mockOpenRequest.onsuccess?.({ target: { result: mockDB } })
      })
      return mockOpenRequest
    }),
  })

  return { store, mockStore }
}

const loadUseAppBackground = async () => {
  vi.resetModules()
  vi.stubGlobal('window', {
    electronAPI: { getLogger: () => logger },
  })
  const storageMock: Record<string, string> = {}
  vi.stubGlobal('localStorage', {
    getItem: vi.fn((key: string) => storageMock[key] ?? null),
    setItem: vi.fn((key: string, value: string) => {
      storageMock[key] = value
    }),
    removeItem: vi.fn((key: string) => {
      delete storageMock[key]
    }),
  })
  createMockIndexedDB()
  return await import('./useAppBackground')
}

describe('useAppBackground cssVars surface', () => {
  beforeEach(async () => {
    vi.clearAllMocks()
    fetchMock.mockReset()
    stubImageSuccess()
    fetchMock.mockResolvedValueOnce(okResponse({ enabled: false }))
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
  beforeEach(async () => {
    vi.clearAllMocks()
    fetchMock.mockReset()
    stubImageSuccess()
    fetchMock.mockResolvedValueOnce(okResponse({ enabled: false }))
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('loads a safe plugin background and reflects it in cssVars', async () => {
    const { useAppBackground } = await loadUseAppBackground()
    const bg = useAppBackground()
    await vi.waitUntil(() => bg.loaded.value === true)
    fetchMock.mockReset()

    fetchMock.mockResolvedValueOnce(
      okResponse({
        enabled: true,
        image_url: '/api/plugins/frontend/background/image?success',
        blur_px: 8,
        opacity: 80,
      })
    )

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
    const { useAppBackground } = await loadUseAppBackground()
    const bg = useAppBackground()
    await vi.waitUntil(() => bg.loaded.value === true)
    fetchMock.mockReset()

    fetchMock.mockRejectedValueOnce(new Error('network down'))
    await bg.loadBackground()

    expect(bg.background.value.enabled).toBe(false)
    expect(bg.background.value.source).toBe('default')
    expect(bg.background.value.imageUrl).toBe('')
    expect(bg.loaded.value).toBe(true)
  })

  it('falls back to the default surface when the backend reports an error status', async () => {
    const { useAppBackground } = await loadUseAppBackground()
    const bg = useAppBackground()
    await vi.waitUntil(() => bg.loaded.value === true)
    fetchMock.mockReset()

    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 500,
      json: async () => ({ message: 'backend error' }),
    })
    await bg.loadBackground()

    expect(bg.background.value.enabled).toBe(false)
    expect(bg.background.value.source).toBe('default')
  })
})

describe('useAppBackground loadBackground race protection', () => {
  beforeEach(async () => {
    vi.clearAllMocks()
    fetchMock.mockReset()
    stubImageSuccess()
    fetchMock.mockResolvedValueOnce(okResponse({ enabled: false }))
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('keeps the newest response and ignores a stale in-flight response', async () => {
    const { useAppBackground } = await loadUseAppBackground()
    const bg = useAppBackground()
    await vi.waitUntil(() => bg.loaded.value === true)
    fetchMock.mockReset()

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

describe('useAppBackground selectLocalImage with IndexedDB persistence', () => {
  beforeEach(async () => {
    vi.clearAllMocks()
    fetchMock.mockReset()
    stubImageSuccess()
    fetchMock.mockResolvedValueOnce(okResponse({ enabled: false }))
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('saves user image to IndexedDB (not localStorage) and enables background', async () => {
    const { useAppBackground } = await loadUseAppBackground()
    const bg = useAppBackground()
    await vi.waitUntil(() => bg.loaded.value === true)

    const testDataUrl = 'data:image/png;base64,testimage123'
    class MockFileReader {
      onload: (() => void) | null = null
      onerror: (() => void) | null = null
      result = testDataUrl
      readAsDataURL = vi.fn(function (this: MockFileReader) {
        queueMicrotask(() => this.onload?.())
      })
    }
    vi.stubGlobal('FileReader', MockFileReader)

    const fakeFile = {
      name: 'test.png',
      type: 'image/png',
      size: 1024,
      lastModified: Date.now(),
      slice: () => new Blob(),
      arrayBuffer: async () => new ArrayBuffer(0),
      stream: () => new ReadableStream(),
      text: async () => '',
    } as File

    const result = await bg.selectLocalImage(fakeFile)
    expect(result.success).toBe(true)
    expect(bg.background.value.enabled).toBe(true)
    expect(bg.background.value.source).toBe('user')
    expect(bg.background.value.imageUrl).toBe(testDataUrl)

    const storedSettings = JSON.parse(
      (localStorage.setItem as ReturnType<typeof vi.fn>).mock.calls.find(
        (c: unknown[]) => c[0] === 'v6-user-background'
      )?.[1] ?? '{}'
    )
    expect(storedSettings.enabled).toBe(true)
    expect(storedSettings.source).toBe('user')
    expect(storedSettings.imageDataUrl).toBeUndefined()
  })
})
