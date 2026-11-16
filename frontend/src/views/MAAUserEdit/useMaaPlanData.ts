import { ref, watch } from 'vue'
import type { PlanGetOut } from '@/api'

export function useMaaPlanData(
  getMode: () => string,
  getPlans: (id: string) => Promise<PlanGetOut>,
  onError: (error: unknown) => void
) {
  const data = ref<PlanGetOut['data'][string] | null>(null)
  const status = ref<'idle' | 'loading' | 'ready' | 'error'>('idle')

  watch(
    getMode,
    async (mode, _previous, onCleanup) => {
      let active = true
      onCleanup(() => {
        active = false
      })
      data.value = null
      if (!mode || mode === 'Fixed') {
        status.value = 'idle'
        return
      }

      status.value = 'loading'
      try {
        const response = await getPlans(mode)
        if (!active) return
        const plan = response.code === 200 ? response.data[mode] : null
        if (!plan) throw new Error('Plan data is missing')
        data.value = plan
        status.value = 'ready'
      } catch (error) {
        if (!active) return
        status.value = 'error'
        onError(error)
      }
    },
    { immediate: true, flush: 'sync' }
  )

  return { data, status }
}
