import { describe, expect, it } from 'vitest'
import { centerIconUrl, satelliteModules } from '@/composables/satellite-config'

describe('satellite-config', () => {
  it('使用打包后的真实卫星图标资源，不退化为占位或 data URI', () => {
    expect(centerIconUrl).toBeTruthy()
    expect(centerIconUrl).not.toMatch(/^data:/)
    expect(satelliteModules.length).toBeGreaterThan(0)

    for (const module of satelliteModules) {
      expect(module.iconUrl).toBeTruthy()
      expect(module.iconUrl).not.toMatch(/^data:/)
    }
  })
})
