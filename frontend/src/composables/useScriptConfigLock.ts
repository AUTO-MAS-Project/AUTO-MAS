import { computed, toValue, type MaybeRefOrGetter } from 'vue'
import { useTaskRuntimeState } from '@/composables/useTaskRuntimeState'
import { isScriptConfigLocked } from '@/utils/scriptConfigLock'

export function useScriptConfigLock(scriptId: MaybeRefOrGetter<string>) {
  const { tasks } = useTaskRuntimeState()
  const configLocked = computed(() =>
    isScriptConfigLocked([...tasks.value.values()], toValue(scriptId))
  )

  return { configLocked }
}
