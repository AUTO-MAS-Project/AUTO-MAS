import * as fs from 'fs'
import * as os from 'os'
import * as path from 'path'
import AdmZip = require('adm-zip')
import { expect, it, vi } from 'vitest'
import { addDebugDirectory, type CollectorState } from './issueReportCore'

vi.mock('./logger', () => ({ getLogger: () => ({ debug: vi.fn(), warn: vi.fn() }) }))

it('includes launcher screenshots only in MaaEnd reports', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'maaend-report-'))
  try {
    const directory = path.join(root, 'maaend-launcher-start')
    fs.mkdirSync(directory)
    fs.writeFileSync(path.join(directory, 'launcher-error.png'), 'screenshot')
    for (const adapter of ['maaend', 'okww', undefined] as const) {
      const state: CollectorState = { zip: new AdmZip(), entries: [], archiveBytes: 0 }
      addDebugDirectory(state, root, 'logs', adapter)
      expect(state.zip.getEntry('logs/maaend-launcher-start/launcher-error.png') !== null).toBe(
        adapter === 'maaend'
      )
    }
  } finally {
    fs.rmSync(root, { recursive: true, force: true })
  }
})
