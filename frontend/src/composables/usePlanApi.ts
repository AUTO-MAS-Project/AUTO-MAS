import { translate as t } from '@/i18n'
import { ref } from 'vue'
import { message } from 'ant-design-vue'
import type { PlanCreateIn, PlanDeleteIn, PlanGetIn, PlanReorderIn, PlanUpdateIn } from '@/api'
import { Service } from '@/api'
import { useAudioPlayer } from '@/composables/useAudioPlayer'
import {
  getPlanCreateType,
  getPlanTypeDescriptor,
  type PlanConfigType,
} from '@/utils/planTypeRegistry'
import { analyticsCountBucket, beginAnalyticsOperation } from '@/utils/analytics'
import type { AnalyticsPlanType } from '@/types/analytics'

const logger = window.electronAPI.getLogger('计划API')
const planTypes = new Map<string, AnalyticsPlanType>()
function rememberPlanType(id: string, type: string): void {
  if (!planTypes.has(id) && planTypes.size >= 128) planTypes.delete(planTypes.keys().next().value!)
  planTypes.set(id, getPlanTypeDescriptor(type)?.configType ?? 'unknown')
}

export function usePlanApi() {
  const loading = ref(false)

  // 获取所有计划
  const getPlans = async (planId?: string) => {
    loading.value = true
    try {
      const params: PlanGetIn = planId ? { planId } : {}
      const response = await Service.getPlanApiPlanGetPost(params)
      if (response.code === 200) {
        for (const item of response.index) rememberPlanType(item.uid, item.type)
      }
      return response
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`获取计划失败: ${errorMsg}`)
      message.error(t('misc.couldNotLoadPlan'))
      throw error
    } finally {
      loading.value = false
    }
  }

  // 创建计划
  const createPlan = async (type: PlanConfigType) => {
    const operation = beginAnalyticsOperation('plan_manage_finished')
    const dimensions = {
      action: 'create' as const,
      plan_type: getPlanTypeDescriptor(type)?.configType ?? ('unknown' as const),
      count_bucket: '1' as const,
    }
    loading.value = true
    try {
      const createType = getPlanCreateType(type)
      if (!createType) {
        throw new Error(t('misc.unsupportedPlanTypeP0', { p0: type }))
      }

      const params: PlanCreateIn = { type: createType }
      const response = await Service.addPlanApiPlanAddPost(params)
      operation.finish({
        ...dimensions,
        outcome: response.code === 200 && response.planId ? 'success' : 'failure',
      })
      if (response.code === 200 && response.planId) rememberPlanType(response.planId, type)

      // 播放添加计划成功音频
      const { playSound } = useAudioPlayer()
      await playSound('add_schedule')

      return response
    } catch (error) {
      operation.finish({ ...dimensions, outcome: 'failure' })
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`创建计划失败: ${errorMsg}`)
      message.error(t('misc.couldNotCreatePlan'))
      throw error
    } finally {
      loading.value = false
    }
  }

  // 更新计划
  const updatePlan = async (
    planId: string,
    data: PlanUpdateIn['data'],
    viewKind: 'simple' | 'complex' | 'unknown' = 'unknown',
    analyticsBatch = false
  ) => {
    const editOperation =
      !analyticsBatch &&
      (Object.keys(data).some(key => key !== 'Info') ||
        Object.keys(data.Info ?? {}).some(key => key !== 'Name'))
        ? beginAnalyticsOperation('plan_edit_finished')
        : null
    const editProps = {
      plan_type: planTypes.get(planId) ?? 'unknown',
      view_kind: viewKind,
      operation_kind: 'save' as const,
    }
    const operation =
      data.Info?.Name !== undefined ? beginAnalyticsOperation('plan_manage_finished') : null
    const dimensions = {
      action: 'rename' as const,
      plan_type: planTypes.get(planId) ?? 'unknown',
      count_bucket: '1' as const,
    }
    loading.value = true
    try {
      const params: PlanUpdateIn = { planId, data }

      const response = await Service.updatePlanApiPlanUpdatePost(params)
      if (response.code !== 200) {
        throw new Error(response.message || t('misc.couldNotUpdatePlan'))
      }
      operation?.finish({ ...dimensions, outcome: 'success' })
      editOperation?.finish({ ...editProps, outcome: 'success' })
      return response
    } catch (error) {
      operation?.finish({ ...dimensions, outcome: 'failure' })
      editOperation?.finish({ ...editProps, outcome: 'failure' })
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`更新计划失败: ${errorMsg}`)
      message.error(t('misc.couldNotUpdatePlan'))
      throw error
    } finally {
      loading.value = false
    }
  }

  // 删除计划
  const deletePlan = async (planId: string) => {
    const operation = beginAnalyticsOperation('plan_manage_finished')
    const dimensions = {
      action: 'delete' as const,
      plan_type: planTypes.get(planId) ?? 'unknown',
      count_bucket: '1' as const,
    }
    loading.value = true
    try {
      const params: PlanDeleteIn = { planId }
      const response = await Service.deletePlanApiPlanDeletePost(params)
      operation.finish({ ...dimensions, outcome: response.code === 200 ? 'success' : 'failure' })
      if (response.code === 200) planTypes.delete(planId)

      // 播放删除计划成功音频
      const { playSound } = useAudioPlayer()
      await playSound('delete_schedule')

      return response
    } catch (error) {
      operation.finish({ ...dimensions, outcome: 'failure' })
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`删除计划失败: ${errorMsg}`)
      message.error(t('misc.couldNotDeletePlan'))
      throw error
    } finally {
      loading.value = false
    }
  }

  // 重新排序计划
  const reorderPlans = async (indexList: string[]) => {
    const operation = beginAnalyticsOperation('plan_manage_finished')
    const types = new Set(indexList.map(id => planTypes.get(id) ?? 'unknown'))
    const plan_type = types.has('unknown')
      ? 'unknown'
      : types.size > 1
        ? 'multi'
        : (types.values().next().value ?? 'unknown')
    const dimensions = {
      action: 'reorder' as const,
      plan_type,
      count_bucket: analyticsCountBucket(indexList.length),
    }
    loading.value = true
    try {
      const params: PlanReorderIn = { indexList }
      const response = await Service.reorderPlanApiPlanOrderPost(params)
      operation.finish({ ...dimensions, outcome: response.code === 200 ? 'success' : 'failure' })

      return response
    } catch (error) {
      operation.finish({ ...dimensions, outcome: 'failure' })
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`重新排序失败: ${errorMsg}`)
      message.error(t('misc.couldNotReorder'))
      throw error
    } finally {
      loading.value = false
    }
  }

  return {
    loading,
    getPlans,
    createPlan,
    updatePlan,
    deletePlan,
    reorderPlans,
  }
}
