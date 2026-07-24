import { describe, expect, it, vi } from 'vitest'

import {
  resolveAppBackground,
  resolveLoadableAppBackground,
  resolveSafeBackgroundUrl,
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
    // \t 放在 URL 中间：源码 raw.trim() 只剥首尾空白，中间的控制字符由 hasUnsafeCharacter 拦截
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
