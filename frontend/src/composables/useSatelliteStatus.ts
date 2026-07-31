import { computed } from 'vue'
import { useTaskRuntimeState } from '@/composables/useTaskRuntimeState'

export interface SatelliteModuleStatus {
  queued: boolean
  running: boolean
  lastFailed: boolean
}

export function useSatelliteStatus() {
  const { scriptStatusesByType } = useTaskRuntimeState()

  return {
    statuses: computed(() => new Map<string, SatelliteModuleStatus>(scriptStatusesByType.value)),
  }
}
