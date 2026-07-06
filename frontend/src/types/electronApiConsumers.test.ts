import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const consumerPaths = [
  '../components/devtools/BackendLaunchPage.vue',
  '../views/Emulator.vue',
  '../views/EditView/Script/GeneralScriptEdit.vue',
  '../views/EditView/Script/M9AScriptEdit.vue',
  '../views/EditView/Script/MAAScriptEdit.vue',
  '../views/EditView/Script/SRCScriptEdit.vue',
  '../views/EditView/User/MAAUserEdit.vue',
  '../views/history/useHistoryLogic.ts',
  '../views/setting/index.vue',
]

describe('typed Electron API consumers', () => {
  it.each(consumerPaths)('%s avoids disabling Electron API types', path => {
    const source = readFileSync(new URL(path, import.meta.url), 'utf8')

    expect(source).not.toMatch(/\(window(?:\.electronAPI)? as any\)\.electronAPI/)
    expect(source).not.toContain('(window.electronAPI as any)')
  })
})
