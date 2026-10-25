import { getApiErrorMessage } from '@/utils/apiError'
import { translate as t } from '@/i18n'
import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { GetService, UpdateService, type GlobalConfig, type SettingMirrorCdkData } from '@/api'

export function useSettingsApi() {
  const loading = ref(false)
  const error = ref<string | null>(null)

  const queryMirrorCdk = async (cdk: string): Promise<SettingMirrorCdkData> => {
    try {
      const response = await GetService.querySettingMirrorCdkApiSettingMirrorCdkPost({ cdk })
      if (response.code === 200) return response.data
    } catch {
      // 状态查询失败只显示可重试的提示，不把请求中的 CDK 带入日志或消息。
    }
    return { status: 'error', expiredTime: null }
  }

  // 获取设置
  const getSettings = async (): Promise<GlobalConfig | null> => {
    loading.value = true
    error.value = null

    try {
      const response = await GetService.getScriptsApiSettingGetPost()

      // 根据code判断是否成功（非200就是不成功）
      if (response.code !== 200) {
        const errorMsg = response.message || t('apiErrors.settingsLoadFailed')
        throw new Error(errorMsg)
      }

      return response.data
    } catch (err) {
      const errorMsg = getApiErrorMessage(err, t('apiErrors.settingsLoadFailed'))
      error.value = errorMsg
      message.error(errorMsg)
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
        const errorMsg = response.message || t('apiErrors.settingsSaveFailed')
        throw new Error(errorMsg)
      }

      return true
    } catch (err) {
      const errorMsg = getApiErrorMessage(err, t('apiErrors.settingsSaveFailed'))
      error.value = errorMsg
      message.error(errorMsg)
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
    queryMirrorCdk,
  }
}
