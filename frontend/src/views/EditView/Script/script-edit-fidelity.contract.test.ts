import { describe, expect, it } from 'vitest'
import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const root = resolve(__dirname)

const editorFiles = [
  'GeneralScriptEdit.vue',
  'GenericScriptEdit.vue',
  'HSRScriptEdit.vue',
  'MaaEndScriptEdit.vue',
  'MaaFWScriptEdit.vue',
  'MaaFWSetupWizard.vue',
  'MAAScriptEdit.vue',
  'OkScriptScriptEdit.vue',
  'OkwwScriptEdit.vue',
  'PluginScriptEdit.vue',
  'SRCScriptEdit.vue',
]

describe('script editor UI fidelity contract', () => {
  it.each(editorFiles)('%s keeps a real edit surface and save or autosave flow', file => {
    const source = readFileSync(resolve(root, file), 'utf8')

    expect(source).toMatch(/<a-form|<SchemaForm/)
    expect(source).toMatch(/handleChange|handleSave|saveStatus/)
    expect(source).toContain('ScriptEditPageHeader')
    expect(source).toContain('script-edit-surface.css')
  })

  it('provides one shared compact macOS-style page header', () => {
    const source = readFileSync(resolve(root, 'ScriptEditPageHeader.vue'), 'utf8')

    expect(source).toContain('PageHeader')
    expect(source).not.toContain('ScriptEditLogInspector')
    expect(source).not.toContain('script-edit-log-dock')
    expect(source).toContain('compact')
    expect(source).toContain('transparent')
    expect(source).toContain('var(--v6-radius')
  })

  it('keeps the removed log inspector out of script configuration surfaces', () => {
    // ScriptEditLogInspector.vue 全仓零引用,已作为死代码删除;
    // 守住:该组件不复活、页头也不引用它
    const headerSource = readFileSync(resolve(root, 'ScriptEditPageHeader.vue'), 'utf8')

    expect(headerSource).not.toContain('ScriptEditLogInspector')
    expect(existsSync(resolve(root, 'ScriptEditLogInspector.vue'))).toBe(false)
  })

  it('keeps specialized script capabilities visible in their editors', () => {
    const general = readFileSync(resolve(root, 'GeneralScriptEdit.vue'), 'utf8')
    const hsr = readFileSync(resolve(root, 'HSRScriptEdit.vue'), 'utf8')
    const maa = readFileSync(resolve(root, 'MAAScriptEdit.vue'), 'utf8')
    const src = readFileSync(resolve(root, 'SRCScriptEdit.vue'), 'utf8')
    const maaEnd = readFileSync(resolve(root, 'MaaEndScriptEdit.vue'), 'utf8')
    const maafw = readFileSync(resolve(root, 'MaaFWScriptEdit.vue'), 'utf8')
    const okScript = readFileSync(resolve(root, 'OkScriptScriptEdit.vue'), 'utf8')
    const okww = readFileSync(resolve(root, 'OkwwScriptEdit.vue'), 'utf8')

    expect(general).toContain('selectRootPath')
    expect(general).toContain('showUploadModal')
    expect(hsr).toContain('培养目标')
    expect(hsr).toContain('模块脚本分配')
    expect(hsr).toContain("selectPath('M7A.Path')")
    expect(maa).toContain('模拟器管理')
    expect(maa).toContain('handleEmulatorSelectChange')
    expect(src).toContain('模拟器管理')
    expect(src).toContain('selectSRCPath')
    expect(maaEnd).toContain('handleMaaEndConfig')
    expect(maaEnd).toContain('handleSaveMaaEndConfig')
    expect(maafw).toContain('ControlConfigSection')
    expect(maafw).toContain('UpdateSettingsSection')
    expect(okScript).toContain('projectMetadata')
    expect(okScript).toContain('selectRootPath')
    expect(okww).toContain('CloseOnManualStop')
  })

  it('keeps schema-driven editors on the sensitive-field-safe save path', () => {
    for (const file of ['GenericScriptEdit.vue', 'PluginScriptEdit.vue']) {
      const source = readFileSync(resolve(root, file), 'utf8')

      expect(source).toContain('buildSchemaSavePayload')
      expect(source).toContain('resetSensitiveDrafts')
      expect(source).toContain('sanitizeErrorForLog')
    }
  })

  it('serializes HSR autosaves and surfaces persistence failures', () => {
    const hsr = readFileSync(resolve(root, 'HSRScriptEdit.vue'), 'utf8')

    expect(hsr).toContain('saveQueue.then(persist, persist)')
    expect(hsr).toContain('pendingSaveCount')
    expect(hsr).toContain('message.error(saveError.value)')
    expect(hsr).not.toContain('if (isInitializing.value || isSaving.value) return')
  })
})
