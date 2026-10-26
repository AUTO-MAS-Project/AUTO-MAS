import { onScopeDispose, ref } from 'vue'
import { Service, type BackendHealthOut } from '@/api'
import { translate as t } from '@/i18n'

/** 开发工作台的主动健康探测，不轮询业务接口。 */
export function useDevtoolsApi() {
  const loading = ref(false)
  const error = ref('')
  const health = ref<BackendHealthOut | null>(null)
  const latency = ref<number | null>(null)
  let pending: ReturnType<typeof Service.getHealthApiCoreHealthGet> | undefined
  let disposed = false

  onScopeDispose(() => {
    disposed = true
    pending?.cancel()
  })

  const probe = async () => {
    if (loading.value) return
    loading.value = true
    error.value = ''
    const startedAt = performance.now()
    try {
      pending = Service.getHealthApiCoreHealthGet()
      const result = await pending
      if (disposed) return
      health.value = result
      latency.value = Math.round(performance.now() - startedAt)
    } catch {
      if (disposed) return
      health.value = null
      latency.value = null
      error.value = t('devtools.probeFailed')
    } finally {
      if (!disposed) loading.value = false
      pending = undefined
    }
  }

  return { loading, error, health, latency, probe }
}
