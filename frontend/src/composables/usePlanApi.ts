import { ref } from 'vue'
import { message } from 'ant-design-vue'
import type { PlanCreateIn, PlanDeleteIn, PlanGetIn, PlanReorderIn, PlanUpdateIn } from '@/api'
import { Service } from '@/api'
import { useAudioPlayer } from '@/composables/useAudioPlayer'

const logger = window.electronAPI.getLogger('计划API')

export function usePlanApi() {
  const loading = ref(false)

  const requireSuccess = <T extends { code?: number; message?: string }>(
    response: T,
    fallbackMessage: string
  ): T => {
    if (response.code !== 200) {
      throw new Error(response.message || fallbackMessage)
    }
    return response
  }

  // 获取所有计划
  const getPlans = async (planId?: string) => {
    loading.value = true
    try {
      const params: PlanGetIn = planId ? { planId } : {}
      const response = await Service.getPlanApiPlanGetPost(params)
      return requireSuccess(response, '获取计划失败')
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`获取计划失败: ${errorMsg}`)
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
      requireSuccess(response, '创建计划失败')

      // 播放添加计划成功音频
      const { playSound } = useAudioPlayer()
      await playSound('add_schedule')

      return response
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`创建计划失败: ${errorMsg}`)
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
      const response = await Service.updatePlanApiPlanUpdatePost(params)
      return requireSuccess(response, '更新计划失败')
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`更新计划失败: ${errorMsg}`)
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
      requireSuccess(response, '删除计划失败')

      // 播放删除计划成功音频
      const { playSound } = useAudioPlayer()
      await playSound('delete_schedule')

      return response
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`删除计划失败: ${errorMsg}`)
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
      return requireSuccess(response, '重新排序失败')
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`重新排序失败: ${errorMsg}`)
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
