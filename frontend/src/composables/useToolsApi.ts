import { translate as t } from '@/i18n'
import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { Service, type ToolsConfig, type ToolsConfigInput } from '@/api'

// 接口的只读字段仍需随轮询更新本地显示状态。
export type ToolsViewConfig = {
  [K in keyof ToolsConfig]:
    | {
        -readonly [F in keyof NonNullable<ToolsConfig[K]>]: NonNullable<ToolsConfig[K]>[F]
      }
    | null
}

export function useToolsApi() {
  const loading = ref(false)
  const logger = window.electronAPI.getLogger('工具API')

  /**
   * 获取工具
   */
  const getTools = async (): Promise<ToolsViewConfig> => {
    loading.value = true
    try {
      const response = await Service.getToolsApiToolsGetPost()
      if (response.code !== 200) {
        throw new Error(response.message || '获取工具失败')
      }
      return response.data
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`获取工具失败: ${errorMsg}`)
      message.error(t('core.misc.couldNotLoadTools'))
      throw error
    } finally {
      loading.value = false
    }
  }

  /**
   * 更新工具
   */
  const updateTools = async (data: ToolsConfigInput): Promise<void> => {
    loading.value = true
    try {
      const response = await Service.updateToolsApiToolsUpdatePost({ data })
      if (response.code !== 200) {
        throw new Error(response.message || '更新工具失败')
      }
      logger.info('工具更新成功')
      message.success(t('core.misc.saved'))
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`更新工具失败: ${errorMsg}`)
      message.error(t('core.misc.couldNotSave'))
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
