import { describe, expect, it } from 'vitest'

import {
  AVD_TIERS,
  RESOLUTIONS,
  STANDARD_TIERS,
  alignSettings,
  batchChanges,
  batchKindOf,
  emptyTierForm,
  memoryText,
  nearestTier,
  resolutionTierOf,
  settingsChanges,
  tierKindOf,
  type ActualSettings,
} from './settingsTiers'

const actual = (over: Partial<ActualSettings> = {}): ActualSettings => ({
  width: 1280,
  height: 720,
  dpi: 240,
  cpu: 4,
  memoryMb: 4096,
  fps: 60,
  ...over,
})

describe('tiers', () => {
  it('standard tiers are shared by LDPlayer and MuMu', () => {
    expect(STANDARD_TIERS).toEqual({
      cpu: [2, 4, 6, 8],
      memoryMb: [2048, 3072, 4096, 6144, 8192],
      fps: [30, 60],
    })
  })

  it('mod AVD tiers follow the backend choices', () => {
    expect(AVD_TIERS.cpu).toEqual([2, 4, 6])
    expect(AVD_TIERS.memoryMb).toEqual([3072, 4096, 5120, 6144])
  })

  it('DPI scales with height so both tiers share the same dp layout', () => {
    for (const { height, dpi } of Object.values(RESOLUTIONS)) {
      expect(dpi).toBe((240 * height) / 720)
      // 横屏的短边就是高：sw = 高 × 160 / DPI
      expect((height * 160) / dpi).toBe(480)
    }
  })

  it('kind by emulator type and by the whole config', () => {
    expect(tierKindOf('avd')).toBe('avd')
    expect(tierKindOf('ldplayer')).toBe('standard')
    expect(tierKindOf(undefined)).toBe('standard')
    expect(batchKindOf(['avd', 'avd'])).toBe('avd')
    expect(batchKindOf(['avd', 'mumu'])).toBe('standard')
    expect(batchKindOf([])).toBe('standard')
  })

  it('memory shows whole GB, other values in MB', () => {
    expect(memoryText(6144)).toBe('6 GB')
    expect(memoryText(5120)).toBe('5 GB')
    expect(memoryText(3000)).toBe('3000 MB')
  })
})

describe('nearest tier', () => {
  it('picks the closest tier', () => {
    expect(nearestTier(1, STANDARD_TIERS.cpu)).toBe(2)
    expect(nearestTier(12, STANDARD_TIERS.cpu)).toBe(8)
    expect(nearestTier(40, STANDARD_TIERS.fps)).toBe(30)
    expect(nearestTier(120, STANDARD_TIERS.fps)).toBe(60)
  })

  it('takes the larger tier on a tie', () => {
    expect(nearestTier(3, STANDARD_TIERS.cpu)).toBe(4)
    expect(nearestTier(45, STANDARD_TIERS.fps)).toBe(60)
    expect(nearestTier(5120, STANDARD_TIERS.memoryMb)).toBe(6144)
    expect(nearestTier(7168, STANDARD_TIERS.memoryMb)).toBe(8192)
  })

  it('does not align a missing value', () => {
    expect(nearestTier(null, STANDARD_TIERS.cpu)).toBeNull()
  })
})

describe('resolution tier', () => {
  it('goes by the short side, portrait included', () => {
    expect(resolutionTierOf(1280, 720)).toBe('720p')
    expect(resolutionTierOf(720, 1280)).toBe('720p')
    expect(resolutionTierOf(1600, 900)).toBe('720p')
    expect(resolutionTierOf(1920, 1080)).toBe('1080p')
    expect(resolutionTierOf(1080, 1920)).toBe('1080p')
    expect(resolutionTierOf(2560, 1440)).toBe('1080p')
    expect(resolutionTierOf(1280, 960)).toBe('1080p')
  })

  it('needs both sides', () => {
    expect(resolutionTierOf(null, 720)).toBeNull()
    expect(resolutionTierOf(1280, null)).toBeNull()
  })
})

