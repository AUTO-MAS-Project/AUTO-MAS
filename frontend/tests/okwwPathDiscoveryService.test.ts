import { describe, expect, it } from 'vitest'
import {
  findOkwwCandidates,
  findWutheringWavesCandidates,
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

  it('returns each valid discovery candidate once', async () => {
    const snapshot = {
      uninstallEntries: [
        {
          keyPath: 'ok-ww',
          displayName: 'ok-ww',
          publisher: null,
          installLocation: 'D:\\Script\\ok-ww',
          displayIcon: null,
          uninstallString: null,
        },
        {
          keyPath: 'WeGame',
          displayName: 'WeGame',
          publisher: 'Tencent',
          installLocation: 'E:\\WeGame\\wegame.exe',
          displayIcon: null,
          uninstallString: null,
        },
      ],
      kuroLaunchers: [
        {
          keyPath: 'HKEY_CURRENT_USER\\Software\\kurogame\\KRLauncher\\g152',
          installPath: 'C:\\Kuro\\Launcher',
        },
      ],
    }
    const existingPaths = new Set(
      [
        'D:\\Script\\ok-ww\\ok-ww.exe',
        'D:\\Script\\ok-ww\\data\\apps\\ok-ww\\app.json',
        'C:\\Kuro\\Launcher\\launcher.exe',
        'E:\\WeGame\\wegame.exe',
      ].map(value => value.toLowerCase())
    )
    const fileExists = async (filePath: string) => existingPaths.has(filePath.toLowerCase())

    await expect(findOkwwCandidates(snapshot, fileExists)).resolves.toEqual([
      { path: 'D:\\Script\\ok-ww' },
    ])
    await expect(findWutheringWavesCandidates(snapshot, fileExists)).resolves.toEqual([
      { path: 'C:\\Kuro\\Launcher\\launcher.exe', channel: 'China' },
      { path: 'E:\\WeGame\\wegame.exe', channel: 'WeGame' },
    ])
  })
})
