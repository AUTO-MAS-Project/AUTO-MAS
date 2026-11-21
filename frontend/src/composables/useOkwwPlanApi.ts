import { Service } from '@/api'
import { beginAnalyticsOperation } from '@/utils/analytics'

export async function saveOkwwPlan(
  planId: string,
  day: string,
  configs: Record<string, Record<string, unknown>>
) {
  const operation = beginAnalyticsOperation('plan_edit_finished')
  const dimensions = {
    plan_type: 'OkwwPlanConfig' as const,
    view_kind: 'complex' as const,
    operation_kind: 'save' as const,
  }
  try {
    const response = await Service.saveOkwwPlanConfigsApiApiScriptsOkwwPlanConfigsPost({
      plan_id: planId,
      day,
      configs,
    })
    if (response.code !== 200) throw new Error(response.message)
    operation.finish({ ...dimensions, outcome: 'success' })
  } catch (error) {
    operation.finish({ ...dimensions, outcome: 'failure' })
    throw error
  }
}

export async function readOkwwPlan(planId: string, day: string, locale: string) {
  const response = await Service.getOkwwPlanConfigsApiApiScriptsOkwwPlanConfigsGet(
    planId,
    day,
    locale.startsWith('zh') ? 'zh_CN' : locale.startsWith('ja') ? 'ja_JP' : 'en_US'
  )
  if (response.code !== 200) throw new Error(response.message)
  return response.data ?? []
}
