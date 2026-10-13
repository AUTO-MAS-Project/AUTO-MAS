import { describe, expect, it } from 'vitest'
import { DEFAULT_HOME_SATELLITE_STYLE, normalizeHomeSatelliteStyle } from './homeSatellite'

describe('home satellite style', () => {
  it('默认是经典，没设置过或写坏了都按经典', () => {
    expect(DEFAULT_HOME_SATELLITE_STYLE).toBe('classic')
    expect(normalizeHomeSatelliteStyle(undefined)).toBe('classic')
    expect(normalizeHomeSatelliteStyle('3d')).toBe('classic')
  })

  it('选了 3D 星系就是 3D 星系', () => {
    expect(normalizeHomeSatelliteStyle('galaxy')).toBe('galaxy')
  })
})
