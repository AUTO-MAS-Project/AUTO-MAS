import { onScopeDispose, ref } from 'vue'
import { Service, type BackendHealthOut } from '@/api'
import { translate as t } from '@/i18n'

const HEALTH_PROBE_TIMEOUT_MS = 10_000

/** 开发工作台的主动健康探测，不轮询业务接口。 */
export function useDevtoolsApi() {
  const loading = ref(false)
  const error = ref('')
  const health = ref<BackendHealthOut | null>(null)
  const latency = ref<number | null>(null)
  let pending: ReturnType<typeof Service.getHealthApiCoreHealthGet> | undefined
  let timeout: ReturnType<typeof setTimeout> | undefined
  let disposed = false

  onScopeDispose(() => {
    disposed = true
    clearTimeout(timeout)
    pending?.cancel()
  })

  const probe = async () => {
    if (disposed || loading.value) return
    loading.value = true
    error.value = ''
    const startedAt = performance.now()
    let timedOut = false
    try {
      const request = Service.getHealthApiCoreHealthGet()
      pending = request
      timeout = setTimeout(() => {
        timedOut = true
        request.cancel()
      }, HEALTH_PROBE_TIMEOUT_MS)
      const result = await request
      if (disposed) return
      health.value = result
      latency.value = Math.round(performance.now() - startedAt)
    } catch {
      if (disposed) return
      health.value = null
      latency.value = null
      error.value = t(timedOut ? 'devtools.probeTimedOut' : 'devtools.probeFailed')
    } finally {
      clearTimeout(timeout)
      timeout = undefined
      if (!disposed) loading.value = false
      pending = undefined
    }
  }

  return { loading, error, health, latency, probe }
}
