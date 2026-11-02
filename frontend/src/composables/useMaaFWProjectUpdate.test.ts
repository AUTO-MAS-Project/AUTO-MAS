import { describe, expect, it } from 'vite-plus/test'
import { resolveAutoUpdateMode } from './useMaaFWProjectUpdate'

describe('managed project update timing', () => {
  it.each([
    ['Off', 'Off'],
    ['BeforeRun', 'BeforeRun'],
    ['AfterRun', 'BeforeRun'],
    ['invalid', 'BeforeRun'],
  ])('maps %s to %s', (stored, expected) => {
    expect(resolveAutoUpdateMode({ AutoUpdateMode: stored })).toBe(expected)
  })
})
