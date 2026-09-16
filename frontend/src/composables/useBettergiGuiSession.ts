// BetterGI 原生设置会话（原生 GUI 直控）
import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'
import { Service } from '@/api'
import { TaskCreateIn } from '@/api/models/TaskCreateIn'
import { useWebSocket } from '@/composables/useWebSocket'
import { WS_TASK_COMPLETED, WS_TASK_NOTICE } from '@/services/websocket/types'

const logger = window.electronAPI.getLogger('BetterGI配置会话')

/**
 * BetterGI 原生设置会话：打开 BetterGI 原生界面并遮罩等待，保存快照后结束会话。
 *
 * 配置会话（viewOnly=false）：30 分钟超时前 30 秒提醒并自动保存；
 * 查看会话（viewOnly=true）：只读预览（如「查看历史备份」），超时静默关闭、
 * 不自动保存、无保存按钮。
 */
export function useBettergiGuiSession() {
  const { t } = useI18n()
  const { subscribe, unsubscribe } = useWebSocket()

  const bettergiConfigLoading = ref(false)
  const bettergiSubscriptionIds = ref<string[]>([])
  const bettergiWebsocketId = ref<string | null>(null)
  const showBettergiConfigMask = ref(false)
  const showBettergiViewMask = ref(false)
  // 当前会话类型（查看会话超时静默关闭、无保存入口）
  const currentSessionViewOnly = ref(false)
  const stoppingBettergiConfig = ref(false)

  // 原生设置会话超时自动保存的时长与提前提醒的提前量（避免无预告直接中断会话）
  const SESSION_TIMEOUT_MS = 30 * 60 * 1000
  const SESSION_WARNING_ADVANCE_MS = 30 * 1000

  let bettergiConfigTimeout: number | null = null
  let bettergiConfigWarningTimeout: number | null = null

  const clearSession = () => {
    bettergiSubscriptionIds.value.forEach(unsubscribe)
    bettergiSubscriptionIds.value = []
    bettergiWebsocketId.value = null
    showBettergiConfigMask.value = false
    showBettergiViewMask.value = false
    if (bettergiConfigTimeout) {
      window.clearTimeout(bettergiConfigTimeout)
      bettergiConfigTimeout = null
    }
    if (bettergiConfigWarningTimeout) {
      window.clearTimeout(bettergiConfigWarningTimeout)
      bettergiConfigWarningTimeout = null
    }
  }

  const stopSession = async (keepOnFailure = false): Promise<boolean> => {
    const taskId = bettergiWebsocketId.value
    if (!taskId) {
      clearSession()
      return true
    }
    if (stoppingBettergiConfig.value) return false

    stoppingBettergiConfig.value = true
    try {
      const response = await Service.stopTaskApiDispatchStopPost({ taskId })
      if (response.code !== 200) {
        throw new Error(response.message || t('edit.bettergiStopFailed'))
      }
      clearSession()
      return true
    } catch (e) {
      logger.error(e instanceof Error ? e.message : String(e))
      if (keepOnFailure) return false
      clearSession()
      return false
    } finally {
      stoppingBettergiConfig.value = false
    }
  }

  const startSession = async (userId: string, viewOnly = false): Promise<void> => {
    try {
      bettergiConfigLoading.value = true
      currentSessionViewOnly.value = viewOnly
      const response = await Service.addTaskApiDispatchStartPost({
        taskId: userId,
        mode: TaskCreateIn.mode.SCRIPT_CONFIG,
        viewOnly,
      })
      if (response.code !== 200 || !response.taskId) {
        throw new Error(response.message || t('edit.bettergiStartFailed'))
      }

      if (viewOnly) {
        showBettergiViewMask.value = true
      } else {
        showBettergiConfigMask.value = true
      }
      bettergiWebsocketId.value = response.taskId
      bettergiSubscriptionIds.value = [
        subscribe({ id: response.taskId, type: WS_TASK_NOTICE }, wsMessage => {
          if (wsMessage.data.level !== 'error') return

          message.error(t('edit.bettergiSessionFailed', { p0: wsMessage.data.message }))
          void stopSession()
        }),
        subscribe({ id: response.taskId, type: WS_TASK_COMPLETED }, () => {
          clearSession()
        }),
      ]
      message.success(viewOnly ? t('edit.bettergiViewOpened') : t('edit.bettergiSessionOpened'))
      if (viewOnly) {
        // 查看会话：超时静默关闭，不提示也不触发「保存」
        bettergiConfigTimeout = window.setTimeout(() => void stopSession(), SESSION_TIMEOUT_MS)
        return
      }
      bettergiConfigWarningTimeout = window.setTimeout(() => {
        message.warning(t('edit.bettergiSessionTimeoutWarn'))
      }, SESSION_TIMEOUT_MS - SESSION_WARNING_ADVANCE_MS)
      bettergiConfigTimeout = window.setTimeout(saveSession, SESSION_TIMEOUT_MS)
    } catch (e) {
      logger.error(e instanceof Error ? e.message : String(e))
      message.error(
        e instanceof Error
          ? e.message
          : viewOnly
            ? t('edit.bettergiViewStartFailed')
            : t('edit.bettergiStartFailed')
      )
      clearSession()
    } finally {
      bettergiConfigLoading.value = false
    }
  }

  const saveSession = async () => {
    if (!bettergiWebsocketId.value) return
    if (currentSessionViewOnly.value) {
      // 查看会话：无保存语义，直接关闭
      await stopSession()
      return
    }
    if (await stopSession(true)) {
      message.success(t('edit.bettergiSettingsSaved'))
    } else {
      message.error(t('edit.bettergiSettingsSaveFailed'))
    }
  }

  const dispose = () => {
    void stopSession()
  }

  return {
    bettergiConfigLoading,
    bettergiWebsocketId,
    showBettergiConfigMask,
    showBettergiViewMask,
    currentSessionViewOnly,
    stoppingBettergiConfig,
    startSession,
    saveSession,
    stopSession,
    dispose,
  }
}
