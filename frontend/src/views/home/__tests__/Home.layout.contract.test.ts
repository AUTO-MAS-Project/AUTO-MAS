import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const source = readFileSync(fileURLToPath(new URL('../../Home.vue', import.meta.url)), 'utf8')

/**
 * 主页网格占位契约（真机反馈：卫星图占位太小）。
 *
 * 心智模型：主页 3×3 大网格，卫星模块至少 2×1（行宽 2/3 以上）——
 * 宽屏 12 列中卫星占 8 列、最近活动占 4 列；
 * 中屏（容器 ≤1100px）两者各自独立成行；窄屏本就单列。
 * 仅约束 span 样式，拖拽/排序（normalizeHomeModuleOrder）行为不在此契约内。
 */
describe('Home layout contract', () => {
  it('uses a 12-column grid for the draggable module area', () => {
    expect(source).toContain('grid-template-columns: repeat(12, minmax(0, 1fr))')
  })

  it('gives the satellite module at least two thirds of the row on wide screens', () => {
    expect(source).toMatch(/\.home-module--satellite\s*\{[^}]*grid-column:\s*span 8/)
    expect(source).toMatch(/\.home-module--recent\s*\{[^}]*grid-column:\s*span 4/)
  })

  it('stacks satellite and recent modules into full rows on medium containers', () => {
    const midQuery = source.match(
      /@container home-layout \(max-width: 1100px\)\s*\{([\s\S]*?)\n\}/
    )?.[1]
    expect(midQuery).toBeTruthy()
    expect(midQuery).toMatch(
      /\.home-module--recent,\s*\.home-module--satellite\s*\{\s*grid-column:\s*1 \/ -1;/
    )
  })

  it('keeps all header toolbar buttons in the same default style (no primary/ghost outliers)', () => {
    // 真机反馈：右上工具行六个按钮（启动脚本/添加脚本/管理插件/编辑布局/查看公告/刷新）
    // 必须同为灰色默认态；「查看公告」不得再用 primary/ghost 蓝色描边整钮变色。
    const headerBlock = source.match(/<div class="header-actions">([\s\S]*?)<\/div>/)?.[1]
    expect(headerBlock).toBeTruthy()
    // 无 ghost 态、无静态 primary 态（编辑布局按钮仅在激活编辑时经 :type 动态变为 primary）
    expect(headerBlock).not.toMatch(/\bghost\b/)
    expect(headerBlock).not.toMatch(/[^:]type="primary"/)
    // 查看公告按钮不再有独立 min-width 撑宽，宽度与其余按钮一样由内容决定
    expect(source).not.toMatch(/\.notice-button\s*\{/)
  })

  it('lets the satellite card grow with its grid span and fill height as a flex column', () => {
    // min-height 提升到 clamp(400px, 40cqw, 560px)，大占位真正变大
    expect(source).toMatch(/\.satellite-card\s*\{[^}]*min-height:\s*clamp\(400px, 40cqw, 560px\)/)
    // 卡片为纵向 flex，SatelliteAnimation 容器才能吃满剩余高度
    expect(source).toMatch(/\.satellite-card\s*\{[^}]*flex-direction:\s*column/)
  })
})
