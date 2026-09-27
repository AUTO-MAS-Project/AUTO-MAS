import { translate as t } from '@/i18n'
import { ref } from 'vue'
import { message } from 'ant-design-vue'
import type { PlanCreateIn, PlanDeleteIn, PlanGetIn, PlanReorderIn, PlanUpdateIn } from '@/api'
import { Service } from '@/api'
import { useAudioPlayer } from '@/composables/useAudioPlayer'
import { useConfigEditSession } from '@/composables/useConfigEditSession'
import { getPlanCreateType, type PlanConfigType } from '@/utils/planTypeRegistry'

const logger = window.electronAPI.getLogger('计划API')

export function usePlanApi() {
  const loading = ref(false)
  const { ensureConfigEditSession, markConfigEditSaved } = useConfigEditSession()

  // 获取所有计划
  const getPlans = async (planId?: string) => {
    loading.value = true
    try {
      const params: PlanGetIn = planId ? { planId } : {}
      return await Service.getPlanApiPlanGetPost(params)
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

      const editSession = await ensureConfigEditSession('PlanConfig')
      if (!editSession) throw new Error('有其他用户正在编辑该配置')
      const params: PlanCreateIn = { type: createType, ...editSession }
      const response = await Service.addPlanApiPlanAddPost(params)
      if (response.code === 200) await markConfigEditSaved('PlanConfig')

      // 播放添加计划成功音频
      const { playSound } = useAudioPlayer()
      await playSound('add_schedule')

      return response
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
      const editSession = await ensureConfigEditSession('PlanConfig')
      if (!editSession) throw new Error('有其他用户正在编辑该配置')
      const params: PlanUpdateIn = { planId, data, ...editSession }

      const response = await Service.updatePlanApiPlanUpdatePost(params)
      if (response.code === 200) await markConfigEditSaved('PlanConfig')
      return response
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
      const editSession = await ensureConfigEditSession('PlanConfig')
      if (!editSession) throw new Error('有其他用户正在编辑该配置')
      const params: PlanDeleteIn = { planId, ...editSession }
      const response = await Service.deletePlanApiPlanDeletePost(params)
      if (response.code === 200) await markConfigEditSaved('PlanConfig')

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
      const editSession = await ensureConfigEditSession('PlanConfig')
      if (!editSession) throw new Error('有其他用户正在编辑该配置')
      const params: PlanReorderIn = { indexList, ...editSession }
      const response = await Service.reorderPlanApiPlanOrderPost(params)
      if (response.code === 200) await markConfigEditSaved('PlanConfig')

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
