import { describe, expect, it } from 'vite-plus/test'
import { getDefaultUpdateConfig, normalizeHSRUpdateConfig } from './hsrUpdateConfig'

describe('HSR automatic update settings', () => {
  it('enables updates before running by default', () => {
    expect(getDefaultUpdateConfig().AutoUpdateMode).toBe('BeforeRun')
  })

  it.each([
    ['Off', 'Off'],
    ['BeforeRun', 'BeforeRun'],
    ['AfterRun', 'BeforeRun'],
  ])('maps %s to %s', (stored, expected) => {
    expect(normalizeHSRUpdateConfig({ AutoUpdateMode: stored }).AutoUpdateMode).toBe(expected)
  })

  it('keeps the two engine sources independent', () => {
    const config = normalizeHSRUpdateConfig({ M7ASource: 'MirrorChyan', SRASource: 'AutoSite' })
    expect(config.M7ASource).toBe('MirrorChyan')
    expect(config.SRASource).toBe('AutoSite')
  })
})
