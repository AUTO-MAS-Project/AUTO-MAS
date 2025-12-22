import { ref } from 'vue'
import { message } from 'ant-design-vue'
import type { PlanCreateIn, PlanDeleteIn, PlanGetIn, PlanReorderIn, PlanUpdateIn } from '@/api'
import { Service } from '@/api'
import { getLogger } from '@/utils/logger'
import { useAudioPlayer } from '@/composables/useAudioPlayer'

const logger = getLogger('计划API')

export function usePlanApi() {
  const loading = ref(false)

  // 获取所有计划
  const getPlans = async (planId?: string) => {
    loading.value = true
    try {
      const params: PlanGetIn = planId ? { planId } : {}
      return await Service.getPlanApiPlanGetPost(params)
    } catch (error) {
      logger.error('获取计划失败:', error)
      message.error('获取计划失败')
      throw error
    } finally {
      loading.value = false
    }
  }

  // 创建计划
  const createPlan = async (type: string) => {
    loading.value = true
    try {
      if (type === 'MaaPlanConfig') {
        type = 'MaaPlan'
      }
      const params: PlanCreateIn = { type }
      const response = await Service.addPlanApiPlanAddPost(params)

      // 播放添加计划成功音频
      const { playSound } = useAudioPlayer()
      await playSound('add_schedule')

      return response
    } catch (error) {
      logger.error('创建计划失败:', error)
      message.error('创建计划失败')
      throw error
    } finally {
      loading.value = false
    }
  }

  // 更新计划
  const updatePlan = async (planId: string, data: Record<string, Record<string, any>>) => {
    loading.value = true
    try {
      const params: PlanUpdateIn = { planId, data }

      return await Service.updatePlanApiPlanUpdatePost(params)
    } catch (error) {
      logger.error('更新计划失败:', error)
      message.error('更新计划失败')
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
      const response = await Service.deletePlanApiPlanDeletePost(params)

      // 播放删除计划成功音频
      const { playSound } = useAudioPlayer()
      await playSound('delete_schedule')

      return response
    } catch (error) {
      logger.error('删除计划失败:', error)
      message.error('删除计划失败')
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
      const response = await Service.reorderPlanApiPlanOrderPost(params)

      return response
    } catch (error) {
      logger.error('重新排序失败:', error)
      message.error('重新排序失败')
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
