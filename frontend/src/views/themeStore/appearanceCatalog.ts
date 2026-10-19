import type { OnlineAppearanceListResult, OnlineAppearanceQuery } from '@/types/appearance'
import type { AppearanceCategory } from '@/types/mascotPack'

/** 分享站按单个分类分页；取两类的前 N 项，再按发布时间合成当前页。 */
export async function loadAppearanceCatalog(
  query: OnlineAppearanceQuery,
  list: (
    query: OnlineAppearanceQuery,
    category: AppearanceCategory
  ) => Promise<OnlineAppearanceListResult>
): Promise<OnlineAppearanceListResult> {
  const page = query.page ?? 1
  const pageSize = query.pageSize ?? 12
  const end = page * pageSize
  const batchSize = Math.min(end, 50)
  const results = await Promise.all(
    (['theme', 'mascot'] as const).map(async category => {
      const items: NonNullable<OnlineAppearanceListResult['items']> = []
      let total = 0
      for (let nextPage = 1; items.length < end; nextPage++) {
        const result = await list({ ...query, page: nextPage, pageSize: batchSize }, category)
        if (!result.success) return result
        items.push(...(result.items ?? []).map(item => ({ ...item, categoryKey: category })))
        total = result.pagination?.total ?? items.length
        if (!result.pagination?.hasNext || !result.items?.length) break
      }
      return { success: true, items, pagination: { page, pageSize, total, hasNext: false } }
    })
  )
  const failed = results.find(result => !result.success)
  if (failed) return failed
  const total = results.reduce((sum, result) => sum + (result.pagination?.total ?? 0), 0)
  const items = results
    .flatMap(result => result.items ?? [])
    .sort((a, b) => (Date.parse(b.publishedAt) || 0) - (Date.parse(a.publishedAt) || 0))
  return {
    success: true,
    items: items.slice(end - pageSize, end),
    pagination: { page, pageSize, total, hasNext: total > end },
  }
}
