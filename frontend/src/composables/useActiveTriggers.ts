import { computed } from 'vue'
import { Service } from '@/api'
import { useConfigQuery } from '@/services/configUiSync'

export const ACTIVE_TRIGGERS_QUERY_KEY = ['config-triggers', 'active'] as const

export function useActiveTriggers(observe = true) {
  const query = useConfigQuery({
    queryKey: ACTIVE_TRIGGERS_QUERY_KEY,
    enabled: observe,
    queryFn: async () => {
      const response = await Service.getActiveConfigTriggersApiConfigTriggersActiveGet()
      if (response.code !== 200) throw new Error(response.message)
      return response
    },
  })
  return { ...query, data: computed(() => query.data.value?.data ?? []) }
}
