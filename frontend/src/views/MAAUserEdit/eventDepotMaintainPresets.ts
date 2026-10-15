import type { ActivityItem } from '@/types/home'
import { resolveActivityStage } from './activityStages'

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
  [key: string]: unknown
}

// 活动列表中的搓玉效率会映射成固源岩 ID，必须同时检查原始掉落文案。
export const getEventDepotStages = (stages: ActivityItem[]): ActivityItem[] =>
  stages.filter(
    stage =>
      stage.Value &&
      /^\d+$/.test(stage.Drop) &&
      !stage.DropName.includes('玉') &&
      !stage.Drop.includes('玉')
  )

export const getEventOrundumStages = (stages: ActivityItem[]): ActivityItem[] =>
  stages.filter(
    stage => stage.Value && (stage.DropName.includes('玉') || stage.Drop.includes('玉'))
  )

export const resolveEventDepotStage = (
  stages: ActivityItem[],
  plan: Pick<
    EventDepotMaintainPlan,
    'StageType' | 'StageIndex' | 'LegacyIndex' | 'LegacyActivityFirst'
  >
): ActivityItem | undefined => {
  if (plan.StageType === 'all') return undefined
  const candidates =
    plan.StageType === 'activity'
      ? stages
      : plan.StageType === 'orundum'
        ? getEventOrundumStages(stages)
        : getEventDepotStages(stages)
  if (
    (plan.StageIndex ?? 0) > candidates.length &&
    !plan.LegacyIndex &&
    !plan.LegacyActivityFirst
  ) {
    return undefined
  }
  return resolveActivityStage(candidates, plan.StageIndex)
}

// 保存动态模板，活动换期或关卡数量变化时无需重新导入。
export const getEventDepotPresets = (): EventDepotMaintainPlan[] => [
  { StageType: 'all', DropCount: 999, OrundumDropCount: 9999 },
]

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

export const getLegacyEventDepotPlans = (backupJson: string): EventDepotMaintainPlan[] => {
  try {
    const backup = JSON.parse(backupJson)
    const task = backup?.Task
    if (!task || typeof task !== 'object') return []
    const plans: EventDepotMaintainPlan[] = parseEventDepotPlans(
      JSON.parse(task.EventDepotMaintainPlans || '[]')
    ).map(plan => ({
      ...plan,
      StageType: plan.StageType ?? 'material',
      LegacyIndex: true,
    }))
    if (typeof task.ActivityStageIndex === 'number') {
      plans.push({
        StageType: 'activity',
        StageIndex: task.ActivityStageIndex,
        DropCount: 999,
        OrundumDropCount: 9999,
        MedicineCount: task.ActivityMedicineNumb ?? backup.Info?.MedicineNumb ?? 0,
        UseMedicine: (task.ActivityMedicineNumb ?? backup.Info?.MedicineNumb ?? 0) > 0,
        LegacyActivityFirst: true,
      })
    }
    return plans
  } catch {
    return []
  }
}
