import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const source = readFileSync(new URL('./ScriptCreateDialog.vue', import.meta.url), 'utf8')

describe('ScriptCreateDialog structure', () => {
  it('does not render a sidebar for the linear create flow', () => {
    expect(source).not.toContain('<aside class="step-sidebar"')
  })

  it('keeps the modal below the title bar and scrolls content inside short windows', () => {
    expect(source).toContain(':z-index="900"')
    expect(source).toContain('top: 48px;')
    expect(source).toContain('height: min(500px, calc(100vh - 176px));')
    expect(source).toContain('overflow-y: auto;')
  })
})
