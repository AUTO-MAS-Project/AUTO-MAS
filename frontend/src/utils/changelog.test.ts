import { describe, expect, it } from 'vitest'
import {
  buildChangelogSections,
  compareVersions,
  orderCategories,
  sortVersionsDesc,
} from './changelog'

describe('changelog 版本排序', () => {
  it('beta.10 排在 beta.2 之前（按数值而不是字符串）', () => {
    expect(sortVersionsDesc(['v5.5.0-beta.2', 'v5.5.0-beta.10', 'v5.5.0-beta.3'])).toEqual([
      'v5.5.0-beta.10',
      'v5.5.0-beta.3',
      'v5.5.0-beta.2',
    ])
  })

  it('正式版排在同号预发布版之前，跨主次版本按数值比较', () => {
    expect(sortVersionsDesc(['v5.5.0-beta.10', 'v5.5.0', 'v5.4.9', 'v5.10.0'])).toEqual([
      'v5.10.0',
      'v5.5.0',
      'v5.5.0-beta.10',
      'v5.4.9',
    ])
    expect(compareVersions('v5.5.0-beta.2', 'v5.5.0-beta.10')).toBeLessThan(0)
    expect(compareVersions('v5.5.0', '5.5.0')).toBe(0)
  })

  it('合并即入账的「未发布」段不是版本号，排在最前', () => {
    expect(sortVersionsDesc(['v5.5.0-beta.6', '未发布', 'v5.4.0'])).toEqual([
      '未发布',
      'v5.5.0-beta.6',
      'v5.4.0',
    ])
  })
})

describe('changelog 分类排序', () => {
  it('破坏性变更、本次亮点被提前，其余分类保持原顺序，未知分类仍出现', () => {
    const ordered = orderCategories({
      新增: ['a'],
      修复: ['b'],
      本次亮点: ['h'],
      未知的新分类: ['u'],
      破坏性变更: ['c'],
    })
    expect(ordered.map(c => c.name)).toEqual([
      '破坏性变更',
      '本次亮点',
      '新增',
      '修复',
      '未知的新分类',
    ])
    expect(ordered.map(c => c.kind)).toEqual([
      'critical',
      'highlight',
      'normal',
      'normal',
      'normal',
    ])
  })

  it('空分类被丢掉', () => {
    expect(orderCategories({ 新增: [], 修复: ['x'] }).map(c => c.name)).toEqual(['修复'])
  })
})

describe('buildChangelogSections', () => {
  it('按版本降序分区块，每个区块内分类置顶', () => {
    const sections = buildChangelogSections({
      'v5.5.0-beta.2': { 修复: ['old fix'] },
      'v5.5.0-beta.10': { 新增: ['new'], 破坏性变更: ['breaking'] },
    })
    expect(sections.map(s => s.version)).toEqual(['v5.5.0-beta.10', 'v5.5.0-beta.2'])
    expect(sections[0].categories.map(c => c.name)).toEqual(['破坏性变更', '新增'])
  })

  it('空输入与没有内容的版本段不会崩', () => {
    expect(buildChangelogSections(undefined)).toEqual([])
    expect(buildChangelogSections({})).toEqual([])
    expect(buildChangelogSections({ 'v1.0.0': {} })).toEqual([])
  })
})
