import { beforeAll, describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

/**
 * Lane 08: 历史与日志中心新 UI 功能收口
 * v6 设计令牌契约测试
 *
 * 断言 Lane 08 独占文件已迁移到 v6 设计令牌系统：
 * - 不再引用 --ant-color-* / --ant-space-* / --ant-radius-* / --ant-font-* 等 Ant Design 变量
 * - 不使用 !important 覆盖（v6 令牌已具备语义层级，无需强覆盖）
 * - 仅使用 <style scoped>，避免全局污染
 */

const frontendRoot = resolve(__dirname, '..', '..', '..', '..')

interface LaneFile {
  name: string
  path: string
}

const laneFiles: LaneFile[] = [
  {
    name: 'history/index.vue',
    path: resolve(frontendRoot, 'src/views/history/index.vue'),
  },
  {
    name: 'history/components/HistorySearchPanel.vue',
    path: resolve(frontendRoot, 'src/views/history/components/HistorySearchPanel.vue'),
  },
  {
    name: 'history/components/HistoryDateSidebar.vue',
    path: resolve(frontendRoot, 'src/views/history/components/HistoryDateSidebar.vue'),
  },
  {
    name: 'history/components/HistoryRecordList.vue',
    path: resolve(frontendRoot, 'src/views/history/components/HistoryRecordList.vue'),
  },
  {
    name: 'history/components/HistoryDetailPanel.vue',
    path: resolve(frontendRoot, 'src/views/history/components/HistoryDetailPanel.vue'),
  },
  {
    name: 'history/components/UserStatisticsCard.vue',
    path: resolve(frontendRoot, 'src/views/history/components/UserStatisticsCard.vue'),
  },
  {
    name: 'history/components/HistoryLogModal.vue',
    path: resolve(frontendRoot, 'src/views/history/components/HistoryLogModal.vue'),
  },
  {
    name: 'Logs.vue',
    path: resolve(frontendRoot, 'src/views/Logs.vue'),
  },
  {
    name: 'components/LogHighlightSettings.vue',
    path: resolve(frontendRoot, 'src/components/LogHighlightSettings.vue'),
  },
  {
    name: 'components/LogTimestampSelector.vue',
    path: resolve(frontendRoot, 'src/components/LogTimestampSelector.vue'),
  },
]

const readSource = (file: LaneFile): string => readFileSync(file.path, 'utf-8')

const extractStyleBlocks = (source: string): string[] => {
  const blocks: string[] = []
  const regex = /<style[^>]*>([\s\S]*?)<\/style>/g
  let match: RegExpExecArray | null
  while ((match = regex.exec(source)) !== null) {
    blocks.push(match[1])
  }
  return blocks
}

const antTokenPattern =
  /--ant-(color|space|radius|font|border|shadow|motion|line-height|padding|margin|size|weight)/

describe('Lane 08 v6 design token contract', () => {
  describe.each(laneFiles.map(f => [f.name, f] as const))('%s', (_name, file) => {
    let source: string
    beforeAll(() => {
      source = readSource(file)
    })

    it('uses v6 CSS variables', () => {
      const styleBlocks = extractStyleBlocks(source)
      const combined = styleBlocks.join('\n')
      // 仅当存在 style 块时才要求引用 v6 变量
      if (combined.trim().length > 0) {
        expect(combined).toContain('var(--v6-')
      }
    })

    it('does not reference Ant Design CSS variables in style blocks', () => {
      const styleBlocks = extractStyleBlocks(source)
      for (const block of styleBlocks) {
        // 允许 :deep(.ant-*) 选择器穿透（Ant Design 组件内部 class），
        // 但禁止引用 --ant-* 自定义属性
        expect(block).not.toMatch(antTokenPattern)
      }
    })

    it('does not use !important overrides in style blocks', () => {
      const styleBlocks = extractStyleBlocks(source)
      for (const block of styleBlocks) {
        expect(block).not.toContain('!important')
      }
    })

    it('uses only scoped style blocks', () => {
      const styleTagPattern = /<style([^>]*)>/g
      const tags: string[] = []
      let match: RegExpExecArray | null
      while ((match = styleTagPattern.exec(source)) !== null) {
        tags.push(match[1])
      }
      // 允许零 style 块；存在则必须全部为 scoped
      for (const attrs of tags) {
        expect(attrs).toContain('scoped')
      }
    })
  })
})

describe('Lane 08 history state component integration', () => {
  it('HistoryDetailPanel.vue imports v6 EmptyState', () => {
    const source = readFileSync(
      resolve(frontendRoot, 'src/views/history/components/HistoryDetailPanel.vue'),
      'utf-8'
    )
    expect(source).toContain("from '@/components/v6/EmptyState.vue'")
    expect(source).toContain('<EmptyState')
  })

  it('HistoryRecordList.vue imports v6 EmptyState', () => {
    const source = readFileSync(
      resolve(frontendRoot, 'src/views/history/components/HistoryRecordList.vue'),
      'utf-8'
    )
    expect(source).toContain("from '@/components/v6/EmptyState.vue'")
    expect(source).toContain('<EmptyState')
  })

  it('UserStatisticsCard.vue imports v6 EmptyState', () => {
    const source = readFileSync(
      resolve(frontendRoot, 'src/views/history/components/UserStatisticsCard.vue'),
      'utf-8'
    )
    expect(source).toContain("from '@/components/v6/EmptyState.vue'")
    expect(source).toContain('<EmptyState')
  })
})
