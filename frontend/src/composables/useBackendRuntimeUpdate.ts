/**
 * Runtime 链路的后端更新
 *
 * 灰度开关打开（`managed`）时，标题栏的「检测到后端更新」入口不再走「关后端 → 跳初始化页
 * → 后端自己下整包 → 拉安装器」那条链，而是让主进程按 停机 → `bootstrap --version` →
 * 重新监督 三步完成，本模块只负责把进度与三类失败结局搬到界面上。
 *
 * `development` 模式下 Runtime 只监督开发者自己的检出、不碰源码，入口直接禁用。
 * 灰度开关关闭（`off`）时本模块不参与，标题栏仍走原有流程。
 */

import { computed, ref } from 'vue'
import { translate as t } from '@/i18n'

import type {
  RuntimeLaunchMode,
  RuntimeUpdateOutcome,
  RuntimeUpdateRetryAction,
  RuntimeUpdateStage,
} from '@/types/electron'
import { reconnectNow } from '@/services/websocket/connection'
import {
  beginIntentionalBackendRestart,
  endIntentionalBackendRestart,
} from '@/composables/useAppLifecycle'
import { getBackendVersion } from './useVersionService'

const logger = window.electronAPI.getLogger('后端更新')

/**
 * 进度条的段序。
 *
 * 中间六段就是初始化界面那六段（`mirror` / `pip` / `git` 在 Runtime 链路没有对应物，
 * 主进程进 bootstrap 时立刻置完成），首尾两段是更新独有的停机与重启。
 */
const UPDATE_STAGE_ORDER: readonly RuntimeUpdateStage[] = [
  'shutdown',
  'mirror',
  'python',
  'pip',
  'git',
  'repository',
  'dependency',
  'restart',
]

// 模块级状态：标题栏入口与进度弹窗共用同一份。
const launchMode = ref<RuntimeLaunchMode | null>(null)
const modalVisible = ref(false)
const running = ref(false)
const cancelling = ref(false)
const targetVersion = ref('')
const currentMessage = ref('')
const currentStage = ref<RuntimeUpdateStage | null>(null)
const completedStages = ref<RuntimeUpdateStage[]>([])
const outcome = ref<RuntimeUpdateOutcome | null>(null)
const restartingBackend = ref(false)
const automatic = ref(false)

export const isBackendRuntimeUpdating = (): boolean => running.value

export function finishBackendRuntimeReconnect(): void {
  if (!running.value && outcome.value?.phase === 'connection') {
    outcome.value = { success: true }
    modalVisible.value = false
  }
}

let progressListenerAttached = false

/** 只查一次：灰度开关是进程启动时定下的，一个生命周期内不会变。 */
async function ensureLaunchMode(): Promise<RuntimeLaunchMode> {
  if (launchMode.value) return launchMode.value
  try {
    // 灰度开关升级为三级来源后返回的是 {persisted, mode, source}，这里只关心生效值。
    launchMode.value = (await window.electronAPI.getRuntimeLaunchMode()).mode
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.warn(`获取 Runtime 启动模式失败，按 off 处理: ${errorMsg}`)
    launchMode.value = 'off'
  }
  return launchMode.value
}

function attachProgressListener(): void {
  if (progressListenerAttached) return
  window.electronAPI.onBackendUpdateProgress(progress => {
    currentStage.value = progress.stage
    currentMessage.value = progress.message
    if (progress.status === 'completed' && !completedStages.value.includes(progress.stage)) {
      completedStages.value = [...completedStages.value, progress.stage]
    }
  })
  progressListenerAttached = true
}

function detachProgressListener(): void {
  if (!progressListenerAttached) return
  window.electronAPI.removeBackendUpdateProgressListener?.()
  progressListenerAttached = false
}

function resetProgress(): void {
  currentStage.value = null
  currentMessage.value = ''
  completedStages.value = []
  outcome.value = null
  cancelling.value = false
}

/** 更新成功后把连接与版本信息拉回来，不必跳初始化页。 */
async function refreshAfterUpdate(): Promise<boolean> {
  try {
    if (!(await reconnectNow('后端更新完成'))) return false
    return (await getBackendVersion()) !== false
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.warn(`更新后刷新后端状态失败: ${errorMsg}`)
    return false
  }
}

async function settle(result: RuntimeUpdateOutcome): Promise<void> {
  try {
    outcome.value = result.deferred ? null : result
    if (result.deferred) modalVisible.value = false
    if (result.success && !(await refreshAfterUpdate())) {
      outcome.value = {
        success: false,
        phase: 'connection',
        error: t('comp.backendHotUpdateFailedConnection'),
      }
      modalVisible.value = true
    }
  } finally {
    running.value = false
    cancelling.value = false
    detachProgressListener()
    endIntentionalBackendRestart('Runtime 后端更新结束')
  }
}

