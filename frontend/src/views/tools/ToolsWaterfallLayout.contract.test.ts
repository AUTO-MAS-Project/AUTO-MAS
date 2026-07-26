import { readFileSync } from 'node:fs'
import { fileURLToPath, URL } from 'node:url'
import { describe, expect, it } from 'vitest'

const gameSign = readFileSync(fileURLToPath(new URL('./TabGameSign.vue', import.meta.url)), 'utf8')
const arknightsPC = readFileSync(
  fileURLToPath(new URL('./TabArknightsPC.vue', import.meta.url)),
  'utf8'
)

/**
 * 工具 Tab 瀑布双栏布局契约。
 *
 * 目标形态（iPad 设置式自适应瀑布双栏）：
 * - 宽容器（tools-page 容器查询 >980px）：卡片流入两列，各列独立纵向堆叠；
 *   使用 CSS multi-column（columns: 2），卡片 break-inside: avoid 防断裂，
 *   列间距使用现有 spacing token。
 * - 窄容器：保持单列堆叠（TabGameSign 为原有纵向 flex，TabArknightsPC 为默认块级流）。
 * - 卡片内部结构零改动：只允许动外层布局容器。
 */
describe('工具 Tab 瀑布双栏布局契约', () => {
  const cases: Array<[string, string]> = [
    ['TabGameSign', gameSign],
    ['TabArknightsPC', arknightsPC],
  ]

  it.each(cases)('%s 宽容器启用双栏 multi-column 瀑布布局', (_name, source) => {
    // 使用现有 tools-page 容器查询体系，约 980px 分界
    expect(source).toContain('@container tools-page (min-width: 981px)')
    // 推荐实现：CSS multi-column 双列
    expect(source).toContain('columns: 2')
    // 列间距使用现有 spacing token
    expect(source).toContain('column-gap: var(--v6-space-3)')
  })

  it.each(cases)('%s 卡片防断裂：break-inside avoid + inline-block 全宽', (_name, source) => {
    expect(source).toContain('break-inside: avoid')
    expect(source).toContain('display: inline-block')
    expect(source).toContain('width: 100%')
    expect(source).toContain('vertical-align: top')
  })

  it('TabGameSign 窄容器保持原有单列纵向 flex 堆叠', () => {
    expect(gameSign).toContain('flex-direction: column')
  })

  it('TabGameSign 异步任务面板横跨双栏，避免出现/消失导致卡片跳列', () => {
    expect(gameSign).toMatch(/\.tab-content > \.tools-task-panel \{\s*column-span: all;/)
  })

  it('TabArknightsPC 工具简介横幅横跨双栏，保持三段横排视觉', () => {
    expect(arknightsPC).toMatch(/\.tab-content > \.tool-intro \{\s*column-span: all;/)
  })

  it.each(cases)('%s 卡片内部栅格结构未被改动（a-row/a-col 原样保留）', (_name, source) => {
    // 只动外层布局容器：卡内 a-row :gutter=24 栅格保持原结构
    expect(source).toContain('<a-row :gutter="24">')
  })
})
