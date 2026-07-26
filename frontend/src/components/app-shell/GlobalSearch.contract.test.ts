import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const source = readFileSync(fileURLToPath(new URL('./GlobalSearch.vue', import.meta.url)), 'utf8')

describe('GlobalSearch 组件契约', () => {
  it('使用 script setup lang="ts" 与 scoped styles', () => {
    expect(source).toContain('<script setup lang="ts">')
    expect(source).toContain('<style scoped>')
  })

  it('placeholder 与可达性标签均为「全局搜索」，不再是「搜索脚本」', () => {
    expect(source).toContain('placeholder="全局搜索…"')
    expect(source).toContain('aria-label="全局搜索"')
    expect(source).not.toContain('搜索脚本')
  })

  it('折叠与展开两种形态均可打开搜索，弹层沿用 mac 风格 elevated surface', () => {
    expect(source).toContain('placement="rightTop"')
    expect(source).toContain('overlay-class-name="global-search-popover"')
    expect(source).toContain('v-model:open="popoverOpen"')
    expect(source).toContain('openInlineSearch')
    expect(source).toContain('var(--v6-color-surface-elevated)')
    expect(source).toContain('var(--v6-shadow-elevated)')
  })

  it('聚合四类数据源：页面声明、设置静态表、插件实例与脚本搜索', () => {
    expect(source).toContain('buildGlobalSearchGroups')
    expect(source).toContain("from './globalSearch.ts'")
    expect(source).toContain('pages: PageDeclaration[]')
    expect(source).toContain("'/api/plugins/get'")
    expect(source).toContain('authenticatedApiFetch')
    expect(source).toContain("emit('search', searchKeyword)")
  })

  it('结果下拉分组展示并可点击跳转，尊重路由锁', () => {
    expect(source).toContain('role="listbox"')
    expect(source).toContain('role="option"')
    expect(source).toContain('global-search-group-label')
    expect(source).toContain('activateItem')
    expect(source).toContain('router.push({ path: item.target.path, query: item.target.query })')
    expect(source).toContain('isRouteLocked')
    expect(source).toContain('triggerBlockCallback')
  })

  it('保留原有快捷键行为：Enter 默认跳转脚本搜索，方向键在结果间移动，Esc 关闭', () => {
    expect(source).toContain('@press-enter="submitDefault"')
    expect(source).toContain("event.key === 'ArrowDown'")
    expect(source).toContain("event.key === 'ArrowUp'")
    expect(source).toContain("event.key === 'Escape'")
  })

  it('展示动效在 reduced-motion 与低性能模式下禁用', () => {
    expect(source).toContain('prefers-reduced-motion')
    expect(source).toContain("data-perf-mode='low'")
  })
})
