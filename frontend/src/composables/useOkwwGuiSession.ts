// ok-ww 原生设置会话（原生 GUI 配置 / 只读查看）
import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'
import { Service } from '@/api'
import { TaskCreateIn } from '@/api/models/TaskCreateIn'
import { useWebSocket } from '@/composables/useWebSocket'
import { WS_TASK_COMPLETED, WS_TASK_NOTICE } from '@/services/websocket/types'

const logger = window.electronAPI.getLogger('ok-ww配置会话')

/**
 * ok-ww 原生设置会话：打开 ok-ww 原生 GUI 并遮罩等待，保存后结束会话。
 *
 * 会话负责进程生命周期（WebSocket 订阅、遮罩、30 分钟超时自动保存、卸载
 * 清理）；配置的下发与回写由 ScriptConfig 任务完成。
 *
 * 查看会话（viewOnly）：只读预览（如「查看历史备份」），不显示保存入口，
 * 超时静默关闭；任务结束不回写 MAS 配置。
 */
export function useOkwwGuiSession() {
  const { t } = useI18n()
  const { subscribe, unsubscribe } = useWebSocket()

  const okwwConfigLoading = ref(false)
  const okwwSubscriptionIds = ref<string[]>([])
  const okwwTaskId = ref<string | null>(null)
  const showOkwwConfigMask = ref(false)
  const showOkwwViewMask = ref(false)
  const stoppingOkwwConfig = ref(false)

  // 原生设置会话超时自动保存的时长与提前提醒的提前量（避免无预告直接中断会话）
  const SESSION_TIMEOUT_MS = 30 * 60 * 1000
  const SESSION_WARNING_ADVANCE_MS = 30 * 1000

  let okwwConfigTimeout: number | null = null
  let okwwConfigWarningTimeout: number | null = null

  const clearSession = () => {
    okwwSubscriptionIds.value.forEach(unsubscribe)
    okwwSubscriptionIds.value = []
    okwwTaskId.value = null
    showOkwwConfigMask.value = false
    showOkwwViewMask.value = false
    if (okwwConfigTimeout) {
      window.clearTimeout(okwwConfigTimeout)
      okwwConfigTimeout = null
    }
    if (okwwConfigWarningTimeout) {
      window.clearTimeout(okwwConfigWarningTimeout)
      okwwConfigWarningTimeout = null
    }
  }

  const stopSession = async (keepOnFailure = false): Promise<boolean> => {
    const taskId = okwwTaskId.value
    if (!taskId) {
      clearSession()
      return true
    }
    if (stoppingOkwwConfig.value) return false

    stoppingOkwwConfig.value = true
    try {
      const response = await Service.stopTaskApiDispatchStopPost({ taskId })
      if (response.code !== 200) {
        throw new Error(response.message || t('edit.okwwSessionStopFailed'))
      }
      clearSession()
      return true
    } catch (e) {
      logger.error(e instanceof Error ? e.message : String(e))
      if (keepOnFailure) return false
      clearSession()
      return false
    } finally {
      stoppingOkwwConfig.value = false
    }
  }

  const startSession = async (taskId: string, viewOnly = false): Promise<void> => {
    try {
      okwwConfigLoading.value = true
      const response = await Service.addTaskApiDispatchStartPost({
        taskId,
        mode: TaskCreateIn.mode.SCRIPT_CONFIG,
        viewOnly,
      })
      if (response.code !== 200 || !response.taskId) {
        throw new Error(response.message || t('edit.okwwSessionStartFailed'))
      }

      showOkwwConfigMask.value = !viewOnly
      showOkwwViewMask.value = viewOnly
      okwwTaskId.value = response.taskId
      okwwSubscriptionIds.value = [
        subscribe({ id: response.taskId, type: WS_TASK_NOTICE }, wsMessage => {
          if (wsMessage.data.level !== 'error') return

          message.error(t('edit.okWwSetupFailed', { p0: wsMessage.data.message }))
          void stopSession()
        }),
        subscribe({ id: response.taskId, type: WS_TASK_COMPLETED }, () => {
          clearSession()
        }),
      ]
      message.success(
        viewOnly ? t('edit.okwwViewOpened') : t('edit.okwwSessionOpened')
      )
      if (viewOnly) {
        // 查看会话：超时静默关闭，不提示也不触发「保存」
        okwwConfigTimeout = window.setTimeout(() => void stopSession(), SESSION_TIMEOUT_MS)
        return
      }
      okwwConfigWarningTimeout = window.setTimeout(() => {
        message.warning(t('edit.okwwSessionTimeoutWarn'))
      }, SESSION_TIMEOUT_MS - SESSION_WARNING_ADVANCE_MS)
      okwwConfigTimeout = window.setTimeout(saveSession, SESSION_TIMEOUT_MS)
    } catch (e) {
      logger.error(e instanceof Error ? e.message : String(e))
      message.error(e instanceof Error ? e.message : t('edit.okwwSessionStartFailed'))
      clearSession()
    } finally {
      okwwConfigLoading.value = false
    }
  }

  const saveSession = async () => {
    if (!okwwTaskId.value) return
    if (await stopSession(true)) {
      message.success(t('edit.okWwSettingsSaved'))
    } else {
      message.error(t('edit.couldNotSaveOk2'))
    }
  }

  return {
    okwwConfigLoading,
    okwwTaskId,
    showOkwwConfigMask,
    showOkwwViewMask,
    stoppingOkwwConfig,
    startSession,
    saveSession,
    stopSession,
  }
}