export async function applyStagedBackendUpdate(): Promise<void> {
  if (running.value || outcome.value?.success === false) return
  if ((await ensureLaunchMode()) !== 'managed' || running.value) return
  resetProgress()
  automatic.value = true
  running.value = true
  modalVisible.value = false
  beginIntentionalBackendRestart('自动后端更新')
  try {
    const result = await window.electronAPI.applyStagedBackendUpdate()
    if (result.deferred || result.cancelled) {
      await settle(result)
      outcome.value = null
      return
    }
    if (!result.success) modalVisible.value = true
    await settle(result)
  } catch (error) {
    modalVisible.value = true
    await settle({ success: false, phase: 'restart', error: String(error) })
  }
}

export function useBackendRuntimeUpdate() {
  const isRuntimeManaged = computed(() => launchMode.value === 'managed')
  const isRuntimeDevelopment = computed(() => launchMode.value === 'development')

  /** 完成的段数占总段数，Runtime 不给细粒度百分比，这里也不编。 */
  const overallPercent = computed(() => {
    const done = completedStages.value.filter(stage => UPDATE_STAGE_ORDER.includes(stage)).length
    return Math.round((done / UPDATE_STAGE_ORDER.length) * 100)
  })

  const stageOrder = computed(() => UPDATE_STAGE_ORDER)

  async function start(version: string): Promise<void> {
    if (running.value) return

    resetProgress()
    automatic.value = false
    targetVersion.value = version
    modalVisible.value = true
    running.value = true
    attachProgressListener()

    // Runtime 更新同样是「先停后端，再 workspace sync，最后重新监督」。停机期间的断开
    // 属于计划内：协调器若按事故处理，会在 sync 期间把后端重新拉起来，而 sync 发现后端
    // 仍在跑就会失败——它和 Runtime 命令不共用 backendService 的串行队列，拦不住。
    beginIntentionalBackendRestart('Runtime 后端更新')

    logger.info(`开始经 Runtime 更新后端到 ${version}`)
    try {
      await settle(await window.electronAPI.updateBackendViaRuntime(version))
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`Runtime 更新后端失败: ${errorMsg}`)
      await settle({ success: false, phase: 'bootstrap', error: errorMsg })
    }
  }

  async function retry(action: RuntimeUpdateRetryAction): Promise<void> {
    if (running.value) return

    outcome.value = null
    cancelling.value = false
    running.value = true
    attachProgressListener()

    // 单步重试同样会走停机与源码替换，理由同 start()
    beginIntentionalBackendRestart(`Runtime 后端更新重试: ${action}`)

    logger.info(`重试后端更新: ${action}`)
    try {
      await settle(await window.electronAPI.retryBackendUpdate(action))
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`重试后端更新失败: ${errorMsg}`)
      await settle({ success: false, phase: 'bootstrap', error: errorMsg })
    }
  }

  async function cancel(): Promise<void> {
    if (!running.value) return
    cancelling.value = true
    try {
      await window.electronAPI.cancelBackendUpdate()
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.warn(`取消后端更新失败: ${errorMsg}`)
      cancelling.value = false
    }
  }

  /** `restart` 结局下的兜底：源码与依赖都已就位，只是后端没起来，再拉一次。 */
  async function restartBackend(): Promise<void> {
    if (outcome.value?.phase === 'connection') {
      if (await refreshAfterUpdate()) finishBackendRuntimeReconnect()
      return
    }
    if (automatic.value) {
      await retry('bootstrap')
      return
    }
    if (running.value || restartingBackend.value) return
    restartingBackend.value = true
    running.value = true
    beginIntentionalBackendRestart('Runtime 更新后重新启动后端')
    try {
      const result = await window.electronAPI.backendStart()
      if (result.success) {
        await settle({ success: true })
        return
      }
      await settle({
        success: false,
        phase: 'restart',
        error: result.error,
        logs: result.logs,
      })
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      await settle({ success: false, phase: 'restart', error: errorMsg })
    } finally {
      restartingBackend.value = false
    }
  }

  function close(): void {
    if (running.value) return
    modalVisible.value = false
    if (automatic.value && outcome.value?.success === false) return
    resetProgress()
  }

  return {
    launchMode,
    ensureLaunchMode,
    isRuntimeManaged,
    isRuntimeDevelopment,
    modalVisible,
    running,
    isAutomatic: automatic,
    cancelling,
    restartingBackend,
    targetVersion,
    currentStage,
    currentMessage,
    completedStages,
    stageOrder,
    overallPercent,
    outcome,
    start,
    retry,
    cancel,
    restartBackend,
    close,
  }
}
