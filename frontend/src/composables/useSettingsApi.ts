import { ref } from 'vue'
import { message } from 'ant-design-vue'
import type { SettingsData, GetSettingsResponse, UpdateSettingsResponse } from '../types/settings.ts'

const API_BASE_URL = 'http://localhost:8000/api'

export function useSettingsApi() {
  const loading = ref(false)
  const error = ref<string | null>(null)

  // 获取设置
  const getSettings = async (): Promise<SettingsData | null> => {
    loading.value = true
    error.value = null

    try {
      const response = await fetch(`${API_BASE_URL}/setting/get`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({}), // 空请求体
      })

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }

      const apiResponse: GetSettingsResponse = await response.json()

      // 根据code判断是否成功（非200就是不成功）
      if (apiResponse.code !== 200) {
        const errorMsg = apiResponse.message || '获取设置失败'
        message.error(errorMsg)
        throw new Error(errorMsg)
      }

      return apiResponse.data
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
      const response = await fetch(`${API_BASE_URL}/setting/update`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          data: settings,
        }),
      })

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }

      const apiResponse: UpdateSettingsResponse = await response.json()

      // 根据code判断是否成功（非200就是不成功）
      if (apiResponse.code !== 200) {
        const errorMsg = apiResponse.message || '设置修改失败'
        message.error(errorMsg)
        throw new Error(errorMsg)
      }

      // message.success(apiResponse.message || '设置修改成功')
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
