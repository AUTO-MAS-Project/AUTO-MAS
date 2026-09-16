import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const readSource = (filename: string) =>
  readFileSync(new URL(filename, import.meta.url), 'utf8')

describe('user config runtime save lock', () => {
  it('fails pending saves instead of reporting success while locked', () => {
    const oknte = readSource('./OkNteUserEdit/OkNteConfigEditor.vue')
    expect(oknte).toContain('if (configLocked.value) {\n    if (!hasChanges.value) return true')
    expect(oknte).toContain("message.error(t('edit.configLocked'))")
    expect(oknte).toContain('return false\n  }\n  if (!hasChanges.value) return true')

    const bettergi = readSource('./BetterGIUserEdit.vue')
    expect(bettergi).toContain('const hasDragonGroupSettingsDirty = computed(')
    expect(bettergi).toContain('if (hasDragonGroupSettingsDirty.value) {')
    expect(bettergi).toContain(
      'if (!(await saveDragonGroupSettings(true, dragonGroupSaveSel))) return'
    )

    const zzzod = readSource('./ZzzOdUserEdit.vue')
    expect(zzzod).toContain('if (configLocked.value) {\n    message.error')
    expect(zzzod).toContain('return false\n  }\n  if (nativeInstanceIdx.value === null)')
  })
})
