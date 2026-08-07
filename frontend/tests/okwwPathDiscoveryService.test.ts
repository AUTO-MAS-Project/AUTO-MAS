import { describe, expect, it } from 'vitest'
import {
  parseRegistryPath,
  parseRegistrySnapshot,
} from '../electron/services/okwwPathDiscoveryService'

describe('OK-WW path discovery helpers', () => {
  it('extracts directories and executables from uninstall registry values', () => {
    expect(parseRegistryPath('"D:\\Script\\ok-ww"')).toBe('D:\\Script\\ok-ww')
    expect(parseRegistryPath('"D:\\Script\\ok-ww\\ok-ww.exe",0')).toBe(
      'D:\\Script\\ok-ww\\ok-ww.exe'
    )
    expect(parseRegistryPath('D:\\Script\\ok-ww\\uninstall.exe /S')).toBe(
      'D:\\Script\\ok-ww\\uninstall.exe'
    )
  })

  it('keeps registry collections as arrays even when PowerShell returns one item', () => {
    const snapshot = parseRegistrySnapshot(
      JSON.stringify({
        uninstallEntries: {
          keyPath: 'ok-ww',
          displayName: 'ok-ww',
          installLocation: 'D:\\Script\\ok-ww',
        },
        kuroLaunchers: null,
      })
    )

    expect(snapshot.uninstallEntries).toHaveLength(1)
    expect(snapshot.kuroLaunchers).toEqual([])
  })
})
