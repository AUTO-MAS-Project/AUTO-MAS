import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { Service } from '@/api'

export interface WebConfigTemplate {
  configName: string
  description: string
  author: string
  createTime: string
  downloadUrl: string
}

export interface WebConfigResponse {
  code: number
  status: string
  message: string
  data: {
    WebConfig: WebConfigTemplate[]
  }
}

export function useTemplateApi() {
  const loading = ref(false)
  const error = ref<string | null>(null)

  // 获取Web配置模板列表
  const getWebConfigTemplates = async (): Promise<WebConfigTemplate[]> => {
    loading.value = true
    error.value = null

    try {
      const response = await Service.getWebConfigApiInfoWebconfigPost()

      if (response.code !== 200) {
        const errorMsg = response.message || '获取模板列表失败'
        message.error(errorMsg)
        throw new Error(errorMsg)
      }

      // 直接返回API响应中的WebConfig数组
      return (response.data as any).WebConfig || []
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : '获取模板列表失败'
      error.value = errorMsg
      if (!err.message?.includes('HTTP error')) {
        message.error(errorMsg)
      }
      return []
    } finally {
      loading.value = false
    }
  }

  // 从Web导入脚本配置
  const importScriptFromWeb = async (scriptId: string, url: string): Promise<boolean> => {
    loading.value = true
    error.value = null

    try {
      const response = await Service.importScriptFromWebApiScriptsImportWebPost({
        scriptId,
        url
      })

      if (response.code !== 200) {
        const errorMsg = response.message || '导入配置失败'
        message.error(errorMsg)
        throw new Error(errorMsg)
      }

      message.success(response.message || '导入配置成功')
      return true
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : '导入配置失败'
      error.value = errorMsg
      if (!err.message?.includes('HTTP error')) {
        message.error(errorMsg)
      }
      return false
    } finally {
      loading.value = false
    }
  }

  return {
    loading,
    error,
    getWebConfigTemplates,
    importScriptFromWeb
  }
}
