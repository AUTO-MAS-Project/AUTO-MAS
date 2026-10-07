import { ref } from 'vue'
import { useSaveQueue } from '@/composables/useSaveQueue'

/**
 * MFW 用户页的保存状态：状态机与串行保存在公共 `useSaveQueue` 里，
 * 这里只补「有未保存改动」这一页面语义与保存计数。
 *
 * `state` / `fieldStates` 直接给页面的保存状态指示用（未保存 / 保存中 / 已保存 /
 * 失败已保留草稿 / 失败已回滚 / 被拒绝 / 结果未知）；`pendingCount()` 给出当前还排着
 * （含正在执行）的保存数，调用方据此判断自己是不是最后一个。
 */
export function useMaaFWUserSaveStatus() {
  const { enqueue, isSaving, state, fieldStates, canLeave, waitForIdle, pendingCount } =
    useSaveQueue()
  const hasUnsavedChanges = ref(false)

  const enqueueSave = async (action: () => Promise<void>, key?: string): Promise<void> => {
    hasUnsavedChanges.value = true
    try {
      await enqueue(action, key)
    } finally {
      if (state.value === 'saved') hasUnsavedChanges.value = false
    }
  }

  return {
    isSaving,
    hasUnsavedChanges,
    state,
    fieldStates,
    canLeave,
    waitForIdle,
    enqueueSave,
    pendingCount,
  }
}

export type MaaFWUserSaveStatus = ReturnType<typeof useMaaFWUserSaveStatus>
