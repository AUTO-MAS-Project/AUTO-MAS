import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { Service } from '@/api'
import type { SettingsData } from '@/types/script'

export function useSettingsApi() {
  const loading = ref(false)
  const error = ref<string | null>(null)

  // 获取设置
  const getSettings = async (): Promise<SettingsData | null> => {
    loading.value = true
    error.value = null

    try {
      const response = await Service.getScriptsApiSettingGetPost()

      // 根据code判断是否成功（非200就是不成功）
      if (response.code !== 200) {
        const errorMsg = response.message || '获取设置失败'
        message.error(errorMsg)
        throw new Error(errorMsg)
      }

      return response.data as SettingsData
    } catch (err) {
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

  // 更新设置
  const updateSettings = async (settings: Partial<SettingsData>): Promise<boolean> => {
    loading.value = true
    error.value = null

    try {
      const response = await Service.updateScriptApiSettingUpdatePost({
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
    } catch (err) {
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
