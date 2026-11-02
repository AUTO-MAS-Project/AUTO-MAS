import { onScopeDispose, ref } from 'vue'
import { Service } from '@/api'
import { translate as t } from '@/i18n'
import { getApiErrorMessage } from '@/utils/apiError'

/** 读取托盘可启动的队列与脚本，不采集任务标签或标识。 */
export function useTrayMenuTasks() {
  const options = ref<{ label: string; value: string }[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  let request: ReturnType<typeof Service.getTaskComboxApiInfoComboxTaskPost> | null = null
  let requestId = 0

  const load = async () => {
    const currentId = ++requestId
    request?.cancel()
    loading.value = true
    error.value = null
    request = Service.getTaskComboxApiInfoComboxTaskPost()
    try {
      const response = await request
      if (currentId !== requestId) return
      if (response.code !== 200) throw new Error(response.message)
      options.value = response.data.flatMap(item =>
        item.value ? [{ label: item.label, value: item.value }] : []
      )
    } catch (cause) {
      if (currentId === requestId) {
        error.value = getApiErrorMessage(cause, t('core.setting.tray.tasksLoadFailed'))
      }
    } finally {
      if (currentId === requestId) {
        loading.value = false
        request = null
      }
    }
  }

  onScopeDispose(() => {
    ++requestId
    request?.cancel()
  })

  return { options, loading, error, load }
}
