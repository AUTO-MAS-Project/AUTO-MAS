import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const editPages = [
  'Script/BAAHScriptEdit.vue',
  'Script/BetterGIScriptEdit.vue',
  'Script/GeneralScriptEdit.vue',
  'Script/HSRScriptEdit.vue',
  'Script/MAAScriptEdit.vue',
  'Script/MaaEndScriptEdit.vue',
  'Script/MaaFWScriptEdit.vue',
  'Script/OkNteScriptEdit.vue',
  'Script/OkwwScriptEdit.vue',
  'Script/SRCScriptEdit.vue',
  'Script/WhimboxScriptEdit.vue',
  'Script/ZzzOdScriptEdit.vue',
  'User/BAAHUserEdit.vue',
  'User/BetterGIUserEdit.vue',
  'User/GeneralUserEdit.vue',
  'User/HSRUserEdit.vue',
  'User/MAAUserEdit.vue',
  'User/MaaEndUserEdit.vue',
  'User/MaaFWUserEdit.vue',
  'User/OkNteUserEdit.vue',
  'User/OkwwUserEdit.vue',
  'User/SRCUserEdit.vue',
  'User/WhimboxUserEdit.vue',
  'User/ZzzOdUserEdit.vue',
]

describe('ConfigLockPanel edit page bindings', () => {
  it('binds every edit page to the route script id', () => {
    // M9A 没有专用页面（MaaFW 的特调类型，走 MaaFW 的两个页面）
    expect(editPages).toHaveLength(24)
    for (const filename of editPages) {
      const pageUrl = `../views/EditView/${filename}`
      const pageSource = readFileSync(new URL(pageUrl, import.meta.url), 'utf8')
      expect(pageSource, filename).toContain('<ConfigLockPanel')
      expect(pageSource).toContain(':script-id="scriptId"')
    }
  })

  it('disables native configuration launch controls while the script is locked', () => {
    const expectedSnippets: Record<string, string[]> = {
      'User/BetterGIUserEdit.vue': [
        ':disabled="pageLoading || !userId || configLocked"',
        'if (configLocked.value) return',
      ],
      'User/GeneralUserEdit.vue': [':disabled="configLocked"', 'if (configLocked.value) return'],
      'User/MAAUserEdit.vue': [':config-locked="configLocked"', 'if (configLocked.value) return'],
      'User/MaaEndUserEdit.vue': ['if (configLocked.value) return'],
      'User/OkNteUserEdit.vue': [
        ':config-disabled="pageLoading || !activeUserId || configLocked"',
        'if (configLocked.value) return',
      ],
      'User/OkwwUserEdit.vue': [
        ':config-disabled="pageLoading || !userId || configLocked"',
        'if (configLocked.value) return',
      ],
      'User/SRCUserEdit.vue': [':config-locked="configLocked"', 'if (configLocked.value) return'],
      'User/ZzzOdUserEdit.vue': [
        ':disabled="pageLoading || !userId || configLocked"',
        'if (configLocked.value) return',
      ],
    }

    for (const [filename, snippets] of Object.entries(expectedSnippets)) {
      const pageUrl = `../views/EditView/${filename}`
      const pageSource = readFileSync(new URL(pageUrl, import.meta.url), 'utf8')
      for (const snippet of snippets) {
        expect(pageSource, filename).toContain(snippet)
      }
    }
  })
})
