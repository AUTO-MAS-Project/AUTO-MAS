import { ref } from 'vue'
import { message } from 'ant-design-vue'
import type { PlanCreateIn, PlanDeleteIn, PlanGetIn, PlanReorderIn, PlanUpdateIn } from '../api'
import { Service } from '../api'

export function usePlanApi() {
  const loading = ref(false)

  // 获取所有计划
  const getPlans = async (planId?: string) => {
    loading.value = true
    try {
      const params: PlanGetIn = planId ? { planId } : {}
      const response = await Service.getPlanApiPlanGetPost(params)
      return response
    } catch (error) {
      console.error('获取计划失败:', error)
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
      // message.success('创建计划成功')
      return await Service.addPlanApiPlanAddPost(params)
    } catch (error) {
      console.error('创建计划失败:', error)
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
      // message.success('更新计划成功')
      return await Service.updatePlanApiPlanUpdatePost(params)
    } catch (error) {
      console.error('更新计划失败:', error)
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
      message.success('删除计划成功')
      return response
    } catch (error) {
      console.error('删除计划失败:', error)
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
      message.success('重新排序成功')
      return response
    } catch (error) {
      console.error('重新排序失败:', error)
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
