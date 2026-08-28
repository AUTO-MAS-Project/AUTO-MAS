import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const mainSource = readFileSync(new URL('../main.ts', import.meta.url), 'utf8')
const sheet = readFileSync(new URL('./formSection.css', import.meta.url), 'utf8')
/** 去掉注释再断言：文件头的说明里就提到了 :last-child 和颜色写法 */
const rules = sheet.replace(/\/\*[\s\S]*?\*\//g, '')

describe('global form-section styles', () => {
  it('loads the shared stylesheet from the renderer entry', () => {
    expect(mainSource).toContain("import '@/styles/formSection.css'")
  })

  it('defines the canonical section chrome', () => {
    expect(sheet).toContain('.form-section {')
    expect(sheet).toContain('.section-header {')
    expect(sheet).toContain('.section-header h3 {')
    expect(sheet).toContain('.section-header h3::before {')
    expect(sheet).toContain('.switch-description {')
  })

  it('uses theme tokens instead of hardcoded colors', () => {
    expect(rules).not.toMatch(/#[0-9a-fA-F]{3,8}\b/)
    expect(sheet).toContain('var(--ant-color-border-secondary)')
    expect(sheet).toContain('var(--ant-color-text)')
  })

  it('omits .form-section:last-child, whose specificity would tie with scoped rules', () => {
    // (0,2,0) here would tie with a child's own `.form-section[data-v-xxx]`, making the
    // winner depend on style-injection order. It lives in the setting / tools / gamesign
    // parents as :deep(), which is (0,3,0) and therefore unambiguous.
    expect(rules).not.toContain(':last-child')
  })
})
