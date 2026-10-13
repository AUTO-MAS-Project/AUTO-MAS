import { computed, ref } from 'vue'
import { Service, type Setting_Output } from '@/api'
import { translate as t } from '@/i18n'
import { apiErrorMessage, requestApi } from '@/utils/apiResult'
import { useApiQuery } from './useApiQuery'
import {
  fromBackendSettings,
  toBackendPatch,
  type SettingsCategory,
  type SettingsPatch,
  type SettingsViewModel,
} from '@/types/settings'

export function useSettingsApi() {
  const savingCount = ref(0)
  const error = ref<string | null>(null)
  const query = useApiQuery(async () => {
    const response = await requestApi(() => Service.getSettingApiSettingGetPost(), t('setting.toast.loadFailed'))
    return fromBackendSettings((response.data ?? {}) as Setting_Output)
  }, () => t('setting.toast.loadFailed'))
  const loading = computed(() => query.loading.value || savingCount.value > 0)

  // 获取设置
  const getSettings = (): Promise<SettingsViewModel | null> => query.execute()

  // 更新设置 - 只发送修改的字段
  const updateSettings = async (settings: SettingsPatch): Promise<boolean> => {
    savingCount.value += 1
    error.value = null

    try {
      const category = Object.keys(settings)[0] as SettingsCategory | undefined
      if (!category) return true
      await requestApi(() => Service.updateSettingApiSettingUpdatePost({
        data: toBackendPatch(category, (settings as Record<string, unknown>)[category] as Record<string, unknown>),
      }), t('setting.toast.saveFailed'))

      return true
    } catch (err) {
      error.value = apiErrorMessage(err, t('setting.toast.saveFailed'))
      return false
    } finally {
      savingCount.value -= 1
    }
  }

  return {
    loading,
    error,
    loadError: query.error,
    getSettings,
    updateSettings,
  }
}
