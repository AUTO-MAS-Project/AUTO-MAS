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

  const load = async (refresh = false): Promise<void> => {
    refreshDate()
    if (!refresh) {
      if (loadPromise) return loadPromise
      if (initialized.value) return
    }

    const generation = ++contextGeneration
    loadError.value = ''
    const pending = (async () => {
      try {
        const currentContext = await getMysteryContext()
        // 在指纹请求返回后读配置，避免等待期间手动锁定却又恢复旧的解锁记录。
        const config = await getConfig({ strict: true })
        if (generation !== contextGeneration) return
        context.value = currentContext
        unlockedDate.value = config.mysteryUnlockedDate ?? ''
        unlockedFingerprint.value = config.mysteryUnlockedFingerprint ?? ''
        initialized.value = true
      } catch (error) {
        if (generation !== contextGeneration) return
        context.value = null
        initialized.value = false
        loadError.value =
          error instanceof MysteryContextError ? error.message : 'CONTEXT_UNAVAILABLE'
        throw error
      } finally {
        if (generation === contextGeneration) loadPromise = null
      }
    })()
    loadPromise = pending
    return pending
  }

  // WS 短断时 HTTP 扫码可以继续。重连后用新指纹更新状态，避免卸载同一后端的扫码页面。
  watch(state, status => {
    if (status !== 'open') return
    void load(true).catch(() => {
      // loadError 已保留可重试的失败状态，由入口页面显示。
    })
  })

  const unlock = async (accessCode: string): Promise<boolean> => {
    await load(state.value !== 'open')
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
      await load()
      if (checkedDate !== getMysteryDate() || checkedFingerprint !== fingerprint.value) return false

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

  return { unlocked, initialized, saving, loadError, load, unlock, lock }
})
