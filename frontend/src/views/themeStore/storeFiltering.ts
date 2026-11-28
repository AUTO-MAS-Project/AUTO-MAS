import type { OnlineAppearanceItem } from '@/types/appearance'

export type StoreSortKey = 'latest' | 'popular' | 'updated'
export type StoreQuickFilter = 'all' | 'outdated'

export interface StoreTagSummary {
  tag: string
  count: number
}

const isOutdatedItem = (item: OnlineAppearanceItem): boolean =>
  Boolean(
    item.installed &&
    item.publishedVersionNo !== null &&
    item.publishedVersionNo > item.installed.versionNo
  )

/** 作品数量少于此阈值时使用紧凑横幅，首屏多露一行可直接试穿的卡片。 */
export const COMPACT_BANNER_ITEM_THRESHOLD = 30

export function shouldUseCompactBanner(totalCount: number): boolean {
  return totalCount < COMPACT_BANNER_ITEM_THRESHOLD
}

/** 按资源实际携带的 tags 动态汇总可筛选项，按出现次数降序排列。 */
export function collectStoreTags(items: readonly OnlineAppearanceItem[]): StoreTagSummary[] {
  const counts = new Map<string, number>()
  for (const item of items) {
    const unique = new Set((item.tags ?? []).map(tag => tag.trim()).filter(Boolean))
    for (const tag of unique) {
      counts.set(tag, (counts.get(tag) ?? 0) + 1)
    }
  }
  return [...counts.entries()]
    .map(([tag, count]) => ({ tag, count }))
    .sort((left, right) => right.count - left.count || left.tag.localeCompare(right.tag))
}

/**
 * 自动挑选精选横幅作品：
 * 排除已安装条目，优先按下载量降序，其次按发布时间降序。
 */
export function pickAutoFeaturedItem(
  items: readonly OnlineAppearanceItem[]
): OnlineAppearanceItem | null {
  const candidates = items.filter(item => !item.installed && item.publishedVersionNo !== null)
  if (candidates.length === 0) return null
  return [...candidates].sort((left, right) => {
    const downloadsDiff = (right.downloadCount ?? 0) - (left.downloadCount ?? 0)
    if (downloadsDiff !== 0) return downloadsDiff
    return (Date.parse(right.publishedAt) || 0) - (Date.parse(left.publishedAt) || 0)
  })[0]
}

export function filterAndSortStoreItems(
  items: readonly OnlineAppearanceItem[],
  options: {
    filter: StoreQuickFilter
    tag?: string | null
    sort: StoreSortKey
    installedOnly?: boolean
  }
): OnlineAppearanceItem[] {
  let list = [...items]
  if (options.installedOnly) {
    list = list.filter(item => Boolean(item.installed))
  }
  if (options.filter === 'outdated') {
    list = list.filter(isOutdatedItem)
  }
  if (options.tag) {
    list = list.filter(item => (item.tags ?? []).includes(options.tag as string))
  }
  if (options.sort === 'popular') {
    list.sort((left, right) => {
      const diff = (right.downloadCount ?? 0) - (left.downloadCount ?? 0)
      if (diff !== 0) return diff
      return (Date.parse(right.publishedAt) || 0) - (Date.parse(left.publishedAt) || 0)
    })
  } else if (options.sort === 'updated') {
    list.sort(
      (left, right) =>
        (Date.parse(right.updatedAt || right.publishedAt) || 0) -
        (Date.parse(left.updatedAt || left.publishedAt) || 0)
    )
  } else {
    list.sort(
      (left, right) =>
        (Date.parse(right.publishedAt || right.updatedAt) || 0) -
        (Date.parse(left.publishedAt || left.updatedAt) || 0)
    )
  }
  return list
}

export function formatDownloadCount(count: number | undefined): string {
  if (typeof count !== 'number' || !Number.isFinite(count) || count < 0) return '0'
  return count.toLocaleString('en-US')
}
