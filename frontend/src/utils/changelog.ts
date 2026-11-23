//   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
//   Copyright © 2025-2026 AUTO-MAS Team

/** 一个版本段：分类 -> 条目（条目是行内 Markdown 文本） */
type ChangelogEntries = Record<string, string[]>

/** 后端 /api/update/check 与编译期注入共用的形状：版本号 -> 分类 -> 条目 */
export type ChangelogData = Record<string, ChangelogEntries>

type ChangelogCategoryKind = 'critical' | 'highlight' | 'normal'

export interface ChangelogCategory {
  name: string
  kind: ChangelogCategoryKind
  items: string[]
}

interface ChangelogSection {
  version: string
  categories: ChangelogCategory[]
}

/**
 * 需要置顶并特殊渲染的分类。只识别这两个名字，其余分类一律按后端给的顺序常规展示，
 * 所以这里不是分类白名单：新增的未知分类照常出现，只是排在这两类之后。
 */
const CRITICAL_CATEGORY = '破坏性变更'
const HIGHLIGHT_CATEGORY = '本次亮点'

const PINNED_ORDER: Record<string, number> = {
  [CRITICAL_CATEGORY]: 0,
  [HIGHLIGHT_CATEGORY]: 1,
}

function categoryKind(name: string): ChangelogCategoryKind {
  if (name === CRITICAL_CATEGORY) return 'critical'
  if (name === HIGHLIGHT_CATEGORY) return 'highlight'
  return 'normal'
}

export { compareVersions } from '../../electron/services/updateVersion'
import { compareVersions } from '../../electron/services/updateVersion'

/** 合并即入账的暂存段排在发布版本之前。 */
const UNRELEASED_VERSION = '未发布'

export function sortVersionsDesc(versions: string[]): string[] {
  return [...versions].sort((a, b) => {
    if (a === UNRELEASED_VERSION || b === UNRELEASED_VERSION) {
      return a === b ? 0 : a === UNRELEASED_VERSION ? -1 : 1
    }
    return compareVersions(b, a)
  })
}

/**
 * 把一个版本段的分类排成展示顺序：「破坏性变更」「本次亮点」置顶，其余保持原顺序。
 * 空分类会被丢掉。
 */
export function orderCategories(entries: ChangelogEntries | null | undefined): ChangelogCategory[] {
  if (!entries || typeof entries !== 'object') return []
  const categories = Object.entries(entries)
    .filter(([, items]) => Array.isArray(items) && items.length > 0)
    .map(([name, items], index) => ({
      name,
      kind: categoryKind(name),
      items: items.map(item => (typeof item === 'string' ? item : JSON.stringify(item))),
      index,
    }))
  categories.sort((a, b) => {
    const pa = PINNED_ORDER[a.name] ?? Number.POSITIVE_INFINITY
    const pb = PINNED_ORDER[b.name] ?? Number.POSITIVE_INFINITY
    if (pa !== pb) return pa - pb
    return a.index - b.index
  })
  return categories.map(({ name, kind, items }) => ({ name, kind, items }))
}

/** 把接口/注入的数据整理成按版本降序、分类置顶后的展示结构；没有内容的版本段会被丢掉。 */
export function buildChangelogSections(data: ChangelogData | null | undefined): ChangelogSection[] {
  if (!data || typeof data !== 'object') return []
  return sortVersionsDesc(Object.keys(data))
    .map(version => ({ version, categories: orderCategories(data[version]) }))
    .filter(section => section.categories.length > 0)
}
