import { describe, expect, it } from 'vitest'
import {
  DEFAULT_PRESS_SOUND_PRESET,
  DEFAULT_PRESS_SOUND_VOLUME,
  normalizePressSoundPreset,
  normalizePressSoundVolume,
} from './pressSound'

describe('pressSound', () => {
  it('内置音效名原样保留', () => {
    expect(normalizePressSoundPreset('duck')).toBe('duck')
    expect(normalizePressSoundPreset('fx1')).toBe('fx1')
  })

  it('自定义音效保留，认识不了的值退回默认', () => {
    expect(normalizePressSoundPreset('custom')).toBe('custom')
    expect(normalizePressSoundPreset('nope')).toBe(DEFAULT_PRESS_SOUND_PRESET)
    expect(normalizePressSoundPreset(undefined)).toBe(DEFAULT_PRESS_SOUND_PRESET)
    expect(normalizePressSoundPreset(null)).toBe(DEFAULT_PRESS_SOUND_PRESET)
  })

  it('音量夹在 0..1，坏值用默认', () => {
    expect(normalizePressSoundVolume(0)).toBe(0)
    expect(normalizePressSoundVolume(0.35)).toBe(0.35)
    expect(normalizePressSoundVolume(1)).toBe(1)
    expect(normalizePressSoundVolume(2)).toBe(1)
    expect(normalizePressSoundVolume(-1)).toBe(0)
    expect(normalizePressSoundVolume('abc')).toBe(DEFAULT_PRESS_SOUND_VOLUME)
    expect(normalizePressSoundVolume(undefined)).toBe(DEFAULT_PRESS_SOUND_VOLUME)
  })
})
