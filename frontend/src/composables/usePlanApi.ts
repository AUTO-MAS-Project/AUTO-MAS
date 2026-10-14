import { translate as t } from '@/i18n'
import { ref } from 'vue'
import { message } from 'ant-design-vue'
import type {
  CollectionOrderItem,
  PlanCreateIn,
  PlanDeleteIn,
  PlanGetIn,
  PlanGetOut,
  PlanReorderIn,
  PlanUpdateIn,
} from '@/api'
import { Service } from '@/api'
import { useAudioPlayer } from '@/composables/useAudioPlayer'
import { getPlanCreateType, type PlanConfigType } from '@/utils/planTypeRegistry'
import { requestApi } from '@/utils/apiResult'

const logger = window.electronAPI.getLogger('计划API')

/** Normalized plan response consumed by the legacy selector components. */
type PlanResponse = PlanGetOut & {
  /** Stable alias retained while the page migrates from ``index`` to ``order``. */
  index: CollectionOrderItem[]
}

const toLegacyFieldName = (key: string): string =>
  key
    .replace(/_([a-z])/g, (_, letter: string) => letter.toUpperCase())
    .replace(/^./, c => c.toUpperCase())

const fromLegacyFieldName = (key: string): string =>
  key
    .replace(/([A-Z])/g, '_$1')
    .replace(/^_/, '')
    .toLowerCase()

const normalizePlanEntry = (value: unknown): Record<string, unknown> => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {}
  const input = value as Record<string, unknown>
  const result: Record<string, unknown> = {}
  for (const [key, child] of Object.entries(input)) {
    if (key === 'ui') {
      result.ui = child
      continue
    }
    const legacyKey = key === 'all' ? 'ALL' : toLegacyFieldName(key)
    if (child && typeof child === 'object' && !Array.isArray(child)) {
      result[legacyKey] = normalizePlanEntry(child)
    } else {
      result[legacyKey] = child
    }
  }
  return result
}

const normalizePlanData = (
  data: Record<string, unknown> | undefined
): Record<string, Record<string, unknown>> =>
  Object.fromEntries(
    Object.entries(data ?? {}).map(([uid, value]) => [uid, normalizePlanEntry(value)])
  )

const toBackendPlanPatch = (value: unknown): unknown => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return value
  return Object.fromEntries(
    Object.entries(value as Record<string, unknown>).map(([key, child]) => [
      key === 'ALL' ? 'all' : fromLegacyFieldName(key),
      toBackendPlanPatch(child),
    ])
  )
}

export function usePlanApi() {
  const loading = ref(false)

  // 获取所有计划
  const getPlans = async (planId?: string): Promise<PlanResponse> => {
    loading.value = true
    try {
      const params: PlanGetIn = planId ? { planId } : {}
      const response = await requestApi(
        () => Service.getPlansApiPlanGetPost(params),
        t('misc.couldNotLoadPlan')
      )
      return {
        ...response,
        data: normalizePlanData(response.data),
        index: response.order ?? [],
      }
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
    loading.value = true
    try {
      const createType = getPlanCreateType(type)
      if (!createType) {
        throw new Error(t('misc.unsupportedPlanTypeP0', { p0: type }))
      }

      const params: PlanCreateIn = { scriptType: createType }
      const response = await requestApi(
        () => Service.addPlanApiPlanAddPost(params),
        t('misc.couldNotCreatePlan')
      )

      // 播放添加计划成功音频
      const { playSound } = useAudioPlayer()
      await playSound('add_schedule')

      return { ...response, data: normalizePlanEntry(response.data) }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`创建计划失败: ${errorMsg}`)
      message.error(t('misc.couldNotCreatePlan'))
      throw error
    } finally {
      loading.value = false
    }
  }

  // 更新计划
  const updatePlan = async (planId: string, data: PlanUpdateIn['data']) => {
    loading.value = true
    try {
      const params: PlanUpdateIn = {
        planId,
        data: toBackendPlanPatch(data) as Record<string, unknown>,
      }

      return await requestApi(
        () => Service.updatePlanApiPlanUpdatePost(params),
        t('misc.couldNotUpdatePlan')
      )
    } catch (error) {
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
    loading.value = true
    try {
      const params: PlanDeleteIn = { planId }
      const response = await requestApi(
        () => Service.deletePlanApiPlanDeletePost(params),
        t('misc.couldNotDeletePlan')
      )

      // 播放删除计划成功音频
      const { playSound } = useAudioPlayer()
      await playSound('delete_schedule')

      return response
    } catch (error) {
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
    loading.value = true
    try {
      const params: PlanReorderIn = { indexList }
      const response = await requestApi(
        () => Service.orderPlansApiPlanOrderPost(params),
        t('misc.couldNotReorder')
      )

      return response
    } catch (error) {
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