describe('align on open (standard)', () => {
  it('values on a tier are left alone and nothing is marked', () => {
    const { form, snapped } = alignSettings(actual(), 'standard')
    expect(form).toEqual({ resolution: '720p', cpu: 4, memoryMb: 4096, fps: 60 })
    expect(snapped).toEqual({ resolution: null, dpi: null, cpu: null, memoryMb: null, fps: null })
    expect(settingsChanges(actual(), form, 'standard')).toEqual({})
  })

  it('off-tier values snap, are marked, and get written on save', () => {
    const current = actual({ width: 1280, height: 960, dpi: 320, cpu: 3, memoryMb: 5120, fps: 45 })
    const { form, snapped } = alignSettings(current, 'standard')
    expect(form).toEqual({ resolution: '1080p', cpu: 4, memoryMb: 6144, fps: 60 })
    expect(snapped).toEqual({
      resolution: { width: 1280, height: 960 },
      dpi: 320,
      cpu: 3,
      memoryMb: 5120,
      fps: 45,
    })
    expect(settingsChanges(current, form, 'standard')).toEqual({
      width: 1920,
      height: 1080,
      dpi: 360,
      cpu: 4,
      memoryMb: 6144,
      fps: 60,
    })
  })

  it('portrait is filed by the short side and saved as landscape', () => {
    const current = actual({ width: 720, height: 1280 })
    const { form, snapped } = alignSettings(current, 'standard')
    expect(form.resolution).toBe('720p')
    expect(snapped.resolution).toEqual({ width: 720, height: 1280 })
    expect(snapped.dpi).toBeNull()
    expect(settingsChanges(current, form, 'standard')).toEqual({ width: 1280, height: 720 })
  })

  it('a DPI that does not match the resolution is corrected on its own', () => {
    const current = actual({ dpi: 320 })
    const { form, snapped } = alignSettings(current, 'standard')
    expect(snapped).toMatchObject({ resolution: null, dpi: 320 })
    expect(settingsChanges(current, form, 'standard')).toEqual({ dpi: 240 })
  })

  it('unset or unreadable fields are not aligned and not written', () => {
    const current: ActualSettings = {
      width: null,
      height: null,
      dpi: null,
      cpu: null,
      memoryMb: null,
      fps: null,
    }
    const { form, snapped } = alignSettings(current, 'standard')
    expect(form).toEqual(emptyTierForm())
    expect(snapped).toEqual({ resolution: null, dpi: null, cpu: null, memoryMb: null, fps: null })
    expect(settingsChanges(current, form, 'standard')).toEqual({})
  })

  it('an unset DPI is only written when the resolution changes', () => {
    const current = actual({ dpi: null })
    expect(alignSettings(current, 'standard').snapped.dpi).toBeNull()
    expect(
      settingsChanges(current, { ...emptyTierForm(), resolution: '720p' }, 'standard')
    ).toEqual({})
    expect(
      settingsChanges(current, { ...emptyTierForm(), resolution: '1080p' }, 'standard')
    ).toEqual({ width: 1920, height: 1080, dpi: 360 })
  })

  it('picking a resolution for an instance that never had one writes all three', () => {
    const current = actual({ width: null, height: null, dpi: null })
    expect(
      settingsChanges(current, { ...emptyTierForm(), resolution: '720p' }, 'standard')
    ).toEqual({ width: 1280, height: 720, dpi: 240 })
  })

  it('a user change is sent like any other', () => {
    const current = actual()
    const { form } = alignSettings(current, 'standard')
    expect(settingsChanges(current, { ...form, cpu: 8, fps: 30 }, 'standard')).toEqual({
      cpu: 8,
      fps: 30,
    })
  })
})

describe('align on open (mod AVD)', () => {
  it('resolution and frame rate are fixed and never written', () => {
    const current = actual({
      width: 720,
      height: 1280,
      dpi: 240,
      fps: null,
      cpu: 6,
      memoryMb: 6144,
    })
    const { form, snapped } = alignSettings(current, 'avd')
    expect(form).toEqual({ resolution: '720p', cpu: 6, memoryMb: 6144, fps: 60 })
    expect(snapped).toEqual({ resolution: null, dpi: null, cpu: null, memoryMb: null, fps: null })
    expect(settingsChanges(current, form, 'avd')).toEqual({})
  })

  it('cpu and memory snap to the AVD tiers', () => {
    const current = actual({ cpu: 8, memoryMb: 8192 })
    const { form, snapped } = alignSettings(current, 'avd')
    expect(form).toMatchObject({ cpu: 6, memoryMb: 6144 })
    expect(snapped).toMatchObject({ cpu: 8, memoryMb: 8192 })
    expect(settingsChanges(current, form, 'avd')).toEqual({ cpu: 6, memoryMb: 6144 })
  })

  it('5 GB is a tier on AVD but not on LDPlayer / MuMu', () => {
    expect(alignSettings(actual({ memoryMb: 5120 }), 'avd').form.memoryMb).toBe(5120)
    expect(alignSettings(actual({ memoryMb: 5120 }), 'standard').form.memoryMb).toBe(6144)
  })
})

describe('batch', () => {
  it('sends nothing until something is picked', () => {
    expect(batchChanges(emptyTierForm(), 'standard')).toEqual({})
  })

  it('a resolution brings its DPI along', () => {
    expect(batchChanges({ ...emptyTierForm(), resolution: '1080p' }, 'standard')).toEqual({
      width: 1920,
      height: 1080,
      dpi: 360,
    })
  })

  it('only the picked fields are sent', () => {
    expect(batchChanges({ ...emptyTierForm(), cpu: 6, fps: 30 }, 'standard')).toEqual({
      cpu: 6,
      fps: 30,
    })
  })

  it('mod AVD configs only send what AVD can change', () => {
    expect(batchChanges({ resolution: '1080p', cpu: 4, memoryMb: 5120, fps: 30 }, 'avd')).toEqual({
      cpu: 4,
      memoryMb: 5120,
    })
  })
})
