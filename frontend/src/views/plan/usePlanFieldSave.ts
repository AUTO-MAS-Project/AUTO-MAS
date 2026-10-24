import type { PlanChangeOptions } from '@/utils/planTypeRegistry'
import type { usePlanApi } from '@/composables/usePlanApi'

/** 字段持久化与批次上下文由同一入口传递，页面继续拥有回读和草稿。 */
export function usePlanFieldSave(
  update: ReturnType<typeof usePlanApi>['updatePlan'],
  viewKind: () => 'simple' | 'complex'
) {
  const logger = window.electronAPI.getLogger('计划管理')
  return async (
    planId: string,
    changes: Parameters<typeof update>[1],
    options?: PlanChangeOptions
  ): Promise<boolean> => {
    if (!planId) return false
    try {
      await update(planId, changes, viewKind(), options?.analyticsBatch)
      return true
    } catch (error) {
      const reason = error instanceof Error ? error.message : String(error)
      logger.error('保存计划字段失败: ' + reason)
      options?.onError?.(reason)
      return false
    }
  }
}
