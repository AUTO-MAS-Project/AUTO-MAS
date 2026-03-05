import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { Service, type ToolsConfig } from '@/api'

export function useToolsApi() {
    const loading = ref(false)
    const logger = window.electronAPI.getLogger('工具API')

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
            message.error('获取工具失败')
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
            const response = await Service.updateToolsApiToolsUpdatePost({ data })
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
