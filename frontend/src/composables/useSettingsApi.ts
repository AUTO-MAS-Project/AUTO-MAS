import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { GetService, UpdateService, type GlobalConfig } from '@/api'

export function useSettingsApi() {
  const loading = ref(false)
  const error = ref<string | null>(null)

  // 获取设置
  const getSettings = async (): Promise<GlobalConfig | null> => {
    loading.value = true
    error.value = null

    try {
      const response = await GetService.getScriptsApiSettingGetPost()

      // 根据code判断是否成功（非200就是不成功）
      if (response.code !== 200) {
        const errorMsg = response.message || '获取设置失败'
        message.error(errorMsg)
        throw new Error(errorMsg)
      }

      return response.data
    } catch (err: any) {
      const errorMsg = err instanceof Error ? err.message : '获取设置失败'
      error.value = errorMsg
      if (!err.message?.includes('HTTP error')) {
        message.error(errorMsg)
      }
      return null
    } finally {
      loading.value = false
    }
  }

  // 更新设置 - 只发送修改的字段
  const updateSettings = async (settings: GlobalConfig): Promise<boolean> => {
    loading.value = true
    error.value = null

    try {
      const response = await UpdateService.updateScriptApiSettingUpdatePost({
        data: settings,
      })

      // 根据code判断是否成功（非200就是不成功）
      if (response.code !== 200) {
        const errorMsg = response.message || '设置修改失败'
        message.error(errorMsg)
        throw new Error(errorMsg)
      }

      message.success(response.message || '设置修改成功')
      return true
    } catch (err: any) {
      const errorMsg = err instanceof Error ? err.message : '设置修改失败'
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
    getSettings,
    updateSettings,
  }
}
