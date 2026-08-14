import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { getConfig, saveConfig } from '@/utils/config'

export type WindowActivity = 'visible' | 'background'

const DEFAULT_LOW_PERFORMANCE_MODE = false

export const usePerformanceStore = defineStore('performance', () => {
  const lowPerformanceMode = ref(DEFAULT_LOW_PERFORMANCE_MODE)
  const windowActivity = ref<WindowActivity>('visible')
  const initialized = ref(false)
  const saving = ref(false)

  let initializePromise: Promise<void> | null = null
  let removeWindowActivityListener: (() => void) | null = null
  let windowActivityUpdateVersion = 0

  const isBackgrounded = computed(() => windowActivity.value === 'background')
  const isLowPower = computed(() => lowPerformanceMode.value || isBackgrounded.value)

  const registerWindowActivityListener = () => {
    if (
      removeWindowActivityListener ||
      typeof window.electronAPI?.onWindowActivityChange !== 'function'
    ) {
      return
    }

    removeWindowActivityListener = window.electronAPI.onWindowActivityChange(activity => {
      windowActivityUpdateVersion += 1
      windowActivity.value = activity === 'background' ? 'background' : 'visible'
    })
  }

  const syncWindowActivity = async () => {
    if (typeof window.electronAPI?.getWindowActivity !== 'function') {
      return
    }

    const updateVersion = windowActivityUpdateVersion

    try {
      const activity = await window.electronAPI.getWindowActivity()
      if (
        updateVersion === windowActivityUpdateVersion &&
        (activity === 'visible' || activity === 'background')
      ) {
        windowActivity.value = activity
      }
    } catch {
      // 旧版 preload 未提供查询接口时，继续使用事件监听和默认状态。
    }
  }

  const initialize = async (): Promise<void> => {
    if (initialized.value) {
      return
    }

    if (initializePromise) {
      return initializePromise
    }

    const pendingInitialization = (async () => {
      registerWindowActivityListener()
      await syncWindowActivity()

      try {
        const config = await getConfig()
        lowPerformanceMode.value = config.lowPerformanceMode === true
      } catch {
        lowPerformanceMode.value = DEFAULT_LOW_PERFORMANCE_MODE
      } finally {
        initialized.value = true
        initializePromise = null
      }
    })()

    initializePromise = pendingInitialization
    return pendingInitialization
  }

  const setLowPerformanceMode = async (enabled: boolean): Promise<void> => {
    await initialize()

    if (saving.value || enabled === lowPerformanceMode.value) {
      return
    }

    const previousValue = lowPerformanceMode.value
    saving.value = true
    lowPerformanceMode.value = enabled

    try {
      await saveConfig({ lowPerformanceMode: enabled })
    } catch (error) {
      lowPerformanceMode.value = previousValue
      throw error
    } finally {
      saving.value = false
    }
  }

  return {
    lowPerformanceMode,
    windowActivity,
    initialized,
    saving,
    isBackgrounded,
    isLowPower,
    initialize,
    setLowPerformanceMode,
  }
})
