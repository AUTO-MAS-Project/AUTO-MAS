import { apiOutcome } from './featureAnalytics'

/** 只读取 MAS 接口公开的结果标记，不解释脚本私有配置或日志。 */
export function shellImportOutcome(result: {
  code?: number
  data?: Array<{ success?: boolean; skipped?: string[] }> | null
}) {
  if (result.code !== 200) return apiOutcome(result)
  const items = result.data ?? []
  if (!items.length) return 'skipped' as const
  const successful = items.filter(item => item.success).length
  return !successful
    ? ('failure' as const)
    : successful < items.length || items.some(item => item.skipped?.length)
      ? ('partial' as const)
      : ('success' as const)
}

export function adapterUpdateOutcome(
  result: {
    code?: number
    data?: {
      updated?: boolean
      checked?: boolean
      updateAvailable?: boolean
      update_available?: boolean
    } | null
  },
  action: 'check' | 'apply'
) {
  if (result.code !== 200) return apiOutcome(result)
  if (result.data?.updated) return 'updated' as const
  if (!result.data?.checked) return 'unknown' as const
  const available = result.data.updateAvailable || result.data.update_available
  if (!available) return 'current' as const
  return action === 'check' ? ('success' as const) : ('failure' as const)
}
