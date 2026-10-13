import { onScopeDispose, ref } from 'vue'

/**
 * MFW 用户页的保存状态与串行保存。
 *
 * 和 `useSaveQueue` 语义不同，不要合并：这里每次保存都单独执行（不按 key 合并），
 * 并驱动页头的保存状态（保存中 / 已保存两秒后回到空闲 / 出错带原因）与「有未保存改动」；
 * `pendingCount()` 给出当前还排着（含正在执行）的保存数，调用方据此判断自己是不是最后一个。
 *
 * 失败按保存项的 `key` 记账（单字段保存是字段键，任务队列是 `Task`）：某一项存失败后，只有
 * 同一项后来存成功才算补上；别的项存成功不清它。还有失败项时一直是「出错 + 有未保存改动」，
 * 「返回」与关窗口据此拦下。不传 key 的保存都算同一项。
 */
export function useMaaFWUserSaveStatus() {
  const isSaving = ref(false)
  const hasUnsavedChanges = ref(false)
  const saveStatus = ref<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const saveErrorMessage = ref('')
  let saveStatusTimer: ReturnType<typeof setTimeout> | null = null
  let pendingSaves = 0
  let saveQueue: Promise<void> = Promise.resolve()
  /** 还没补上的失败项：key → 失败原因（按失败先后排，最后一项是最近一次） */
  const failedSaves = new Map<string, string>()

  const latestFailure = () => [...failedSaves.values()].pop() ?? ''

  const enqueueSave = async (action: () => Promise<void>, key = '') => {
    pendingSaves += 1
    isSaving.value = true
    hasUnsavedChanges.value = true
    saveStatus.value = 'saving'
    const next = saveQueue.catch(() => undefined).then(action)
    saveQueue = next.catch(() => undefined)
    try {
      await next
      failedSaves.delete(key)
      if (failedSaves.size > 0) {
        // 这一项存上了，但别的项的失败还在：保持出错提示
        saveStatus.value = 'error'
        saveErrorMessage.value = latestFailure()
      } else {
        saveStatus.value = 'saved'
        saveErrorMessage.value = ''
        if (saveStatusTimer) clearTimeout(saveStatusTimer)
        saveStatusTimer = setTimeout(() => {
          saveStatus.value = 'idle'
          saveStatusTimer = null
        }, 2000)
      }
    } catch (error) {
      const reason = error instanceof Error ? error.message : String(error)
      failedSaves.delete(key)
      failedSaves.set(key, reason)
      saveStatus.value = 'error'
      saveErrorMessage.value = reason
      throw error
    } finally {
      pendingSaves -= 1
      isSaving.value = pendingSaves > 0
      if (pendingSaves === 0 && failedSaves.size === 0) {
        hasUnsavedChanges.value = false
      }
    }
  }

  /** 重新从后端读了整份用户数据（加载、配置恢复）：之前没存上的改动已不在页面上，失败账清空 */
  const resetSaveFailures = () => {
    failedSaves.clear()
    if (saveStatus.value === 'error') {
      saveStatus.value = 'idle'
      saveErrorMessage.value = ''
    }
    hasUnsavedChanges.value = pendingSaves > 0
  }

  /** 等排着的保存全部跑完（成功或失败都算完）；等待期间又排进来的也一起等 */
  const waitForSaves = async () => {
    while (pendingSaves > 0) {
      await saveQueue
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
    waitForSaves,
    resetSaveFailures,
    pendingCount: () => pendingSaves,
  }
}

export type MaaFWUserSaveStatus = ReturnType<typeof useMaaFWUserSaveStatus>
