import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const readSibling = (name: string) =>
  readFileSync(fileURLToPath(new URL(`./${name}`, import.meta.url)), 'utf8')

describe('AppSider selection contract', () => {
  it('prevents accidental text selection across the navigation shell', () => {
    const source = readSibling('AppSider.vue')

    expect(source).toContain('user-select: none')
    expect(source).toContain('-webkit-user-select: none')
  })

  it('keeps a restrained keyboard-only focus indication on menu items', () => {
    const source = readSibling('AppSiderMenu.vue')

    expect(source).toContain('.ant-menu-item:focus-visible')
    expect(source).toContain('user-select: none')
    expect(source).not.toContain('inset 0 0 0 2px var(--v6-color-info)')
  })

  it('keeps labels mounted while collapse motion fades and reflows them', () => {
    const siderSource = readSibling('AppSider.vue')
    const menuSource = readSibling('AppSiderMenu.vue')

    expect(siderSource).toContain('<span class="toggle-text" :aria-hidden="collapsed">')
    expect(siderSource).not.toContain('<span v-if="!collapsed" class="toggle-text">')
    expect(menuSource).toContain('v-if="sectionLabel"')
    expect(menuSource).not.toContain('v-if="sectionLabel && !collapsed"')
    expect(menuSource).toContain('.ant-menu-title-content')
    expect(menuSource).toContain('max-width var(--v6-motion-base)')
    expect(menuSource).toContain('opacity var(--v6-motion-fast)')
    // 纵向布局属性一律不做动画，杜绝折叠过程中的上下抖动
    expect(menuSource).not.toContain('max-height var(')
    expect(siderSource).not.toContain('height var(--v6-motion')
  })

  it('keeps identical row geometry in both sidebar states, hiding only the text', () => {
    const siderSource = readSibling('AppSider.vue')
    const menuSource = readSibling('AppSiderMenu.vue')

    expect(siderSource).toContain("'app-sider--collapsed': collapsed")
    // 折叠态不得改写任何行几何（无 .collapse-toggle 折叠特例），仅收文字
    expect(siderSource).not.toContain('.app-sider--collapsed .collapse-toggle')
    expect(siderSource).toContain('.app-sider--collapsed .toggle-text')
    expect(menuSource).toContain("'app-sider-menu--collapsed': collapsed")
    // 两态同一行契约：40px 行高、外框 calc(100% - 8px)、0 10px 内边距、20px 图标列
    expect(menuSource).toContain('height: 40px')
    expect(menuSource).toContain('line-height: 40px')
    expect(menuSource).toContain('width: calc(100% - 8px)')
    expect(menuSource).toContain('padding: 0 10px !important')
    expect(menuSource).toContain('flex: 0 0 20px')
    // 折叠时文字以 max-width/opacity 收缩，不从 DOM 移除
    expect(menuSource).toContain(
      '.app-sider-menu--collapsed :deep(.ant-menu .ant-menu-title-content)'
    )
    expect(menuSource).toContain('max-width: 0')
  })

  it('animates sider width but disables shell motion for reduced-motion and low-performance modes', () => {
    const siderSource = readSibling('AppSider.vue')
    const menuSource = readSibling('AppSiderMenu.vue')

    expect(siderSource).toContain('width var(--v6-motion-base)')
    expect(siderSource).toContain('flex-basis var(--v6-motion-base)')
    expect(siderSource).toContain("data-perf-mode='low'")
    expect(menuSource).toContain("data-perf-mode='low'")
    expect(siderSource).toContain('prefers-reduced-motion')
    expect(menuSource).toContain('prefers-reduced-motion')
  })

  it('hosts global search and appearance controls in both expanded and collapsed sidebar modes', () => {
    const siderSource = readSibling('AppSider.vue')
    const searchSource = readSibling('GlobalSearch.vue')

    expect(siderSource).toContain('<GlobalSearch')
    expect(siderSource).toContain(':collapsed="collapsed"')
    expect(siderSource).toContain('@search="handleGlobalSearch"')
    expect(siderSource).toContain('sider-theme-toggle')
    expect(siderSource).toContain('.app-sider--collapsed .sider-tool-text')
    expect(searchSource).toContain('@press-enter="submitDefault"')
    expect(searchSource).toContain('popoverOpen')
  })

  it('drops the 主菜单 section label so collapse motion stays clean', () => {
    const siderSource = readSibling('AppSider.vue')

    expect(siderSource).not.toContain('主菜单')
    // 开发分组仍保留分组标题
    expect(siderSource).toContain('section-label="开发"')
  })

  it('aligns the theme toggle with the bottom menu items geometry', () => {
    const siderSource = readSibling('AppSider.vue')
    const menuSource = readSibling('AppSiderMenu.vue')

    // 与菜单项一致：外框 calc(100% - 8px) 居中、40px 行高、0 10px 内边距、间距 6px
    expect(siderSource).toContain(
      'width: calc(100% - 8px);\n  height: 40px;\n  margin: 0 auto var(--v6-space-1);\n  padding: 0 10px;'
    )
    expect(siderSource).toContain('gap: 6px;')
    expect(siderSource).toContain('font-size: 18px')
    expect(menuSource).toContain('padding: 0 10px !important')
    expect(menuSource).toContain('gap: 6px;')
  })
})
