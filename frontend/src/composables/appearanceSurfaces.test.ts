import { describe, expect, it } from 'vitest'
import type { InstalledAppearance } from '@/types/appearance'
import { createAppearanceSurfaceColor, getAppearanceSurfaceOpacity } from './appearanceSurfaces'

const appearance: InstalledAppearance = {
  formatVersion: 1,
  id: 'background',
  name: 'Background',
  mode: 'light',
  tokens: { colorPrimary: '#1677ff' },
  background: { path: 'assets/background.png' },
  backgroundUrl: 'data:image/png;base64,AA==',
}

describe('appearance surfaces', () => {
  it('only enables surfaces when a background image is available', () => {
    expect(getAppearanceSurfaceOpacity(null)).toBeUndefined()
    expect(getAppearanceSurfaceOpacity({ ...appearance, backgroundUrl: undefined })).toBeUndefined()
    expect(getAppearanceSurfaceOpacity(appearance)).toBe(0.72)
  })

  it.each([0, 0.4, 1])(
    'preserves a surface opacity of %s independently of image opacity',
    opacity => {
      expect(
        getAppearanceSurfaceOpacity({
          ...appearance,
          background: { path: 'assets/background.png', surfaceOpacity: opacity, opacity: 0.2 },
        })
      ).toBe(opacity)
    }
  )

  it('bounds the surface opacity before producing a CSS color', () => {
    expect(
      getAppearanceSurfaceOpacity({
        ...appearance,
        background: { path: 'assets/background.png', surfaceOpacity: 2 },
      })
    ).toBe(1)
    expect(
      getAppearanceSurfaceOpacity({
        ...appearance,
        background: { path: 'assets/background.png', surfaceOpacity: -1 },
      })
    ).toBe(0)
  })

  it('keeps native token colors without an image and derives only the surface color', () => {
    expect(createAppearanceSurfaceColor('#ffeecc', undefined)).toBe('#ffeecc')
    expect(createAppearanceSurfaceColor('#ffeecc', 0)).toBe(
      'color-mix(in srgb, #ffeecc 0%, transparent)'
    )
    expect(createAppearanceSurfaceColor('#141414', 0.72)).toBe(
      'color-mix(in srgb, #141414 72%, transparent)'
    )
  })
})
