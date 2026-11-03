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
  stages.filter(stage => stage.Value && /^\d+$/.test(stage.Drop) && !isOrundumStage(stage))

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

// 只投影旧选择用于展示；用户主动编辑后，再由完整的新选择替换旧项。
export const getLegacyEventDepotPlans = (
  plans: EventDepotMaintainPlan[],
  stages: ActivityItem[],
  template: ('material' | 'orundum')[] = []
): Map<string, EventDepotMaintainPlan> => {
  const kinds = stages.length
    ? stages.map(stage =>
        isOrundumStage(stage) ? 'orundum' : /^\d+$/.test(stage.Drop) ? 'material' : undefined
      )
    : template
  const result = new Map<string, EventDepotMaintainPlan>()
  for (const plan of plans) {
    const index = plan.StageIndex
    if (
      (!plan.LegacyActivityFirst && !plan.LegacyIndex) ||
      !Number.isInteger(index) ||
      !index ||
      index < 1
    )
      continue
    const sourceKind = plan.StageType ?? 'material'
    const pool = sourceKind === 'activity' ? kinds : kinds.filter(kind => kind === sourceKind)
    if (plan.Skip && index > pool.length) continue
    // 沿用旧序号越界时回到第一关的选择，活动空档仅借上期类别展示。
    const position = index > pool.length ? 0 : index - 1
    const kind = pool[position]
    if (!kind) continue
    const stageIndex = pool.slice(0, position + 1).filter(value => value === kind).length
    const identity = eventStageIdentity(kind, stageIndex)
    const previous = result.get(identity)
    // 多个旧序号回退到同一关时，保留最高自定义目标，活动默认不抬高它。
    if (previous) {
      if (previous.Skip && !plan.Skip) continue
      if (!plan.Skip || previous.Skip) {
        const count =
          kind === 'orundum' ? (plan.OrundumDropCount ?? plan.DropCount) : plan.DropCount
        const previousCount =
          kind === 'orundum'
            ? (previous.OrundumDropCount ?? previous.DropCount)
            : previous.DropCount
        if (plan.LegacyActivityFirst || (!previous.LegacyActivityFirst && previousCount >= count))
          continue
      }
    }
    const { key: _key, ...target } = plan
    result.set(identity, {
      ...target,
      StageType: kind,
      StageIndex: stageIndex,
    })
  }
  return result
}

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
