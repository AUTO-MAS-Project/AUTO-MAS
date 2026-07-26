import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  resolveAppBackground,
  resolveLoadableAppBackground,
  resolveSafeBackgroundUrl,
  validateImageFile,
  saveUserBackgroundSettings,
  loadUserBackgroundSettings,
  clearUserBackgroundSettings,
  saveUserBackgroundImage,
  loadUserBackgroundImage,
  loadUserBackgroundSettingsWithImage,
  clearUserBackgroundImage,
  fileToDataUrl,
  DEFAULT_BACKGROUND_SETTINGS,
} from './background'

const API_BASE = 'http://127.0.0.1:36163'

describe('background source contract', () => {
  it('prefers a user background and falls back through plugin to the default surface', () => {
    const resolved = resolveAppBackground(
      {
        user: { enabled: true, image_url: '/api/settings/frontend/background/image' },
        plugin: { enabled: true, image_url: '/api/plugins/frontend/background/image' },
      },
      API_BASE
    )

    expect(resolved.source).toBe('user')
    expect(resolved.imageUrl).toBe('http://127.0.0.1:36163/api/settings/frontend/background/image')
  })

  it('rejects filesystem, cross-origin and non-API paths', () => {
    expect(resolveSafeBackgroundUrl('file:///C:/Users/example/background.png', API_BASE)).toBe('')
    expect(resolveSafeBackgroundUrl('https://example.com/background.png', API_BASE)).toBe('')
    expect(resolveSafeBackgroundUrl('../../private/background.png', API_BASE)).toBe('')
    expect(resolveSafeBackgroundUrl('javascript:alert(1)', API_BASE)).toBe('')

    const resolved = resolveAppBackground(
      { enabled: true, image_url: 'C:\\Users\\example\\background.png' },
      API_BASE
    )
    expect(resolved.source).toBe('default')
    expect(resolved.enabled).toBe(false)
    expect(resolved.fallbackReason).toBe('unsafe-url')
  })

  it('drops to the default surface when a plugin is uninstalled or disabled', () => {
    const installed = resolveAppBackground(
      { enabled: true, image_url: '/api/plugins/frontend/background/image?v=1' },
      API_BASE
    )
    const uninstalled = resolveAppBackground({ enabled: false, image_url: null }, API_BASE)

    expect(installed.source).toBe('plugin')
    expect(installed.enabled).toBe(true)
    expect(uninstalled.source).toBe('default')
    expect(uninstalled.enabled).toBe(false)
    expect(uninstalled.imageUrl).toBe('')
  })

  it('falls back without blocking the shell when an otherwise safe image fails to decode', async () => {
    const imageLoader = vi.fn().mockResolvedValue(false)
    const resolved = await resolveLoadableAppBackground(
      { enabled: true, image_url: '/api/plugins/frontend/background/image?v=2' },
      API_BASE,
      null,
      imageLoader
    )

    expect(imageLoader).toHaveBeenCalledOnce()
    expect(resolved.source).toBe('default')
    expect(resolved.enabled).toBe(false)
    expect(resolved.fallbackReason).toBe('image-load-failed')
  })
})

describe('resolveSafeBackgroundUrl boundary rules', () => {
  it('accepts same-origin http and https API paths and normalizes them', () => {
    expect(resolveSafeBackgroundUrl('/api/plugins/frontend/background/image.png', API_BASE)).toBe(
      'http://127.0.0.1:36163/api/plugins/frontend/background/image.png'
    )
    expect(resolveSafeBackgroundUrl('/api/plugins/assets/bg.png', API_BASE)).toBe(
      'http://127.0.0.1:36163/api/plugins/assets/bg.png'
    )
    const httpsBase = 'https://localhost:36163'
    expect(resolveSafeBackgroundUrl('/api/frontend/background/image', httpsBase)).toBe(
      'https://localhost:36163/api/frontend/background/image'
    )
  })

  it('strips the fragment but keeps the query string', () => {
    const resolved = resolveSafeBackgroundUrl(
      '/api/plugins/frontend/background/image?token=abc#section',
      API_BASE
    )
    expect(resolved).toBe('http://127.0.0.1:36163/api/plugins/frontend/background/image?token=abc')
  })

  it('rejects URLs that carry credentials', () => {
    expect(
      resolveSafeBackgroundUrl(
        'http://user:pass@127.0.0.1:36163/api/plugins/assets/bg.png',
        API_BASE
      )
    ).toBe('')
  })

  it('rejects control characters and protocol-relative URLs', () => {
    expect(resolveSafeBackgroundUrl('/api/plugins/assets/bg.png\u0000', API_BASE)).toBe('')
    expect(resolveSafeBackgroundUrl('/api/plugins/assets/bg\t.png', API_BASE)).toBe('')
    expect(resolveSafeBackgroundUrl('//evil.example/api/plugins/assets/bg.png', API_BASE)).toBe('')
    expect(resolveSafeBackgroundUrl('/api/plugins/assets/bg.png\\x', API_BASE)).toBe('')
  })

  it('rejects same-origin paths outside the whitelist', () => {
    expect(resolveSafeBackgroundUrl('/api/plugins/reload', API_BASE)).toBe('')
    expect(resolveSafeBackgroundUrl('/static/bg.png', API_BASE)).toBe('')
    expect(resolveSafeBackgroundUrl('/api/unknown/background', API_BASE)).toBe('')
  })
})

