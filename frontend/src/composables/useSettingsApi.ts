import { computed, ref } from 'vue'
import { ApiError, Service, type Setting_Output } from '@/api'
import { translate as t } from '@/i18n'
import { apiErrorMessage, requestApi, responseError } from '@/utils/apiResult'
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
  const saveFailure = ref<'rejected' | 'unknown' | null>(null)
  const query = useApiQuery(
    async () => {
      const response = await requestApi(
        () => Service.getSettingApiSettingGetPost(),
        t('setting.toast.loadFailed')
      )
      return fromBackendSettings((response.data ?? {}) as Setting_Output)
    },
    () => t('setting.toast.loadFailed')
  )
  const loading = computed(() => query.loading.value || savingCount.value > 0)

  // 获取设置
  const getSettings = (): Promise<SettingsViewModel | null> => query.execute()

  // 更新设置 - 只发送修改的字段
  const updateSettings = async (settings: SettingsPatch): Promise<boolean> => {
    savingCount.value += 1
    error.value = null
    saveFailure.value = null
    let requestStarted = false

    try {
      const category = Object.keys(settings)[0] as SettingsCategory | undefined
      if (!category) return true
      const data = toBackendPatch(
        category,
        (settings as Record<string, unknown>)[category] as Record<string, unknown>
      )
      requestStarted = true
      const response = await Service.updateSettingApiSettingUpdatePost({ data })
      const failure = responseError(response, t('setting.toast.saveFailed'))
      if (failure) {
        saveFailure.value = typeof response.code === 'number' ? 'rejected' : 'unknown'
        error.value = failure.message
        return false
      }

      return true
    } catch (err) {
      const body: { detail?: unknown } | undefined =
        err instanceof ApiError && err.body && typeof err.body === 'object' ? err.body : undefined
      // FastAPI 的完整 422 校验响应表示请求被拒绝，尚未进入路由的写入处理。
      const validationRejected =
        err instanceof ApiError &&
        err.status === 422 &&
        Array.isArray(body?.detail) &&
        body.detail.length > 0 &&
        body.detail.every((item: unknown) => {
          if (!item || typeof item !== 'object') return false
          const detail = item as { loc?: unknown; msg?: unknown; type?: unknown }
          return (
            Array.isArray(detail.loc) &&
            detail.loc.length > 0 &&
            detail.loc.every(part => typeof part === 'string' || typeof part === 'number') &&
            typeof detail.msg === 'string' &&
            typeof detail.type === 'string'
          )
        })
      // 连接失败只说明响应未确认，服务端仍可能继续落盘；不自动重发或通过 GET 推断终态。
      saveFailure.value = !requestStarted || validationRejected ? 'rejected' : 'unknown'
      error.value = apiErrorMessage(err, t('setting.toast.saveFailed'))
      return false
    } finally {
      savingCount.value -= 1
    }
  }

  return {
    loading,
    error,
    saveFailure,
    loadError: query.error,
    getSettings,
    updateSettings,
  }
}
