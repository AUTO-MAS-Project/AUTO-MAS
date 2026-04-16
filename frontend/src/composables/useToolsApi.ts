import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { toolsApi, type ToolsConfigRead } from '@/api'

export function useToolsApi() {
  const loading = ref(false)
  const logger = window.electronAPI.getLogger('工具API')

  /**
   * 获取工具
   */
  const getTools = async (): Promise<ToolsConfigRead> => {
    loading.value = true
    try {
      const response = await toolsApi.get()
      if (response.code !== 200) {
        throw new Error(response.message || '获取工具失败')
      }
      return response.data
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`获取工具失败: ${errorMsg}`)
      message.error('获取工具失败')
      throw error
    } finally {
      loading.value = false
    }
  }

  /**
   * 更新工具
   */
  const updateTools = async (data: ToolsConfigRead): Promise<void> => {
    loading.value = true
    try {
      const response = await toolsApi.update(data)
      if (response.code !== 200) {
        throw new Error(response.message || '更新工具失败')
      }
      logger.info('工具更新成功')
      message.success('保存成功')
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`更新工具失败: ${errorMsg}`)
      message.error('保存失败')
      throw error
    } finally {
      loading.value = false
    }
  }

  return {
    loading,
    getTools,
    updateTools,
  }
}
