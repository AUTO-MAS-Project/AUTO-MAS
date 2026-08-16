import { describe, expect, it } from 'vitest'
import { getDisplayCharacter } from './encryptedTextMotion'

describe('getDisplayCharacter', () => {
  it('keeps Emoji characters intact when they are revealed', () => {
    const text = '很不高兴为你服务喵😑'
    const emojiIndex = Array.from(text).length - 1

    expect(getDisplayCharacter(text, [], emojiIndex, emojiIndex + 1)).toBe('😑')
  })
})
