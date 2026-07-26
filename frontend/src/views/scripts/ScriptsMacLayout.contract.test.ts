import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const scriptsViewPath = fileURLToPath(new URL('../Scripts.vue', import.meta.url))
const splitViewPath = fileURLToPath(new URL('./components/ScriptSplitView.vue', import.meta.url))
const cardPath = fileURLToPath(new URL('./components/ScriptCard.vue', import.meta.url))
const searchBarPath = fileURLToPath(new URL('./components/ScriptSearchBar.vue', import.meta.url))

describe('Scripts macOS layout contract', () => {
  it('routes the page through the mac shell and the split-view implementation', () => {
    const source = readFileSync(scriptsViewPath, 'utf8')

    expect(source).toContain("from '@/components/mac/PageHeader.vue'")
    expect(source).toContain("from '@/components/mac/Toolbar.vue'")
    expect(source).toContain("from '@/components/mac/StatePanel.vue'")
    expect(source).toContain("from '@/views/scripts/components/ScriptSplitView.vue'")
    expect(source).toContain('<PageHeader')
    expect(source).toContain('<Toolbar')
    expect(source).toContain('<ScriptSplitView')
    expect(source).not.toContain("from '@/components/ScriptTable.vue'")
  })

  it('exposes search from the trailing slot only and drops the status filter', () => {
    const source = readFileSync(scriptsViewPath, 'utf8')

    // 搜索入口位于工具栏右侧 trailing 槽，由小按钮或 Ctrl+F 触发行内横向展开
    expect(source).toContain('<template #trailing>')
    expect(source).toContain('aria-label="搜索脚本"')
    // leading 槽不再承载搜索(或已整体移除)
    expect(source).not.toContain('<template #leading>')
    // 搜索按钮位于「一键收起」左侧:trailing 槽内搜索按钮先于一键收起出现
    const searchButtonIndex = source.indexOf('aria-label="搜索脚本"')
    const collapseAllIndex = source.indexOf('一键收起')
    expect(searchButtonIndex).toBeGreaterThanOrEqual(0)
    expect(collapseAllIndex).toBeGreaterThan(searchButtonIndex)
    // 状态筛选（全部/配置中/空闲/不可用）已按新 UI 要求整体移除
    expect(source).not.toContain('script-segmented-filter')
    expect(source).not.toContain("label: '配置中'")
    expect(source).not.toContain("label: '空闲'")
    expect(source).not.toContain("label: '不可用'")
    expect(source).not.toContain('scriptStatusFilter')
    // 工具栏不再显示常驻拖拽提示文字
    expect(source).not.toContain('拖拽左侧把手调整脚本顺序')
  })

  it('expands the search field inline within the toolbar row, not as a stacked row', () => {
    const source = readFileSync(scriptsViewPath, 'utf8')
    const searchBarSource = readFileSync(searchBarPath, 'utf8')

    const toolbarStart = source.indexOf('<Toolbar')
    const toolbarEnd = source.indexOf('</Toolbar>')
    expect(toolbarStart).toBeGreaterThanOrEqual(0)
    expect(toolbarEnd).toBeGreaterThan(toolbarStart)
    const toolbarBlock = source.slice(toolbarStart, toolbarEnd)

    // 搜索框与搜索按钮同处 trailing 槽:点击后在工具栏同一行内向左展开(mac Spotlight/Safari 风格)
    expect(toolbarBlock).toContain('<template #trailing>')
    expect(toolbarBlock).toContain('<ScriptSearchBar')
    // 搜索框(向左伸出的行内容器)位于搜索按钮左侧,展开时不推挤右侧的一键收起按钮
    const inlineIndex = toolbarBlock.indexOf('script-search-inline')
    const searchButtonIndex = toolbarBlock.indexOf('aria-label="搜索脚本"')
    expect(inlineIndex).toBeGreaterThanOrEqual(0)
    expect(searchButtonIndex).toBeGreaterThan(inlineIndex)
    // 不再在工具栏下方渲染独立占行的搜索条
    expect(source.slice(toolbarEnd)).not.toContain('<ScriptSearchBar')

    // 横向展开动画:通过 Transition 过渡 max-width(0 <-> 展开宽度),并提供 reduced-motion 回退
    expect(toolbarBlock).toContain('<Transition name="script-search-expand">')
    expect(source).toMatch(/\.script-search-expand-enter-from[^{]*\{[^}]*max-width:\s*0/s)
    expect(source).toMatch(/\.script-search-expand-enter-to[^{]*\{[^}]*max-width:/s)
    expect(source).toContain('prefers-reduced-motion')

    // 搜索条自身收敛为行内布局:不再保留独立成行时代的页级块外边距与超高输入框
    expect(searchBarSource).not.toContain('--v6-content-padding-inline')
    expect(searchBarSource).not.toContain('size="large"')
  })

  it('keeps the master list, detail section and state panel in one split-view', () => {
    const source = readFileSync(splitViewPath, 'utf8')

    expect(source).toContain('class="script-split-view"')
    expect(source).toContain('class="script-master-list"')
    expect(source).toContain('class="script-detail-pane"')
    expect(source).toContain("from '@/components/mac/Section.vue'")
    expect(source).toContain("from '@/components/mac/StatePanel.vue'")
    expect(source).toContain('handle=".script-master-drag-handle"')
  })

  it('fills the available page height without viewport-derived fixed sizing', () => {
    const pageSource = readFileSync(scriptsViewPath, 'utf8')
    const splitSource = readFileSync(splitViewPath, 'utf8')
    const cardSource = readFileSync(cardPath, 'utf8')

    expect(pageSource).toMatch(/\.scripts-content\s*\{[^}]*display:\s*flex/s)
    expect(pageSource).toMatch(/\.scripts-content\s*\{[^}]*min-height:\s*0/s)
    expect(pageSource).toMatch(/\.scripts-content\s*\{[^}]*overflow:\s*hidden/s)
    expect(splitSource).toMatch(/\.script-split-view\s*\{[^}]*height:\s*100%/s)
    expect(splitSource).toMatch(/\.script-master-list\s*\{[^}]*overflow:\s*auto/s)
    expect(cardSource).toMatch(/\.users-list\s*\{[^}]*overflow:\s*auto/s)
    expect(splitSource).not.toContain('calc(100vh')
    expect(splitSource).not.toMatch(/max-height:\s*(?:\d+px|[^;]*vh)/)
  })
})
