import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const source = readFileSync(
  fileURLToPath(new URL('./PluginInstanceList.vue', import.meta.url)),
  'utf8'
)

describe('PluginInstanceList switch styling', () => {
  it('moves the switch handle instead of translating its white pseudo-element', () => {
    expect(source).toMatch(
      /\.plugin-toggle-wrap :deep\(\.ant-switch-checked \.ant-switch-handle\)\s*\{[^}]*inset-inline-start:\s*calc\(100% - 16px\)/s
    )
    expect(source).not.toMatch(
      /\.plugin-toggle-wrap :deep\(\.ant-switch-checked \.ant-switch-handle::before\)\s*\{[^}]*transform:/s
    )
  })

  it('keeps the compact switch and plugin row vertically aligned', () => {
    expect(source).toMatch(
      /\.plugin-toggle-wrap\s*\{[^}]*inline-flex[^}]*align-items:\s*center[^}]*align-self:\s*center/s
    )
    expect(source).toMatch(
      /\.plugin-toggle-wrap :deep\(\.ant-switch\)\s*\{[^}]*width:\s*32px[^}]*height:\s*18px/s
    )
    expect(source).toMatch(/\.instance-item\s*\{[^}]*height:\s*56px/s)
  })
})

describe('PluginInstanceList row layout', () => {
  // 真机反馈：窄面板（约 380px）下版本号/运行中徽章挤占首行，实例名收缩到不可见。
  // 契约：实例名是主标题，必须以 flex 主元素占据剩余宽度并在截断时提供 title 提示；
  // 版本号与类型徽章降级到次行（plugin-meta-row）。

  it('keeps the instance name visible as the flexible primary title with a tooltip', () => {
    expect(source).toMatch(
      /\.plugin-name\s*\{[^}]*flex:\s*1 1 auto[^}]*min-width:\s*0[^}]*text-overflow:\s*ellipsis/s
    )
    // 名称不再用固定 max-width 上限（窄容器下会导致名称被版本/徽章挤没）
    expect(source).not.toMatch(/\.plugin-name\s*\{[^}]*max-width/s)
    expect(source).toMatch(/class="plugin-name"\s+:title="element\.name \|\| element\.id"/)
  })

  it('demotes version and type badge to the secondary meta row', () => {
    // 首行（plugin-name-row 到 plugin-meta-row 之间）不再包含版本号
    expect(source).not.toMatch(/plugin-name-row"((?!plugin-meta-row)[\s\S])*plugin-version/)
    // 次行按 版本号 -> 类型徽章 -> 提供者描述 排列
    expect(source).toMatch(
      /class="plugin-meta-row">[\s\S]*?plugin-version[\s\S]*?plugin-type-badge[\s\S]*?class="plugin-desc"/
    )
    // 独立的右侧 plugin-meta 徽章列已移除
    expect(source).not.toMatch(/class="plugin-meta"/)
    // 描述截断时提供完整 title
    expect(source).toMatch(/class="plugin-desc"\s+:title="getPluginDescription\(element\)"/)
  })
})
