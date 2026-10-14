import { defineStore } from 'pinia'
import { computed, onScopeDispose, ref, watch } from 'vue'
import { useEventListener } from '@vueuse/core'
import type { MysteryContextData } from '@/api'
import { getMysteryContext, MysteryContextError } from '@/composables/useMysteryApi'
import { useWebSocket } from '@/composables/useWebSocket'
import { getConfig, saveConfig } from '@/utils/config'
import { getMysteryDate } from '@/utils/mysteryAccess'

export const useMysteryStore = defineStore('mystery', () => {
  const unlockedDate = ref('')
  const unlockedFingerprint = ref('')
  const context = ref<MysteryContextData | null>(null)
  const today = ref(getMysteryDate())
  const fingerprint = computed(() =>
    context.value ? `${context.value.deviceHash}:${context.value.backendHash}` : ''
  )
  const unlocked = computed(
    () =>
      !!fingerprint.value &&
      unlockedDate.value === today.value &&
      unlockedFingerprint.value === fingerprint.value
  )
  const requestInfo = computed(() =>
    context.value ? JSON.stringify({ version: 1, ...context.value }) : ''
  )
  const initialized = ref(false)
  const saving = ref(false)
  const loadError = ref('')
  const { state } = useWebSocket()
  let contextGeneration = 0
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

    const generation = contextGeneration
    loadError.value = ''
    const pending = (async () => {
      try {
        const [config, currentContext] = await Promise.all([
          getConfig({ strict: true }),
          getMysteryContext(),
        ])
        if (generation !== contextGeneration) return
        context.value = currentContext
        unlockedDate.value = config.mysteryUnlockedDate ?? ''
        unlockedFingerprint.value = config.mysteryUnlockedFingerprint ?? ''
        initialized.value = true
      } catch (error) {
        if (generation === contextGeneration) {
          loadError.value =
            error instanceof MysteryContextError ? error.message : 'CONTEXT_UNAVAILABLE'
        }
        throw error
      } finally {
        if (generation === contextGeneration) loadPromise = null
      }
    })()
    loadPromise = pending
    return pending
  }

  // 后端重连后重取它自己的源码指纹，避免更新后沿用上一进程的解锁状态。
  watch(state, status => {
    contextGeneration++
    context.value = null
    initialized.value = false
    loadError.value = ''
    loadPromise = null
    if (status !== 'open') return
    void load().catch(() => {
      // loadError 已保留可重试的失败状态，由入口页面显示。
    })
  })

  const unlock = async (accessCode: string): Promise<boolean> => {
    await load()
    if (saving.value) return false

    saving.value = true
    try {
      const checkedAt = new Date()
      const checkedDate = getMysteryDate(checkedAt)
      const checkedContext = context.value
      const checkedFingerprint = fingerprint.value
      if (!checkedContext) return false
      if (
        !(await window.electronAPI.verifyMysteryAccessCode(accessCode, {
          deviceHash: checkedContext.deviceHash,
          backendHash: checkedContext.backendHash,
        }))
      )
        return false
      if (checkedDate !== getMysteryDate() || checkedContext !== context.value) return false

      await saveConfig({
        mysteryUnlockedDate: checkedDate,
        mysteryUnlockedFingerprint: checkedFingerprint,
      })
      unlockedDate.value = checkedDate
      unlockedFingerprint.value = checkedFingerprint
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
      await saveConfig({ mysteryUnlockedDate: '', mysteryUnlockedFingerprint: '' })
      unlockedDate.value = ''
      unlockedFingerprint.value = ''
    } finally {
      saving.value = false
    }
  }

  return { unlocked, initialized, saving, loadError, requestInfo, load, unlock, lock }
})
