import type { PlanGetOut } from '@/api'
import type { UnavailableConfigCard } from '@/components/UnavailableConfigCards.vue'
import { generateUniquePlanName } from '@/utils/planNameUtils'
import { getPlanTypeOption, type PlanConfigData } from '@/utils/planTypeRegistry'
import type { PluginScriptTypes } from '@/utils/pluginScriptTypes'

export interface PlanListItem {
  id: string
  name: string
  type: string
  typeLabel: string
}

export function projectPlanList(
  response: { index: { uid: string; type: string }[]; data: PlanGetOut['data'] },
  plugins: PluginScriptTypes,
  reportError: (message: string) => void
) {
  const nextPlanDataMap: Record<string, PlanConfigData> = {}
  const nextPlanList: PlanListItem[] = []
  const allPlanNames: string[] = []

  response.index.forEach(item => {
    const planId = item.uid
    const planData = response.data[planId] as PlanConfigData | undefined
    const planType = item.type
    const planDescriptor = getPlanTypeOption(planType, plugins)

    if (!planDescriptor) {
      reportError(`跳过未注册的计划表类型: ${planType}`)
      return
    }
    if (!planData) {
      reportError(`跳过缺少配置数据的计划表: ${planId}`)
      return
    }

    let planName = planData.Info?.Name || ''
    if (!planName || planName === planDescriptor.defaultName) {
      planName = generateUniquePlanName(planDescriptor.defaultName, allPlanNames)
    }

    allPlanNames.push(planName)
    nextPlanDataMap[planId] = planData
    nextPlanList.push({
      id: planId,
      name: planName,
      type: planType,
      typeLabel: planDescriptor.selectorTag,
    })
  })

  return { nextPlanDataMap, nextPlanList }
}

/** 所属插件不可用的计划表（不在 index / data 里），投影成只读卡片。 */
export function projectUnavailablePlans(
  response: Pick<PlanGetOut, 'unavailable'>
): UnavailableConfigCard[] {
  return (response.unavailable ?? []).map(item => ({
    uid: item.uid,
    name: item.name ?? '',
    typeLabel: item.typeLabel,
    reason: item.reason,
    plugin: item.plugin,
    detail: item.detail,
  }))
}
