import type { PlanChangeHandler } from '@/utils/planTypeRegistry'
import { beginAnalyticsOperation } from '@/utils/analytics'

/** 一次批量编辑沿用逐日串行保存，但只产生一条统计，保留半批成功。 */
export async function savePlanDayBatch(
  save: PlanChangeHandler,
  changes: { path: string; config: unknown }[],
  viewKind: 'config' | 'simple',
  forceCustomStages?: boolean
): Promise<boolean> {
  if (!changes.length) return true
  const telemetry = beginAnalyticsOperation('plan_edit_finished')
  const props = {
    plan_type: 'MaaPlanConfig' as const,
    view_kind: viewKind === 'simple' ? ('simple' as const) : ('complex' as const),
    operation_kind: 'save' as const,
  }
  let saved = 0
  try {
    for (const [index, change] of changes.entries()) {
      if (
        await save(change.path, change.config, {
          refresh: index === changes.length - 1,
          forceCustomStages,
          analyticsBatch: true,
        })
      )
        saved++
    }
    telemetry.finish({
      ...props,
      outcome: saved === changes.length ? 'success' : saved > 0 ? 'partial' : 'failure',
    })
    return saved === changes.length
  } catch (error) {
    telemetry.finish({ ...props, outcome: saved > 0 ? 'partial' : 'unknown' })
    throw error
  }
}
