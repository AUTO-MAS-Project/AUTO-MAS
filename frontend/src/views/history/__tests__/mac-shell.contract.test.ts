import { describe, expect, it } from 'vitest'
import historySource from '../index.vue?raw'
import detailSource from '../components/HistoryDetailPanel.vue?raw'
import listSource from '../components/HistoryRecordList.vue?raw'
import searchPanelSource from '../components/HistorySearchPanel.vue?raw'
import sidebarSource from '../components/HistoryDateSidebar.vue?raw'
import logicSource from '../useHistoryLogic.ts?raw'

describe('history macOS shell contract', () => {
  it('uses the shared compact page header instead of a standalone oversized title', () => {
    expect(historySource).toContain('<MacPageHeader')
    expect(historySource).toContain('title="历史记录"')
    expect(historySource).toContain('compact')
    expect(historySource).not.toContain('class="page-title"')
  })

  it('toolbar switches are connected to real rendering and refresh behavior', () => {
    expect(detailSource).toContain(':show-timestamp="showTimestamp"')
    expect(detailSource).toContain(':wrap-text="wrapText"')
    expect(detailSource).toContain(':auto-scroll="autoScroll"')
    expect(listSource).toContain('v-if="showTimestamp"')
    expect(listSource).toContain("'col-msg--wrap': wrapText")
    expect(listSource).toContain('container.scrollTop = container.scrollHeight')
    expect(logicSource).toContain('LIVE_REFRESH_INTERVAL_MS')
    expect(logicSource).toContain('handleSearch({ silent: true })')
    expect(logicSource).toContain('stopLiveRefresh()')
  })

  it('level filter exposes only 全部/错误/信息 (backend has DONE/ERROR only, no debug level)', () => {
    // 分段控件仅三段：全部 / 错误 / 信息
    expect(searchPanelSource).toContain("{ key: 'all', label: '全部' }")
    expect(searchPanelSource).toContain("{ key: 'error', label: '错误' }")
    expect(searchPanelSource).toContain("{ key: 'info', label: '信息' }")
    // 「调试」段与 debug 死代码不得回归
    const debugFreeSources = [
      searchPanelSource,
      sidebarSource,
      logicSource,
      listSource,
      detailSource,
    ]
    for (const source of debugFreeSources) {
      expect(source).not.toContain('调试')
      expect(source).not.toContain("'debug'")
      expect(source).not.toContain('-debug')
    }
    // 窄屏下拉与分段控件共用同一选项源（levelSegments 被两处 v-for 引用），保持同步
    const levelSegmentLoops = searchPanelSource.match(/v-for="opt in levelSegments"/g) ?? []
    expect(levelSegmentLoops).toHaveLength(2)
  })
})
