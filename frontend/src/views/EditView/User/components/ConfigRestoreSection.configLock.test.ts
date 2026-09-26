import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const source = readFileSync(new URL('./ConfigRestoreSection.vue', import.meta.url), 'utf8')

describe('ConfigRestoreSection runtime lock', () => {
  it('disables restore actions while keeping backup preview available', () => {
    expect(source).toContain('disabled?: boolean')
    expect(source).toContain("t('edit.configLocked')")
    expect(source).toContain(':disabled="disabled" @click="confirmRestore(item)"')
    expect(source).toContain(':disabled="disabled" @click="handlePreviewDetail"')
    expect(source).toContain('if (props.disabled) return')
    expect(source).toContain('if (props.disabled || !previewItem.value) return')
  })

  it('rechecks the lock after the restore confirmation is opened', () => {
    expect(source).toContain('const runRestore = async (item: BackupItem, force = false) => {')
    expect(source).toContain('if (props.disabled) {\n    throw new Error')
  })

  it('passes the runtime lock from every restore-capable edit page', () => {
    const pages = [
      'BAAHUserEdit.vue',
      'BetterGIUserEdit.vue',
      'GeneralUserEdit.vue',
      'HSRUserEdit.vue',
      'MAAUserEdit.vue',
      'MaaEndUserEdit.vue',
      'MaaFWUserEdit.vue',
      'OkNteUserEdit.vue',
      'OkwwUserEdit.vue',
      'SRCUserEdit.vue',
      'WhimboxUserEdit.vue',
      'ZzzOdUserEdit.vue',
    ]
    for (const filename of pages) {
      const pageUrl = `../${filename}`
      const pageSource = readFileSync(new URL(pageUrl, import.meta.url), 'utf8')
      expect(pageSource).toContain(':disabled="configLocked"')
    }
  })

  it('guards detail restore entry points and confirmations while locked', () => {
    const pages = [
      'BetterGIUserEdit.vue',
      'GeneralUserEdit.vue',
      'MAAUserEdit.vue',
      'MaaEndUserEdit.vue',
      'OkNteUserEdit.vue',
      'OkwwUserEdit.vue',
      'SRCUserEdit.vue',
      'ZzzOdUserEdit.vue',
    ]
    for (const filename of pages) {
      const pageUrl = `../${filename}`
      const pageSource = readFileSync(new URL(pageUrl, import.meta.url), 'utf8')
      expect(pageSource).toContain('if (configLocked.value) return')
      expect(pageSource).toContain(
        "if (configLocked.value) {\n          message.error(t('edit.configLocked'))"
      )
    }
  })
})
