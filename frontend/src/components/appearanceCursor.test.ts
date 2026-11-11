import { describe, expect, it } from 'vite-plus/test'
import {
  createAppearanceCursorValue,
  normalizeCursorSize,
  scaleCursorGeometry,
} from './appearanceCursor'

describe('appearance cursor size', () => {
  it.each([24, 32, 48])('sets the longest edge to %i and scales the hotspot', size => {
    expect(scaleCursorGeometry(32, 64, 8, 16, size)).toEqual({
      width: size / 2,
      height: size,
      hotspotX: size / 8,
      hotspotY: size / 4,
    })
  })

  it('keeps the rounded hotspot inside a thin, downscaled image', () => {
    expect(scaleCursorGeometry(64, 2, 63, 1, 8)).toEqual({
      width: 8,
      height: 1,
      hotspotX: 7,
      hotspotY: 0,
    })
  })

  it.each([undefined, null, 7, 65, 24.5, '32'])('uses the original size for %s', value => {
    expect(normalizeCursorSize(value)).toBeNull()
  })

  it.each([8, 64])('accepts the supported limit %i', value => {
    expect(normalizeCursorSize(value)).toBe(value)
  })

  it('keeps native fallback for missing cursor roles', () => {
    expect(createAppearanceCursorValue('pointer', {}, {})).toBe('pointer')
    expect(createAppearanceCursorValue('text', {}, {})).toBe('text')
  })
})
