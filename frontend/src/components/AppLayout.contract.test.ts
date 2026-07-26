import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const source = readFileSync(resolve(__dirname, 'AppLayout.vue'), 'utf-8')

describe('AppLayout 布局契约', () => {
  it('使用 AppSider、AppContentArea、AppBackgroundLayer 子组件', () => {
    expect(source).toContain('AppSider')
    expect(source).toContain('AppContentArea')
    expect(source).toContain('AppBackgroundLayer')
  })

  it('提供跳转到主内容的 skip link', () => {
    expect(source).toContain('class="skip-to-content"')
    expect(source).toContain('#app-main-content')
    expect(source).toContain('focusMainContent')
  })

  it('skip link 在聚焦时可见并具备焦点环', () => {
    expect(source).toContain('.skip-to-content:focus')
    expect(source).toContain('box-shadow: var(--v6-focus-ring)')
  })

  it('背景图相关属性通过 data 属性暴露', () => {
    expect(source).toContain(':data-background-source="backgroundSource"')
    expect(source).toContain('has-background')
  })

  it('使用 v6 design tokens', () => {
    expect(source).toContain('var(--v6-')
  })

  it('尊重 prefers-reduced-motion', () => {
    expect(source).toContain('prefers-reduced-motion')
  })
})
