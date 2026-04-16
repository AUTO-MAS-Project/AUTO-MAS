import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { infoApi, scriptApi } from '@/api'

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

  // 鑾峰彇Web閰嶇疆妯℃澘鍒楄〃
  const getWebConfigTemplates = async (): Promise<WebConfigTemplate[]> => {
    loading.value = true
    error.value = null

    try {
      const response = await infoApi.getWebConfig()

      if (response.code !== 200) {
        const errorMsg = response.message || '鑾峰彇妯℃澘鍒楄〃澶辫触'
        message.error(errorMsg)
        throw new Error(errorMsg)
      }

      // 鐩存帴杩斿洖API鍝嶅簲涓殑WebConfig鏁扮粍
      return (response.data as any).WebConfig || []
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : '鑾峰彇妯℃澘鍒楄〃澶辫触'
      error.value = errorMsg
      if (err instanceof Error && !err.message.includes('HTTP error')) {
        message.error(errorMsg)
      }
      return []
    } finally {
      loading.value = false
    }
  }

  // 浠嶹eb瀵煎叆鑴氭湰閰嶇疆
  const importScriptFromWeb = async (scriptId: string, url: string): Promise<boolean> => {
    loading.value = true
    error.value = null

    try {
      const response = await scriptApi.importTemplateFromWeb({
        scriptId,
        url,
      })

      if (response.code !== 200) {
        const errorMsg = response.message || '瀵煎叆閰嶇疆澶辫触'
        message.error(errorMsg)
        throw new Error(errorMsg)
      }

      return true
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : '瀵煎叆閰嶇疆澶辫触'
      error.value = errorMsg
      if (err instanceof Error && !err.message.includes('HTTP error')) {
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
    importScriptFromWeb,
  }
}

