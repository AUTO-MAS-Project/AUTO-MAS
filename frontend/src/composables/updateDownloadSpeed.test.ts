import { describe, expect, it } from 'vitest'
import { createLowSpeedDetector } from './updateDownloadSpeed'

describe('createLowSpeedDetector', () => {
  it('prompts once after GitHub stays below 50 KB/s for 10 seconds', () => {
    const detector = createLowSpeedDetector()
    expect(detector.update('GitHub', 40 * 1024, 0)).toBe(false)
    expect(detector.update('GitHub', 40 * 1024, 9_999)).toBe(false)
    expect(detector.update('GitHub', 40 * 1024, 10_000)).toBe(true)
    expect(detector.update('GitHub', 40 * 1024, 20_000)).toBe(false)
  })

  it('resets the timer when speed recovers', () => {
    const detector = createLowSpeedDetector()
    detector.update('GitHub', 40 * 1024, 0)
    detector.update('GitHub', 60 * 1024, 5_000)
    expect(detector.update('GitHub', 40 * 1024, 10_000)).toBe(false)
  })

  it('ignores zero speed and non-GitHub sources', () => {
    const detector = createLowSpeedDetector()
    detector.update('GitHub', 0, 0)
    expect(detector.update('GitHub', 0, 20_000)).toBe(false)
    detector.reset()
    detector.update('CNB', 10 * 1024, 0)
    expect(detector.update('CNB', 10 * 1024, 20_000)).toBe(false)
  })
})
