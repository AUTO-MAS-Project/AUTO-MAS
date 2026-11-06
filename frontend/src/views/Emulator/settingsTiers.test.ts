import { describe, expect, it } from 'vitest'

import { createOptions, defaultAvdOptions } from './avdLogic'
import { alignSettings, batchChanges, settingsChanges, type ActualSettings } from './settingsTiers'

const actual: ActualSettings = {
  width: 720,
  height: 1280,
  dpi: 240,
  cpu: 6,
  memoryMb: 6144,
  fps: 60,
}

describe('AVD resolution selection', () => {
  it('sends the default 1080p and an explicit 720p through creation options', () => {
    expect(createOptions(defaultAvdOptions()).resolution).toBe(1080)
    expect(createOptions({ ...defaultAvdOptions(), resolution: 720 }).resolution).toBe(720)
  })

  it('recognizes portrait presets and changes dimensions and DPI together', () => {
    const form = alignSettings(actual, 'avd').form
    expect(form.resolution).toBe('720p')
    expect(settingsChanges(actual, form, 'avd')).toEqual({})
    expect(settingsChanges(actual, { ...form, resolution: '1080p' }, 'avd')).toEqual({
      width: 1080,
      height: 1920,
      dpi: 280,
    })
    expect(
      alignSettings({ ...actual, width: 1080, height: 1920, dpi: 280 }, 'avd').form.resolution
    ).toBe('1080p')
  })

  it('keeps family-specific DPI in batch settings', () => {
    const form = { resolution: '1080p', cpu: null, memoryMb: null, fps: null } as const
    expect(batchChanges(form, 'avd')).toEqual({ width: 1920, height: 1080, dpi: 280 })
    expect(batchChanges(form, 'standard')).toEqual({ width: 1920, height: 1080, dpi: 360 })
  })
})
