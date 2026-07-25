import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const source = readFileSync(new URL('./ScriptCreateDialog.vue', import.meta.url), 'utf8')

describe('ScriptCreateDialog structure', () => {
  it('does not render a sidebar for the linear create flow', () => {
    expect(source).not.toContain('<aside class="step-sidebar"')
  })

  it('overrides the global scrollbar hiding with defined theme variables', () => {
    expect(source).toContain('scrollbar-color: var(--ant-color-border) transparent;')
    expect(source).toContain('width: 8px !important;')
    expect(source).toContain('display: block !important;')
    expect(source).toContain('background: var(--ant-color-border) !important;')
  })
})
