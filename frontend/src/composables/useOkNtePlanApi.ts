import { OknteService } from '@/api'
import { beginAnalyticsOperation } from '@/utils/analytics'
export async function saveOkNtePlan(
  planId: string,
  day: string,
  configs: Record<string, unknown>,
  replace = false
) {
  const operation = beginAnalyticsOperation('plan_edit_finished')
  try {
    const response = await OknteService.saveOkntePlanConfigsApiScriptsOkntePlanSavePost({
      plan_id: planId,
      day,
      configs,
      replace,
    })
    operation.finish({
      plan_type: 'OkNtePlanConfig',
      view_kind: 'complex',
      operation_kind: 'save',
      outcome: response.code === 200 ? 'success' : 'failure',
    })
    return response
  } catch (error) {
    operation.finish({
      plan_type: 'OkNtePlanConfig',
      view_kind: 'complex',
      operation_kind: 'save',
      outcome: 'failure',
    })
    throw error
  }
}
