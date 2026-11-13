import { ref, type Ref } from 'vue'
import type { OkwwTaskForm } from './okwwTaskConfig'

export function useOkwwCustomArguments(
  task: Ref<OkwwTaskForm>,
  currentArguments: Ref<string>,
  save: () => Promise<boolean>,
  confirm: (onOk: () => Promise<void>) => void
) {
  const saving = ref(false)
  const persist = async (enabled: boolean, argumentsText: string) => {
    const previous = {
      IfCustomArguments: task.value.IfCustomArguments,
      CustomArguments: task.value.CustomArguments,
    }
    task.value.IfCustomArguments = enabled
    task.value.CustomArguments = argumentsText
    saving.value = true
    let saved = false
    try {
      saved = await save()
      return saved
    } finally {
      if (!saved) Object.assign(task.value, previous)
      saving.value = false
    }
  }
  const changeCustomArguments = (enabled: boolean) => {
    if (!enabled) return persist(false, task.value.CustomArguments)
    const argumentsText = currentArguments.value
    confirm(async () => {
      await persist(true, argumentsText)
    })
  }
  return { saving, changeCustomArguments }
}