describe('resolveAppBackground nested structures and priority', () => {
  const userCandidate = { enabled: true, image_url: '/api/settings/frontend/background/user.png' }
  const pluginCandidate = {
    enabled: true,
    image_url: '/api/plugins/frontend/background/plugin.png',
  }

  it('reads the direct source envelope shape (envelope.user / envelope.plugin)', () => {
    const resolved = resolveAppBackground(
      { user: userCandidate, plugin: pluginCandidate },
      API_BASE
    )

    expect(resolved.source).toBe('user')
    expect(resolved.imageUrl).toBe(
      'http://127.0.0.1:36163/api/settings/frontend/background/user.png'
    )
  })

  it('reads the sources.{source} envelope shape', () => {
    const resolved = resolveAppBackground({ sources: { plugin: pluginCandidate } }, API_BASE)

    expect(resolved.source).toBe('plugin')
    expect(resolved.enabled).toBe(true)
  })

  it('reads the {source}_background envelope shape', () => {
    const resolved = resolveAppBackground({ user_background: userCandidate }, API_BASE)

    expect(resolved.source).toBe('user')
    expect(resolved.imageUrl).toBe(
      'http://127.0.0.1:36163/api/settings/frontend/background/user.png'
    )
  })

  it('honors active_source to promote plugin above user', () => {
    const resolved = resolveAppBackground(
      { active_source: 'plugin', user: userCandidate, plugin: pluginCandidate },
      API_BASE
    )

    expect(resolved.source).toBe('plugin')
    expect(resolved.imageUrl).toBe(
      'http://127.0.0.1:36163/api/plugins/frontend/background/plugin.png'
    )
  })

  it('falls back to plugin when the user source is missing an image and falls through to default', () => {
    const resolved = resolveAppBackground(
      { user: { enabled: true, image_url: '' }, plugin: pluginCandidate },
      API_BASE
    )

    expect(resolved.source).toBe('plugin')
    expect(resolved.fallbackReason).toBe('none')
  })

  it('returns the default surface with a missing-image reason when nothing is usable', () => {
    const resolved = resolveAppBackground(
      { user: { enabled: false }, plugin: { enabled: false } },
      API_BASE
    )

    expect(resolved).toMatchObject({
      source: 'default',
      enabled: false,
      fallbackReason: 'disabled',
    })
    expect(resolved.imageUrl).toBe('')
  })
})

