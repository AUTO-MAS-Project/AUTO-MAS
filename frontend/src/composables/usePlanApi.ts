import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { planApi } from '@/api'
import { useAudioPlayer } from '@/composables/useAudioPlayer'

const logger = window.electronAPI.getLogger('计划API')

export function usePlanApi() {
  const loading = ref(false)

  // 获取所有计划
  const getPlans = async (planId?: string) => {
    loading.value = true
    try {
      if (planId) {
        const response = await planApi.get(planId)
        return {
          code: response.code,
          status: response.status,
          message: response.message,
          index: [{ uid: planId, type: 'MaaPlanConfig' }],
          data: { [planId]: response.data },
        }
      }
      return await planApi.list()
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
      const response = await planApi.create({ type })

      // 播放添加计划成功音频
      const { playSound } = useAudioPlayer()
      await playSound('add_schedule')

      return {
        ...response,
        planId: response.id,
      }
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
      return await planApi.update(planId, { data })
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
      const response = await planApi.remove(planId)

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
      const response = await planApi.reorder({
        index_list: indexList,
      })

      return response
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
