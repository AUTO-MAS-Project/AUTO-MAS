import { beginSettingsChanges } from '@/utils/settingsAnalytics'
import { getApiErrorMessage } from '@/utils/apiError'
import { translate as t } from '@/i18n'
import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { GetService, UpdateService, type GlobalConfig, type SettingMirrorCdkData } from '@/api'
import { analyticsConfigSection, beginAnalyticsOperation } from '@/utils/analytics'
import { beginNotificationChannelChanges } from '@/utils/notificationAnalytics'

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
        const errorMsg = response.message || t('bootstrap.apiErrors.settingsLoadFailed')
        throw new Error(errorMsg)
      }

      return response.data
    } catch (err) {
      const errorMsg = getApiErrorMessage(err, t('bootstrap.apiErrors.settingsLoadFailed'))
      error.value = errorMsg
      message.error(errorMsg)
      return null
    } finally {
      loading.value = false
    }
  }

  // 更新设置 - 只发送修改的字段
  const updateSettings = async (settings: GlobalConfig): Promise<boolean> => {
    const channelChanges = beginNotificationChannelChanges(settings.Notify)
    const settingChanges = beginSettingsChanges(settings)
    // 开关自身不产生保存事件，也不在重新开启后补报。
    const operation =
      settings.Function &&
      Object.prototype.hasOwnProperty.call(settings.Function, 'IfEnableTelemetry')
        ? null
        : beginAnalyticsOperation('config_write_finished')
    const dimensions = {
      owner_kind: 'settings' as const,
      section_kind: analyticsConfigSection(settings),
      script_type: 'none' as const,
    }
    loading.value = true
    error.value = null

    try {
      const response = await UpdateService.updateScriptApiSettingUpdatePost({
        data: settings,
      })

      // 根据code判断是否成功（非200就是不成功）
      if (response.code !== 200) {
        const errorMsg = response.message || t('core.apiErrors.settingsSaveFailed')
        throw new Error(errorMsg)
      }

      operation?.finish({ ...dimensions, outcome: 'success' })
      channelChanges.forEach(finish => finish('success'))
      settingChanges.forEach(finish => finish('success'))
      return true
    } catch (err) {
      operation?.finish({ ...dimensions, outcome: 'failure' })
      channelChanges.forEach(finish => finish('failure'))
      settingChanges.forEach(finish => finish('failure'))
      const errorMsg = getApiErrorMessage(err, t('core.apiErrors.settingsSaveFailed'))
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
