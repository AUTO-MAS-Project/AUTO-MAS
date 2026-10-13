import type { ActivityItem } from '@/types/home'
export type EventDepotMaintainPlan = { StageIndex: number; DropCount: number }

// 活动列表中的搓玉效率会映射成固源岩 ID，必须同时检查原始掉落文案。
export const getEventDepotStages = (stages: ActivityItem[]): ActivityItem[] =>
  stages.filter(stage => stage.Value && /^\d+$/.test(stage.Drop) && !stage.DropName.includes('玉'))

export const getEventDepotPresets = (stages: ActivityItem[]): EventDepotMaintainPlan[] =>
  getEventDepotStages(stages).map((_, index) => ({ StageIndex: index + 1, DropCount: 200 }))

export const parseEventDepotPlans = (parsed: unknown): EventDepotMaintainPlan[] => {
  if (!Array.isArray(parsed)) return []
  return parsed.flatMap((plan, index) => {
    if (!plan || typeof plan !== 'object') return []
    // 旧版具体关卡计划按原列表顺序迁移，下一次保存时只写序号和目标。
    const stageIndex = plan.StageIndex ?? (typeof plan.Stage === 'string' ? index + 1 : undefined)
    return Number.isInteger(stageIndex) && stageIndex > 0 && typeof plan.DropCount === 'number'
      ? [{ StageIndex: stageIndex, DropCount: plan.DropCount }]
      : []
  })
}
