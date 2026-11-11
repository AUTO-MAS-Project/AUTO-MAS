import { describe, expect, it } from 'vitest'
import { emulatorTabTitle } from './emulatorTabTitle'

describe('emulator tab titles', () => {
  it('omits the repeated installation path without changing custom names', () => {
    expect(emulatorTabTitle('MuMu (F:/MuMu/manager.exe)', 'F:\\MuMu\\manager.exe')).toBe('MuMu')
    expect(emulatorTabTitle('MuMu (work)', 'F:/MuMu/manager.exe')).toBe('MuMu (work)')
    expect(emulatorTabTitle('MuMu (F:/Apps (x86)/manager.exe)', 'F:/Apps (x86)/manager.exe')).toBe(
      'MuMu'
    )
    expect(emulatorTabTitle('MuMu', 'F:/MuMu/manager.exe')).toBe('MuMu')
  })
})
