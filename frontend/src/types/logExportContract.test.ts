import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const declarationSource = readFileSync(new URL('./electron.d.ts', import.meta.url), 'utf8')
const logsViewSource = readFileSync(new URL('../views/Logs.vue', import.meta.url), 'utf8')
const settingsViewSource = readFileSync(
  new URL('../views/setting/TabAdvanced.vue', import.meta.url),
  'utf8'
)

describe('log export contract', () => {
  it('declares the fields returned by the main process', () => {
    expect(declarationSource).toContain('message?: string')
    expect(declarationSource).toContain('zipPath?: string')
  })

  it('uses the typed Electron API in both consumers', () => {
    expect(logsViewSource).not.toContain('(window as any).electronAPI')
    expect(settingsViewSource).not.toContain('(window as any).electronAPI')
  })
})
