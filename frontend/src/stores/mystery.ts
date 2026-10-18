import { defineStore } from 'pinia'
import { computed, onScopeDispose, ref } from 'vue'
import { useEventListener } from '@vueuse/core'
import { getConfig, saveConfig } from '@/utils/config'
import { getMysteryDate, isValidMysteryAccessCode } from '@/utils/mysteryAccess'

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
        const config = await getConfig()
        unlockedDate.value = config.mysteryUnlockedDate ?? ''
        initialized.value = true
      } finally {
        loadPromise = null
      }
    })()

    return loadPromise
  }

  const unlock = async (accessCode: string): Promise<boolean> => {
    await load()
    if (saving.value) return false

    saving.value = true
    try {
      const checkedAt = new Date()
      const checkedDate = getMysteryDate(checkedAt)
      if (!(await isValidMysteryAccessCode(accessCode, checkedAt))) return false
      if (checkedDate !== getMysteryDate()) return false

      await saveConfig({ mysteryUnlockedDate: checkedDate })
      unlockedDate.value = checkedDate
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
      await saveConfig({ mysteryUnlockedDate: '' })
      unlockedDate.value = ''
    } finally {
      saving.value = false
    }
  }

  return { unlocked, initialized, saving, load, unlock, lock }
})