describe('resolveLoadableAppBackground preload and normalization', () => {
  it('keeps the resolved background when the image loads successfully', async () => {
    const imageLoader = vi.fn().mockResolvedValue(true)
    const resolved = await resolveLoadableAppBackground(
      { enabled: true, image_url: '/api/plugins/frontend/background/image?v=3' },
      API_BASE,
      null,
      imageLoader
    )

    expect(resolved.enabled).toBe(true)
    expect(resolved.fallbackReason).toBe('none')
    expect(resolved.imageUrl).toBe(
      'http://127.0.0.1:36163/api/plugins/frontend/background/image?v=3'
    )
  })

  it('normalizes brightness, opacity and blur with both 0-1 and 0-100 input', () => {
    const fromFraction = resolveAppBackground(
      {
        enabled: true,
        image_url: '/api/plugins/frontend/background/image',
        brightness: 0.5,
        opacity: 0.4,
        overlay_opacity: 0.2,
        blur_px: 12,
      },
      API_BASE
    )
    const fromPercent = resolveAppBackground(
      {
        enabled: true,
        image_url: '/api/plugins/frontend/background/image',
        brightness: 50,
        opacity: 40,
        overlay_opacity: 20,
        blur_px: 12,
      },
      API_BASE
    )

    expect(fromFraction.brightness).toBe(50)
    expect(fromFraction.opacity).toBe(40)
    expect(fromFraction.overlayOpacity).toBe(20)
    expect(fromFraction.blurPx).toBe(12)
    expect(fromPercent.brightness).toBe(fromFraction.brightness)
    expect(fromPercent.opacity).toBe(fromFraction.opacity)
    expect(fromPercent.overlayOpacity).toBe(fromFraction.overlayOpacity)
  })

  it('clamps blur to the 0-40 range and opacity-derived surfaces fall back to card opacity', () => {
    const resolved = resolveAppBackground(
      {
        enabled: true,
        image_url: '/api/plugins/frontend/background/image',
        blur_px: 200,
        card_opacity: 80,
      },
      API_BASE
    )

    expect(resolved.blurPx).toBe(40)
    expect(resolved.cardOpacity).toBe(80)
    expect(resolved.panelOpacity).toBe(80)
    expect(resolved.elevatedOpacity).toBe(80)
  })
})

describe('validateImageFile local image security', () => {
  const makeFile = (name: string, type: string, size: number): File => {
    return {
      name,
      type,
      size,
      lastModified: Date.now(),
      slice: () => new Blob(),
      arrayBuffer: async () => new ArrayBuffer(0),
      stream: () => new ReadableStream(),
      text: async () => '',
    } as File
  }

  it('accepts PNG, JPEG, WebP, GIF, and BMP images', () => {
    expect(validateImageFile(makeFile('a.png', 'image/png', 1024)).valid).toBe(true)
    expect(validateImageFile(makeFile('a.jpg', 'image/jpeg', 1024)).valid).toBe(true)
    expect(validateImageFile(makeFile('a.webp', 'image/webp', 1024)).valid).toBe(true)
    expect(validateImageFile(makeFile('a.gif', 'image/gif', 1024)).valid).toBe(true)
    expect(validateImageFile(makeFile('a.bmp', 'image/bmp', 1024)).valid).toBe(true)
  })

  it('rejects non-image MIME types', () => {
    expect(validateImageFile(makeFile('a.svg', 'image/svg+xml', 1024)).valid).toBe(false)
    expect(validateImageFile(makeFile('a.exe', 'application/octet-stream', 1024)).valid).toBe(false)
    expect(validateImageFile(makeFile('a.html', 'text/html', 1024)).valid).toBe(false)
  })

  it('rejects files larger than 10MB', () => {
    const elevenMb = 11 * 1024 * 1024
    const result = validateImageFile(makeFile('large.png', 'image/png', elevenMb))
    expect(result.valid).toBe(false)
    expect(result.reason).toContain('10MB')
  })

  it('accepts files at exactly 10MB', () => {
    const tenMb = 10 * 1024 * 1024
    expect(validateImageFile(makeFile('ok.png', 'image/png', tenMb)).valid).toBe(true)
  })
})

