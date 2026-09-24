import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const source = readFileSync(new URL('./ConfigLockPanel.vue', import.meta.url), 'utf8')

describe('ConfigLockPanel', () => {
  it('shows a warning when the configuration is locked', () => {
    expect(source).toContain("t('edit.configLocked')")
    expect(source).toContain('v-if="configLocked"')
  })

  it('disables Ant Design components and blocks native content', () => {
    expect(source).toContain(':component-disabled="configLocked"')
    expect(source).toContain(':inert="configLocked"')
  })
})
