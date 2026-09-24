import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const source = readFileSync(new URL('./GeneralUserEdit.vue', import.meta.url), 'utf8')

describe('general user configuration entry', () => {
  it('does not pass the click event as the viewOnly argument', () => {
    expect(source).toContain('@click="handleGeneralConfig()"')
    expect(source).not.toMatch(/@click="handleGeneralConfig"(?:\s|>)/)
  })
})
