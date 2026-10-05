import { describe, expect, it } from 'vitest'
import { createAppearanceCursorValue } from './appearanceCursor'

const POINTER_URL = 'data:image/png;base64,AA=='

describe('createAppearanceCursorValue', () => {
  it('includes a validated hotspot and native fallback in the CSS value', () => {
    expect(
      createAppearanceCursorValue(
        'pointer',
        { pointer: POINTER_URL },
        { pointer: { path: 'assets/pointer.png', hotspotX: 4, hotspotY: 6 } }
      )
    ).toBe(`url("${POINTER_URL}") 4 6, pointer`)
  })

  it('falls back to the browser cursor when a key or data URL is missing', () => {
    expect(createAppearanceCursorValue('default', undefined, undefined)).toBe('auto')
    expect(
      createAppearanceCursorValue(
        'text',
        { text: 'https://example.invalid/cursor.png' },
        { text: { path: 'assets/text.png' } }
      )
    ).toBe('text')
  })
})
