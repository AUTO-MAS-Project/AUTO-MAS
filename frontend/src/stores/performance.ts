import { observePreference } from '@/utils/preferenceAnalytics'
import { observeFeature } from '@/utils/featureAnalytics'
import { computed, onScopeDispose, ref, watch } from 'vue'
import { defineStore } from 'pinia'
import { useTaskRuntimeState } from '@/composables/useTaskRuntimeState'
import { getConfig, saveConfig } from '@/utils/config'

export type WindowActivity = 'visible' | 'background'

const DEFAULT_LOW_PERFORMANCE_MODE = false
/** 有脚本任务在跑就自动暂停主页动效：默认开，旧配置缺省同此 */
const DEFAULT_PAUSE_HOME_EFFECTS_WHEN_RUNNING = true
/** 任务清零后延迟这么久再恢复动效：避开队列内脚本交接、任务收尾的瞬时无运行窗口 */
const HOME_EFFECTS_RESUME_DELAY_MS = 5000

export const usePerformanceStore = defineStore('performance', () => {
  const lowPerformanceMode = ref(DEFAULT_LOW_PERFORMANCE_MODE)
  const pauseHomeEffectsWhenRunning = ref(DEFAULT_PAUSE_HOME_EFFECTS_WHEN_RUNNING)
  const windowActivity = ref<WindowActivity>('visible')
  const initialized = ref(false)
  const saving = ref(false)

  let initializePromise: Promise<void> | null = null
  let removeWindowActivityListener: (() => void) | null = null
  let windowActivityUpdateVersion = 0

  const isBackgrounded = computed(() => windowActivity.value === 'background')
  const isLowPower = computed(() => lowPerformanceMode.value || isBackgrounded.value)

  // 任务运行状态来自常驻订阅（WS 增量 + HTTP 快照兜底），这里只读
  const { scriptStatusesByType } = useTaskRuntimeState()
  /** 是否有脚本任务在运行（手动 / 定时 / 周期 / 自动代理都算） */
  const anyScriptRunning = computed(() =>
    [...scriptStatusesByType.value.values()].some(status => status.running)
  )
  /**
   * 脚本运行期间自动暂停主页动效；与低性能模式、窗口后台是三条独立的停帧路径。
   * 暂停立即生效；恢复延后 HOME_EFFECTS_RESUME_DELAY_MS，队列内脚本交接或任务收尾
   * 时会短暂没有脚本处于「运行」，延迟恢复可避免动效跟着一闪一闪。
   */
  const homeEffectsPaused = ref(false)
  /** 用户点了暂停提示上的「继续」：只对当前这轮任务生效，动效恢复时一并复位。
   * 放在 store 里而不是组件里：主页不在 keep-alive 里，切页回来组件会重建，
   * 局部状态会把「恢复到本轮任务结束」变成「恢复到切页为止」。 */
  const homeEffectsManuallyResumed = ref(false)
  let resumeTimer: ReturnType<typeof setTimeout> | null = null

  const clearResumeTimer = () => {
    if (resumeTimer !== null) {
      clearTimeout(resumeTimer)
      resumeTimer = null
    }
  }

  watch(
    [anyScriptRunning, pauseHomeEffectsWhenRunning],
    ([running, enabled]) => {
      clearResumeTimer()
      if (!enabled) {
        homeEffectsPaused.value = false
        homeEffectsManuallyResumed.value = false
        return
      }
      if (running) {
        homeEffectsPaused.value = true
        return
      }
      if (!homeEffectsPaused.value) return
      resumeTimer = setTimeout(() => {
        resumeTimer = null
        homeEffectsPaused.value = false
        homeEffectsManuallyResumed.value = false
      }, HOME_EFFECTS_RESUME_DELAY_MS)
    },
    { immediate: true }
  )

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
        pauseHomeEffectsWhenRunning.value = config.pauseHomeEffectsWhenRunning !== false
      } catch {
        lowPerformanceMode.value = DEFAULT_LOW_PERFORMANCE_MODE
        pauseHomeEffectsWhenRunning.value = DEFAULT_PAUSE_HOME_EFFECTS_WHEN_RUNNING
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
      await observePreference('performance', enabled ? 'low' : 'normal', () =>
        saveConfig({ lowPerformanceMode: enabled })
      )
    } catch (error) {
      lowPerformanceMode.value = previousValue
      throw error
    } finally {
      saving.value = false
    }
  }

  const setPauseHomeEffectsWhenRunning = async (enabled: boolean): Promise<void> => {
    await initialize()

    if (saving.value || enabled === pauseHomeEffectsWhenRunning.value) {
      return
    }

    const previousValue = pauseHomeEffectsWhenRunning.value
    saving.value = true
    pauseHomeEffectsWhenRunning.value = enabled

    try {
      await observeFeature(
        'settings_change_finished',
        {
          setting_kind: 'performance',
          setting_key: 'performance_effects',
          value_kind: enabled ? 'enabled' : 'disabled',
        },
        () => saveConfig({ pauseHomeEffectsWhenRunning: enabled }),
        () => 'success'
      )
    } catch (error) {
      pauseHomeEffectsWhenRunning.value = previousValue
      throw error
    } finally {
      saving.value = false
    }
  }

  onScopeDispose(() => {
    clearResumeTimer()
    removeWindowActivityListener?.()
    removeWindowActivityListener = null
  })

  return {
    lowPerformanceMode,
    pauseHomeEffectsWhenRunning,
    windowActivity,
    initialized,
    saving,
    isBackgrounded,
    isLowPower,
    anyScriptRunning,
    homeEffectsPaused,
    homeEffectsManuallyResumed,
    initialize,
    setLowPerformanceMode,
    setPauseHomeEffectsWhenRunning,
  }
})
