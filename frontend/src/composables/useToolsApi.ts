import { translate as t } from '@/i18n'
import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { Service, type ToolsConfig } from '@/api'
import { useConfigEditSession } from '@/composables/useConfigEditSession'

export function useToolsApi() {
  const loading = ref(false)
  const logger = window.electronAPI.getLogger('工具API')
  const { ensureConfigEditSession, markConfigEditSaved } = useConfigEditSession()

  /**
   * 获取工具
   */
  const getTools = async (): Promise<ToolsConfig> => {
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
      message.error(t('misc.couldNotLoadTools'))
      throw error
    } finally {
      loading.value = false
    }
  }

  /**
   * 更新工具
   */
  const updateTools = async (data: ToolsConfig): Promise<void> => {
    loading.value = true
    try {
      const editSession = await ensureConfigEditSession('ToolsConfig')
      if (!editSession) throw new Error('有其他用户正在编辑该配置')
      const response = await Service.updateToolsApiToolsUpdatePost({ data, ...editSession })
      if (response.code !== 200) {
        throw new Error(response.message || '更新工具失败')
      }
      await markConfigEditSaved('ToolsConfig')
      logger.info('工具更新成功')
      message.success(t('misc.saved'))
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`更新工具失败: ${errorMsg}`)
      message.error(t('misc.couldNotSave'))
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
