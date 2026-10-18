import { describe, expect, it } from 'vite-plus/test'
import {
  clampCustomSurfaceOpacity,
  createCustomBackgroundDataUrl,
  CUSTOM_BACKGROUND_MAX_BYTES,
  getCustomBackgroundMime,
  hasCustomBackgroundExtension,
} from './customBackground'

describe('custom background helpers', () => {
  it('accepts supported image extensions in Windows and POSIX paths', () => {
    expect(hasCustomBackgroundExtension('D:\\背景\\wallpaper.PNG')).toBe(true)
    expect(hasCustomBackgroundExtension('/pictures/background.webp')).toBe(true)
    expect(hasCustomBackgroundExtension('/pictures/archive.zip')).toBe(false)
    expect(hasCustomBackgroundExtension('/pictures/no-extension')).toBe(false)
  })

  it('maps supported extensions to MIME types', () => {
    expect(getCustomBackgroundMime('D:\\背景\\photo.jpg')).toBe('image/jpeg')
    expect(getCustomBackgroundMime('/pictures/animation.gif')).toBe('image/gif')
    expect(getCustomBackgroundMime('/pictures/photo.svg')).toBeNull()
  })

  it('creates a data URL only for readable supported content', () => {
    expect(createCustomBackgroundDataUrl('AA==', 'D:\\背景\\photo.png')).toBe(
      'data:image/png;base64,AA=='
    )
    expect(createCustomBackgroundDataUrl('', 'D:\\背景\\photo.png')).toBeNull()
    expect(createCustomBackgroundDataUrl('AA==', '/pictures/photo.svg')).toBeNull()
  })

  it('clamps opacity to the user-facing range', () => {
    expect(clampCustomSurfaceOpacity(-1)).toBe(0.1)
    expect(clampCustomSurfaceOpacity(0.42)).toBe(0.42)
    expect(clampCustomSurfaceOpacity(1.8)).toBe(1)
    expect(clampCustomSurfaceOpacity(Number.NaN)).toBe(1)
  })

  it('keeps the background limit at 8 MB', () => {
    expect(CUSTOM_BACKGROUND_MAX_BYTES).toBe(8 * 1024 * 1024)
  })
})