describe('user background settings persistence (localStorage metadata only)', () => {
  beforeEach(() => {
    vi.stubGlobal('localStorage', {
      getItem: vi.fn(),
      setItem: vi.fn(),
      removeItem: vi.fn(),
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('saveUserBackgroundSettings writes JSON to localStorage WITHOUT imageDataUrl', () => {
    const settings = {
      ...DEFAULT_BACKGROUND_SETTINGS,
      enabled: true,
      blurPx: 12,
      imageDataUrl: 'data:image/png;base64,abc',
    }
    saveUserBackgroundSettings(settings)
    const savedArg = JSON.parse((localStorage.setItem as ReturnType<typeof vi.fn>).mock.calls[0][1])
    expect(localStorage.setItem).toHaveBeenCalledWith('v6-user-background', expect.any(String))
    expect(savedArg.enabled).toBe(true)
    expect(savedArg.blurPx).toBe(12)
    expect(savedArg.imageDataUrl).toBeUndefined()
  })

  it('loadUserBackgroundSettings returns null when nothing is stored', () => {
    ;(localStorage.getItem as ReturnType<typeof vi.fn>).mockReturnValue(null)
    expect(loadUserBackgroundSettings()).toBeNull()
  })

  it('loadUserBackgroundSettings merges stored values with defaults', () => {
    ;(localStorage.getItem as ReturnType<typeof vi.fn>).mockReturnValue(
      JSON.stringify({ enabled: true, blurPx: 15 })
    )
    const loaded = loadUserBackgroundSettings()
    expect(loaded).not.toBeNull()
    expect(loaded!.enabled).toBe(true)
    expect(loaded!.blurPx).toBe(15)
    expect(loaded!.brightness).toBe(DEFAULT_BACKGROUND_SETTINGS.brightness)
    expect(loaded!.opacity).toBe(DEFAULT_BACKGROUND_SETTINGS.opacity)
    expect(loaded!.imageDataUrl).toBeUndefined()
  })

  it('loadUserBackgroundSettings returns null for corrupted JSON', () => {
    ;(localStorage.getItem as ReturnType<typeof vi.fn>).mockReturnValue('not-json{{{')
    expect(loadUserBackgroundSettings()).toBeNull()
  })

  it('clearUserBackgroundSettings removes the storage key', () => {
    clearUserBackgroundSettings()
    expect(localStorage.removeItem).toHaveBeenCalledWith('v6-user-background')
  })
})

describe('user background image persistence (IndexedDB)', () => {
  let idbStore: Record<string, string>
  let idbShouldFail: boolean
  let idbQuotaExceeded: boolean
  let localStorageData: Record<string, string>
  let getItemMock: ReturnType<typeof vi.fn>
  let setItemMock: ReturnType<typeof vi.fn>
  let removeItemMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    idbStore = {}
    idbShouldFail = false
    idbQuotaExceeded = false
    localStorageData = {}
    getItemMock = vi.fn((key: string) => localStorageData[key] ?? null)
    setItemMock = vi.fn((key: string, value: string) => {
      localStorageData[key] = value
    })
    removeItemMock = vi.fn((key: string) => {
      delete localStorageData[key]
    })

    vi.stubGlobal('localStorage', {
      getItem: getItemMock,
      setItem: setItemMock,
      removeItem: removeItemMock,
    })

    const createdStores = new Set<string>()

    const mockStore = {
      put: vi.fn((value: string, key: string) => {
        if (idbQuotaExceeded) {
          const error = new Error('QuotaExceededError: storage quota exceeded')
          const req = {
            onsuccess: null as (() => void) | null,
            onerror: null as (() => void) | null,
            error,
            result: undefined,
          }
          queueMicrotask(() => {
            if (req.onerror) req.onerror()
          })
          return req
        }
        if (idbShouldFail) {
          const error = new Error('IndexedDB put failed')
          const req = {
            onsuccess: null as (() => void) | null,
            onerror: null as (() => void) | null,
            error,
            result: undefined,
          }
          queueMicrotask(() => {
            if (req.onerror) req.onerror()
          })
          return req
        }
        idbStore[key] = value
        const req = {
          onsuccess: null as (() => void) | null,
          onerror: null as (() => void) | null,
          error: null,
          result: undefined,
        }
        queueMicrotask(() => {
          if (req.onsuccess) req.onsuccess()
        })
        return req
      }),
      get: vi.fn((key: string) => {
        const value = idbStore[key]
        const req = {
          onsuccess: null as (() => void) | null,
          onerror: null as (() => void) | null,
          error: null,
          result: value,
        }
        queueMicrotask(() => {
          if (req.onsuccess) req.onsuccess()
        })
        return req
      }),
      delete: vi.fn((key: string) => {
        delete idbStore[key]
        const req = {
          onsuccess: null as (() => void) | null,
          onerror: null as (() => void) | null,
          error: null,
          result: undefined,
        }
        queueMicrotask(() => {
          if (req.onsuccess) req.onsuccess()
        })
        return req
      }),
    }

    const createTx = () => {
      const tx: {
        oncomplete: null | (() => void)
        onerror: null | ((e: unknown) => void)
        objectStore: (name: string) => typeof mockStore
      } = {
        oncomplete: null,
        onerror: null,
        objectStore: () => mockStore,
      }
      return tx
    }

    const mockDB = {
      transaction: vi.fn(() => createTx()),
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
      onerror: null as ((e: unknown) => void) | null,
      error: null,
      result: mockDB,
    }

    vi.stubGlobal('indexedDB', {
      open: vi.fn(() => {
        if (idbShouldFail && Object.keys(idbStore).length === 0) {
          queueMicrotask(() => mockOpenRequest.onerror?.({ error: new Error('open failed') }))
        } else {
          queueMicrotask(() => {
            mockOpenRequest.onupgradeneeded?.()
            mockOpenRequest.onsuccess?.({ target: { result: mockDB } })
          })
        }
        return mockOpenRequest
      }),
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('saveUserBackgroundImage stores to IndexedDB and returns success', async () => {
    const dataUrl = 'data:image/png;base64,abc123'
    const result = await saveUserBackgroundImage(dataUrl)
    expect(result.success).toBe(true)
    expect(idbStore['user-wallpaper']).toBe(dataUrl)
  })

  it('saveUserBackgroundImage returns quota-exceeded on QuotaExceededError', async () => {
    idbQuotaExceeded = true
    const result = await saveUserBackgroundImage('data:image/png;base64,toolarge')
    expect(result.success).toBe(false)
    expect(result.reason).toBe('storage-quota-exceeded')
  })

  it('saveUserBackgroundImage returns local-file-error on generic failure', async () => {
    idbShouldFail = true
    const result = await saveUserBackgroundImage('data:image/png;base64,abc')
    expect(result.success).toBe(false)
    expect(result.reason).toBe('local-file-error')
  })

  it('loadUserBackgroundImage returns stored image', async () => {
    idbStore['user-wallpaper'] = 'data:image/png;base64,stored'
    const result = await loadUserBackgroundImage()
    expect(result).toBe('data:image/png;base64,stored')
  })

  it('loadUserBackgroundImage returns null when nothing is stored', async () => {
    const result = await loadUserBackgroundImage()
    expect(result).toBeNull()
  })

  it('loadUserBackgroundSettingsWithImage combines settings from localStorage and image from IndexedDB', async () => {
    localStorageData['v6-user-background'] = JSON.stringify({
      enabled: true,
      source: 'user',
      blurPx: 8,
    })
    idbStore['user-wallpaper'] = 'data:image/png;base64,from-idb'

    const result = await loadUserBackgroundSettingsWithImage()
    expect(result).not.toBeNull()
    expect(result!.enabled).toBe(true)
    expect(result!.source).toBe('user')
    expect(result!.blurPx).toBe(8)
    expect(result!.imageDataUrl).toBe('data:image/png;base64,from-idb')
  })

  it('loadUserBackgroundSettingsWithImage disables user background when image is missing from IndexedDB', async () => {
    localStorageData['v6-user-background'] = JSON.stringify({ enabled: true, source: 'user' })

    const result = await loadUserBackgroundSettingsWithImage()
    expect(result).not.toBeNull()
    expect(result!.enabled).toBe(false)
    expect(result!.source).toBe('default')
  })

  it('clearUserBackgroundImage removes image from IndexedDB', async () => {
    idbStore['user-wallpaper'] = 'data:image/png;base64,todelete'
    await clearUserBackgroundImage()
    expect(idbStore['user-wallpaper']).toBeUndefined()
  })
})

describe('fileToDataUrl conversion', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('resolves with a data URL on successful read', async () => {
    const fakeFile = {
      name: 'test.png',
      type: 'image/png',
    } as File
    const result = 'data:image/png;base64,abc123'
    class MockFileReader {
      onload: (() => void) | null = null
      onerror: (() => void) | null = null
      result = result
      readAsDataURL = vi.fn(function (this: MockFileReader) {
        queueMicrotask(() => this.onload?.())
      })
    }
    vi.stubGlobal('FileReader', MockFileReader)
    const dataUrl = await fileToDataUrl(fakeFile)
    expect(dataUrl).toBe(result)
  })

  it('rejects on FileReader error', async () => {
    const fakeFile = { name: 'bad.png', type: 'image/png' } as File
    class MockFileReader {
      onload: (() => void) | null = null
      onerror: (() => void) | null = null
      readAsDataURL = vi.fn(function (this: MockFileReader) {
        queueMicrotask(() => this.onerror?.())
      })
    }
    vi.stubGlobal('FileReader', MockFileReader)
    await expect(fileToDataUrl(fakeFile)).rejects.toThrow('读取文件失败')
  })
})

describe('resolveSafeBackgroundUrl data URL support', () => {
  it('accepts data:image/ URLs for local user backgrounds', () => {
    const dataUrl =
      'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=='
    expect(resolveSafeBackgroundUrl(dataUrl, API_BASE)).toBe(dataUrl)
  })
})
