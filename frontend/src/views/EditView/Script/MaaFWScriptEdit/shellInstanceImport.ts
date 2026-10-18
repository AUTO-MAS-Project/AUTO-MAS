import type { MaaFWShellInstanceImportItem } from '@/api'

/** 提示里每个用户最多列出几项被跳过的内容，其余写成「等 N 项」。 */
export const SKIPPED_PREVIEW_LIMIT = 5

type Translate = (key: string, named?: Record<string, unknown>) => string

export type ShellImportSummary = {
  /** 建成了用户的实例 */
  created: MaaFWShellInstanceImportItem[]
  /** 没建成用户的实例（找不到、新增被拒…） */
  failed: MaaFWShellInstanceImportItem[]
  /** 建成了、但有任务 / 选项在当前项目里对不上被跳过的实例 */
  partial: MaaFWShellInstanceImportItem[]
}

const isCreated = (item: MaaFWShellInstanceImportItem) => Boolean(item.success && item.userId)

export const summarizeShellImport = (
  results: readonly MaaFWShellInstanceImportItem[]
): ShellImportSummary => {
  const created = results.filter(isCreated)
  return {
    created,
    failed: results.filter(item => !isCreated(item)),
    partial: created.filter(item => (item.skipped?.length ?? 0) > 0),
  }
}

/** 列表太长时只留前 `limit` 项，`rest` 是省掉的项数。 */
export const truncateItems = (
  items: readonly string[],
  limit = SKIPPED_PREVIEW_LIMIT
): { shown: string[]; rest: number } => ({
  shown: items.slice(0, limit),
  rest: Math.max(items.length - limit, 0),
})

/** 实例来源去重后按出现顺序连起来（「MFAAvalonia / MXU」）。 */
export const describeShellSources = (sources: readonly string[]): string =>
  [...new Set(sources.filter(Boolean))].join(' / ')

/**
 * 提示里写的实例名：结果项带的实例名 → 列表里同 ID 的实例名 → 实例 ID（都拿不到才用）。
 * 找不到的实例结果项里没有名字，只有 `mfaa:default` 这种内部 ID，不能直接给人看。
 */
export const shellImportItemName = (
  item: MaaFWShellInstanceImportItem,
  names?: ReadonlyMap<string, string>
): string => item.instanceName || names?.get(item.instanceId) || item.instanceId

/**
 * 导入结束后那一条提示的正文：先写没导入成功的实例，再写导不全的用户。
 * 两者都没有时返回空数组，不弹提示。`names` 是实例 ID → 实例名。
 */
export const buildShellImportReportLines = (
  summary: ShellImportSummary,
  t: Translate,
  names?: ReadonlyMap<string, string>
): string[] => {
  const lines: string[] = []
  if (summary.failed.length > 0) {
    lines.push(t('edit.shellImportFailedHead', { count: summary.failed.length }))
    for (const item of summary.failed) {
      lines.push(
        t('edit.shellImportFailedLine', {
          name: shellImportItemName(item, names),
          reason: item.error || '-',
        })
      )
    }
  }
  const separator = t('edit.shellImportListSeparator')
  for (const item of summary.partial) {
    const skipped = item.skipped ?? []
    const { shown, rest } = truncateItems(skipped)
    const named = { name: item.name, count: skipped.length, items: shown.join(separator) }
    lines.push(
      rest > 0
        ? t('edit.shellImportSkippedLineMore', { ...named, rest })
        : t('edit.shellImportSkippedLine', named)
    )
  }
  return lines
}
