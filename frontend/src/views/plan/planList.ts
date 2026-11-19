import type { PlanGetOut } from '@/api'
import { generateUniquePlanName } from '@/utils/planNameUtils'
import {
  PLAN_TYPE_REGISTRY,
  isKnownPlanType,
  type PlanConfigData,
  type PlanConfigType,
} from '@/utils/planTypeRegistry'

export interface PlanListItem {
  id: string
  name: string
  type: PlanConfigType
}

export function projectPlanList(
  response: Pick<PlanGetOut, 'index' | 'data'>,
  reportError: (message: string) => void
) {
  const nextPlanDataMap: Record<string, PlanConfigData> = {}
  const nextPlanList: PlanListItem[] = []
  const allPlanNames: string[] = []

  response.index.forEach(item => {
    const planId = item.uid
    const planData = response.data[planId] as PlanConfigData | undefined
    const planType = item.type as string

    if (!isKnownPlanType(planType)) {
      reportError(`跳过未注册的计划表类型: ${planType}`)
      return
    }
    if (!planData) {
      reportError(`跳过缺少配置数据的计划表: ${planId}`)
      return
    }

    const planDescriptor = PLAN_TYPE_REGISTRY[planType]
    let planName = planData.Info?.Name || ''
    if (!planName || planName === planDescriptor.defaultName) {
      planName = generateUniquePlanName(planType, allPlanNames)
    }

    allPlanNames.push(planName)
    nextPlanDataMap[planId] = planData
    nextPlanList.push({ id: planId, name: planName, type: planType })
  })

  return { nextPlanDataMap, nextPlanList }
}
