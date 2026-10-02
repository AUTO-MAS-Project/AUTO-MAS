import { onScopeDispose, ref } from 'vue'

/**
 * MFW 用户页的保存状态与串行保存。
 *
 * 和 `useSaveQueue` 语义不同，不要合并：这里每次保存都单独执行（不按 key 合并），
 * 并驱动页头的保存状态（保存中 / 已保存两秒后回到空闲 / 出错带原因）与「有未保存改动」；
 * `pendingCount()` 给出当前还排着（含正在执行）的保存数，调用方据此判断自己是不是最后一个。
 */
export function useMaaFWUserSaveStatus() {
  const isSaving = ref(false)
  const hasUnsavedChanges = ref(false)
  const saveStatus = ref<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const saveErrorMessage = ref('')
  let saveStatusTimer: ReturnType<typeof setTimeout> | null = null
  let pendingSaves = 0
  let saveQueue: Promise<void> = Promise.resolve()

  const enqueueSave = async (action: () => Promise<void>) => {
    pendingSaves += 1
    isSaving.value = true
    hasUnsavedChanges.value = true
    saveStatus.value = 'saving'
    const next = saveQueue.catch(() => undefined).then(action)
    saveQueue = next.catch(() => undefined)
    try {
      await next
      saveStatus.value = 'saved'
      saveErrorMessage.value = ''
      if (saveStatusTimer) clearTimeout(saveStatusTimer)
      saveStatusTimer = setTimeout(() => {
        saveStatus.value = 'idle'
        saveStatusTimer = null
      }, 2000)
    } catch (error) {
      saveStatus.value = 'error'
      saveErrorMessage.value = error instanceof Error ? error.message : String(error)
      throw error
    } finally {
      pendingSaves -= 1
      isSaving.value = pendingSaves > 0
      if (pendingSaves === 0 && saveStatus.value === 'saved') {
        hasUnsavedChanges.value = false
      }
    }
  }

  onScopeDispose(() => {
    if (saveStatusTimer) clearTimeout(saveStatusTimer)
  })

  return {
    isSaving,
    hasUnsavedChanges,
    saveStatus,
    saveErrorMessage,
    enqueueSave,
    pendingCount: () => pendingSaves,
  }
}

export type MaaFWUserSaveStatus = ReturnType<typeof useMaaFWUserSaveStatus>
