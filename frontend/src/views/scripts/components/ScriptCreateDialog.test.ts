import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const source = readFileSync(new URL('./ScriptCreateDialog.vue', import.meta.url), 'utf8')

describe('ScriptCreateDialog structure', () => {
  it('does not render a sidebar for the linear create flow', () => {
    expect(source).not.toContain('<aside class="step-sidebar"')
  })

  it('keeps the modal below the title bar and scrolls content inside short windows', () => {
    expect(source).toContain(':z-index="900"')
    expect(source).toContain('top: 64px;')
    expect(source).toContain('height: min(500px, calc(100vh - 192px));')
    expect(source.match(/overflow-y: auto;/g)).toHaveLength(1)
  })

  it('centers template loading in a sized state container', () => {
    expect(source).toContain('<div v-if="templateLoading" class="template-loading-state">')
    expect(source).toContain('<a-spin size="large" tip="正在加载配置模板..." />')
    expect(source).toContain('min-height: 240px;')
    expect(source).not.toContain('<a-spin :spinning="templateLoading">')
  })
})
