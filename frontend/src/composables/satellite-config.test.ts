import { describe, expect, it } from 'vitest'
import { centerIconUrl, satelliteModules } from './satellite-config'

describe('satellite icon config', () => {
  it('loads the center and OK-WW icons from root assets', () => {
    expect(centerIconUrl).not.toBe('')
    expect(satelliteModules.some(module => module.scriptType === 'Okww')).toBe(true)
  })
})
