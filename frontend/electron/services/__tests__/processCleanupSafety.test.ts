import * as fs from 'fs'
import * as path from 'path'

import { describe, expect, it } from 'vitest'

describe('Electron process cleanup safety boundary', () => {
  it('does not contain system-wide Python or main.py termination paths', () => {
    const electronRoot = path.resolve(__dirname, '..', '..')
    const mainSource = fs.readFileSync(path.join(electronRoot, 'main.ts'), 'utf-8')
    const legacyManagerSource = fs.readFileSync(
      path.join(electronRoot, 'utils', 'processManager.ts'),
      'utf-8'
    )

    expect(mainSource).not.toMatch(/taskkill\s+\/f\s+\/im\s+python\.exe/i)
    expect(mainSource).not.toContain("import('./utils/processManager')")
    expect(mainSource).not.toMatch(/Where-Object[^\n]*main\.py/i)
    expect(legacyManagerSource).not.toMatch(/Where-Object[^\n]*main\.py/i)
    expect(mainSource).toContain("ipcMain.handle('kill-all-processes'")
    expect(mainSource).toContain('cleanupInitializationResources()')
  })
})
