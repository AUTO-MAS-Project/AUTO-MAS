import { defineStore } from 'pinia'
import { computed, onScopeDispose, ref } from 'vue'
import { useEventListener } from '@vueuse/core'
import { Service, type MysteryStatusOut } from '@/api'
import { getMysteryDate } from '@/utils/mysteryAccess'

/**
 * 取解锁日期；业务失败时后端把状态码放在 body 里（HTTP 状态始终是 200），
 * 所以 HTTP 成功不代表业务成功，仍需判 `code`。
 */
const unlockDateOf = (payload: MysteryStatusOut): string => {
  if (payload.code !== 200) throw new Error(payload.message || `HTTP ${payload.code}`)
  return payload.unlockedDate ?? ''
}

export const useMysteryStore = defineStore('mystery', () => {
  const unlockedDate = ref('')
  const today = ref(getMysteryDate())
  const unlocked = computed(() => unlockedDate.value === today.value)
  const initialized = ref(false)
  const saving = ref(false)
  let loadPromise: Promise<void> | null = null
  let expiryTimer: ReturnType<typeof setTimeout> | undefined

  const refreshDate = () => {
    const now = new Date()
    today.value = getMysteryDate(now)
    clearTimeout(expiryTimer)
    const nextMidnight = new Date(`${today.value}T00:00:00+08:00`).getTime() + 24 * 60 * 60 * 1000
    expiryTimer = setTimeout(refreshDate, nextMidnight - now.getTime())
  }

  // 零点主动锁回；窗口从后台或休眠恢复时再同步一次日期。
  refreshDate()
  if (typeof document !== 'undefined') {
    useEventListener(document, 'visibilitychange', refreshDate)
  }
  onScopeDispose(() => clearTimeout(expiryTimer))

  const load = async (): Promise<void> => {
    refreshDate()
    if (initialized.value) return
    if (loadPromise) return loadPromise

    loadPromise = (async () => {
      try {
        unlockedDate.value = unlockDateOf(await Service.getMysteryStatusApiMysteryStatusGet())
        initialized.value = true
      } finally {
        loadPromise = null
      }
    })()

    return loadPromise
  }

  /**
   * 提交口令。
   *
   * 口令不正确（后端 400）返回 false 由页面提示，其余失败继续抛出，
   * 让页面能区分「密钥不对」与「服务异常」两种提示。
   */
  const unlock = async (accessCode: string): Promise<boolean> => {
    await load()
    if (saving.value) return false

    saving.value = true
    try {
      const payload = await Service.unlockMysteryApiMysteryUnlockPost({ accessCode })
      if (payload.code === 400) return false

      unlockedDate.value = unlockDateOf(payload)
      refreshDate()
      return unlocked.value
    } finally {
      saving.value = false
    }
  }

  const lock = async (): Promise<void> => {
    await load()
    if (saving.value) return

    saving.value = true
    try {
      unlockDateOf(await Service.lockMysteryApiMysteryLockPost())
      unlockedDate.value = ''
    } finally {
      saving.value = false
    }
  }

  return { unlocked, initialized, saving, load, unlock, lock }
})
