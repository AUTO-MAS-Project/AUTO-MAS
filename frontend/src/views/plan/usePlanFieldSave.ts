import type { PlanChangeOptions } from '@/utils/planTypeRegistry'
import type { usePlanApi } from '@/composables/usePlanApi'

// 辅助函数：根据路径构建嵌套对象
// 例如 "Info.Name" -> { Info: { Name: value } }
// 例如 "Monday.stages.stage_1" -> { Monday: { stages: { stage_1: value } } }
export const buildNestedObject = (path: string, value: any): Record<string, any> => {
  const keys = path.split('.')
  const result: Record<string, any> = {}
  let current = result

  for (let i = 0; i < keys.length - 1; i++) {
    current[keys[i]] = {}
    current = current[keys[i]]
  }

  current[keys[keys.length - 1]] = value
  return result
}

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
