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

interface ParsedVersion {
  release: number[]
  /** 无预发布段时为 null；正式版排在同号预发布版之前 */
  pre: (number | string)[] | null
}

function parseVersion(raw: string): ParsedVersion {
  const text = raw.trim().replace(/^v/i, '')
  const [main, ...rest] = text.split('-')
  const release = main.split('.').map(part => {
    const n = Number.parseInt(part, 10)
    return Number.isNaN(n) ? 0 : n
  })
  if (rest.length === 0) return { release, pre: null }
  const pre = rest
    .join('-')
    .split(/[.-]/)
    .filter(part => part.length > 0)
    .map(part => (/^\d+$/.test(part) ? Number.parseInt(part, 10) : part.toLowerCase()))
  return { release, pre }
}

function compareIdentifiers(a: number | string, b: number | string): number {
  if (typeof a === 'number' && typeof b === 'number') return a - b
  // 数字标识符排在字母标识符之前（与 semver 一致）
  if (typeof a === 'number') return -1
  if (typeof b === 'number') return 1
  return a < b ? -1 : a > b ? 1 : 0
}

/** 版本号升序比较：a < b 返回负数。beta.10 大于 beta.2，正式版大于同号预发布版。 */
export function compareVersions(a: string, b: string): number {
  const pa = parseVersion(a)
  const pb = parseVersion(b)
  const len = Math.max(pa.release.length, pb.release.length)
  for (let i = 0; i < len; i += 1) {
    const diff = (pa.release[i] ?? 0) - (pb.release[i] ?? 0)
    if (diff !== 0) return diff
  }
  if (pa.pre === null && pb.pre === null) return 0
  if (pa.pre === null) return 1
  if (pb.pre === null) return -1
  const preLen = Math.max(pa.pre.length, pb.pre.length)
  for (let i = 0; i < preLen; i += 1) {
    const ia = pa.pre[i]
    const ib = pb.pre[i]
    if (ia === undefined) return -1
    if (ib === undefined) return 1
    const diff = compareIdentifiers(ia, ib)
    if (diff !== 0) return diff
  }
  return 0
}

/** 版本号降序（最新在前） */
export function sortVersionsDesc(versions: string[]): string[] {
  return [...versions].sort((a, b) => compareVersions(b, a))
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
