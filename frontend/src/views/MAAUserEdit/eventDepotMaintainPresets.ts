import type { ActivityItem } from '@/types/home'

export type EventDepotStageType = 'material' | 'activity' | 'orundum' | 'all'
export type EventDepotMaintainPlan = {
  StageIndex?: number
  StageType?: EventDepotStageType
  DropCount: number
  OrundumDropCount?: number
  MedicineCount?: number
  UseMedicine?: boolean
  LegacyIndex?: boolean
  LegacyActivityFirst?: boolean
  // 前端勾选状态：true 表示本轮不刷这个关卡，后端解析时直接跳过。
  Skip?: boolean
  [key: string]: unknown
}

// 搓玉关在 MAA 侧固定按固源岩备料，与后端 activity_inventory 的取值保持一致。
export const ORUNDUM_ITEM_ID = '30012'

// 活动列表中的搓玉效率会映射成固源岩 ID，必须同时检查原始掉落文案。
export const isOrundumStage = (stage: ActivityItem): boolean =>
  stage.DropName.includes('玉') || stage.Drop.includes('玉')

// 计划在 MAA 侧实际备料的物品 ID（搓玉关为固源岩）。
export const eventDepotItemId = (stage: ActivityItem): string =>
  isOrundumStage(stage) ? ORUNDUM_ITEM_ID : stage.Drop

export const getEventDepotStages = (stages: ActivityItem[]): ActivityItem[] =>
  stages.filter(
    stage =>
      stage.Value && /^\d+$/.test(stage.Drop) && !isOrundumStage(stage)
  )

export const getEventOrundumStages = (stages: ActivityItem[]): ActivityItem[] =>
  stages.filter(stage => stage.Value && isOrundumStage(stage))

// 保存动态模板，活动换期或关卡数量变化时无需重新导入。
export const getEventDepotPresets = (): EventDepotMaintainPlan[] => [
  { StageType: 'all', DropCount: 999, OrundumDropCount: 9999 },
]

export const eventStageIdentity = (type: EventDepotStageType, index: number): string =>
  `${type}:${index}`

export const eventDepotPlanIdentity = (plan: EventDepotMaintainPlan) =>
  `${plan.StageType ?? 'material'}:${plan.StageType === 'all' ? '' : plan.StageIndex}`

export const parseEventDepotPlans = (parsed: unknown): EventDepotMaintainPlan[] => {
  if (!Array.isArray(parsed)) return []
  return parsed.flatMap((plan, index) => {
    if (!plan || typeof plan !== 'object' || typeof plan.DropCount !== 'number') return []
    // 旧版具体关卡计划按原列表顺序迁移；逐计划参数随编辑一起保留。
    const stageIndex = plan.StageIndex ?? (typeof plan.Stage === 'string' ? index + 1 : undefined)
    return plan.StageType === 'all' || (Number.isInteger(stageIndex) && stageIndex > 0)
      ? [{ ...plan, ...(stageIndex === undefined ? {} : { StageIndex: stageIndex }) }]
      : []
  })
}
