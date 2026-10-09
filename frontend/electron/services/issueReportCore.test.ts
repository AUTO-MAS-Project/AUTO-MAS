import * as fs from 'fs'
import * as os from 'os'
import * as path from 'path'
import AdmZip = require('adm-zip')
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { addDebugDirectory, CollectorState } from './issueReportCore'

vi.mock('./logger', () => ({
  getLogger: () => ({
    error: vi.fn(),
    warn: vi.fn(),
    info: vi.fn(),
    verbose: vi.fn(),
    debug: vi.fn(),
    silly: vi.fn(),
  }),
}))

let root: string

function write(relative: string, text: string): void {
  const target = path.join(root, relative)
  fs.mkdirSync(path.dirname(target), { recursive: true })
  fs.writeFileSync(target, text, 'utf-8')
}

function collect(archiveDir: string, ownAdapter?: 'oknte'): string[] {
  const state: CollectorState = { zip: new AdmZip(), entries: [], archiveBytes: 0 }
  addDebugDirectory(state, path.join(root, 'debug'), archiveDir, ownAdapter)
  return state.entries.map(entry => ({ ...entry }))
}

function pathsOf(entries: ReturnType<typeof collect>): string[] {
  return entries.map(entry => entry.path)
}

function skippedPaths(entries: ReturnType<typeof collect>): string[] {
  return entries.filter(entry => entry.status === 'skipped').map(entry => entry.path)
}

describe('addDebugDirectory 只收声明方自己的诊断子目录', () => {
  beforeEach(() => {
    root = fs.mkdtempSync(path.join(os.tmpdir(), 'issue-report-core-'))
  })

  afterEach(() => {
    fs.rmSync(root, { recursive: true, force: true })
  })

  it('收顶层文件与 ownAdapter 声明的目录，其他专项与未登记目录都跳过', () => {
    write('debug/app.log', 'app log')
    write('debug/oknte-launcher-start/launcher-error.jpg', 'oknte')
    write('debug/maa-failure/failure.jpg', 'maa')
    write('debug/okww-account-switch/switch-error.jpg', 'okww')
    write('debug/new-adapter-diag/detail.log', '未登记的新目录')

    const entries = collect('logs/auto-mas', 'oknte')

    expect(pathsOf(entries)).toContain('logs/auto-mas/app.log')
    expect(pathsOf(entries)).toContain(
      'logs/auto-mas/oknte-launcher-start/launcher-error.jpg'
    )
    expect(pathsOf(entries)).not.toContain('logs/auto-mas/maa-failure/failure.jpg')
    expect(pathsOf(entries)).not.toContain(
      'logs/auto-mas/okww-account-switch/switch-error.jpg'
    )
    expect(pathsOf(entries)).not.toContain('logs/auto-mas/new-adapter-diag/detail.log')
  })

  it('其他专项的登记目录静默跳过，未登记目录留跳过条目进清单', () => {
    write('debug/maa-failure/failure.jpg', 'maa')
    write('debug/new-adapter-diag/detail.log', '未登记的新目录')

    const entries = collect('logs/auto-mas', 'oknte')

    expect(skippedPaths(entries)).toEqual(['logs/auto-mas/new-adapter-diag'])
    expect(skippedPaths(entries)).not.toContain('logs/auto-mas/maa-failure')
  })

  it('未声明 ownAdapter 时只收顶层文件', () => {
    write('debug/app.log', 'app log')
    write('debug/maa-failure/failure.jpg', 'maa')
    write('debug/oknte-launcher-start/launcher-error.jpg', 'oknte')

    const entries = collect('logs/auto-mas')

    expect(pathsOf(entries)).toEqual(['logs/auto-mas/app.log'])
  })
})
