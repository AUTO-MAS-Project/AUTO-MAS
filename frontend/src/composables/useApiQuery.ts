import { ref, shallowRef } from 'vue'
import { apiErrorMessage } from '@/utils/apiResult'

/** 共享读取状态；重试由用户触发，不自动重发配置更新或触发器。 */
export function useApiQuery<T>(request: () => Promise<T>, fallback: () => string) {
  const loading = ref(false)
  const error = ref<string | null>(null)
  const data = shallowRef<T | null>(null)
  let pending: Promise<T | null> | null = null

  const execute = (): Promise<T | null> => {
    if (pending) return pending
    loading.value = true
    error.value = null
    pending = Promise.resolve()
      .then(request)
      .then(result => {
        data.value = result
        return result
      })
      .catch(reason => {
        error.value = apiErrorMessage(reason, fallback())
        return null
      })
      .finally(() => {
        loading.value = false
        pending = null
      })
    return pending
  }

  return { loading, error, data, execute }
}
