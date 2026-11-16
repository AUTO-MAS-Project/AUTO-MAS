import { onScopeDispose, ref } from 'vue'
import { fetchTaskTargets } from './useTaskOptions'
import { translate as t } from '@/i18n'
import { getApiErrorMessage } from '@/utils/apiError'

/** 读取托盘可启动的队列与脚本，不采集任务标签或标识。 */
export function useTrayMenuTasks() {
  const options = ref<{ label: string; value: string }[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  let requestId = 0

  const load = async () => {
    const currentId = ++requestId
    loading.value = true
    error.value = null
    try {
      const response = await fetchTaskTargets()
      if (currentId !== requestId) return
      options.value = response.flatMap(item =>
        item.value ? [{ label: item.label, value: item.value }] : []
      )
    } catch (cause) {
      if (currentId === requestId) {
        error.value = getApiErrorMessage(cause, t('core.setting.tray.tasksLoadFailed'))
      }
    } finally {
      if (currentId === requestId) {
        loading.value = false
      }
    }
  }

  onScopeDispose(() => {
    ++requestId
  })

  return { options, loading, error, load }
}
