// MaaEnd 原生设置会话（MXU GUI 配置 / 只读查看）
import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'
import { Service } from '@/api'
import { TaskCreateIn } from '@/api/models/TaskCreateIn'
import { useWebSocket } from '@/composables/useWebSocket'
import { WS_TASK_COMPLETED, WS_TASK_NOTICE } from '@/services/websocket/types'

const logger = window.electronAPI.getLogger('MaaEnd配置会话')

/**
 * MaaEnd 原生设置会话：打开 MaaEnd（MXU）GUI 并遮罩等待，保存后结束会话。
 *
 * 会话负责进程生命周期（WebSocket 订阅、遮罩、30 分钟超时自动保存、卸载
 * 清理）；配置的下发与回写由 ScriptConfig 任务完成。
 *
 * 查看会话（viewOnly）：只读预览（如「查看历史备份」），不显示保存入口，
 * 超时静默关闭；任务结束不回写 MAS 配置。
 */
export function useMaaEndGuiSession() {
  const { t } = useI18n()
  const { subscribe, unsubscribe } = useWebSocket()

  const maaEndConfigLoading = ref(false)
  const maaEndSubscriptionIds = ref<string[]>([])
  const maaEndTaskId = ref<string | null>(null)
  const showMaaEndConfigMask = ref(false)
  const showMaaEndViewMask = ref(false)
  const stoppingMaaEndConfig = ref(false)

  // 原生设置会话超时自动保存的时长与提前提醒的提前量（避免无预告直接中断会话）
  const SESSION_TIMEOUT_MS = 30 * 60 * 1000
  const SESSION_WARNING_ADVANCE_MS = 30 * 1000

  let maaEndConfigTimeout: number | null = null
  let maaEndWarningTimeout: number | null = null

  const clearSession = () => {
    maaEndSubscriptionIds.value.forEach(unsubscribe)
    maaEndSubscriptionIds.value = []
    maaEndTaskId.value = null
    showMaaEndConfigMask.value = false
    showMaaEndViewMask.value = false
    if (maaEndConfigTimeout) {
      window.clearTimeout(maaEndConfigTimeout)
      maaEndConfigTimeout = null
    }
    if (maaEndWarningTimeout) {
      window.clearTimeout(maaEndWarningTimeout)
      maaEndWarningTimeout = null
    }
  }

  const stopSession = async (keepOnFailure = false): Promise<boolean> => {
    const taskId = maaEndTaskId.value
    if (!taskId) {
      clearSession()
      return true
    }
    if (stoppingMaaEndConfig.value) return false

    stoppingMaaEndConfig.value = true
    try {
      const response = await Service.stopTaskApiDispatchStopPost({ taskId })
      if (response.code !== 200) {
        throw new Error(response.message || t('edit.maaendSessionStopFailed'))
      }
      clearSession()
      return true
    } catch (e) {
      logger.error(e instanceof Error ? e.message : String(e))
      if (keepOnFailure) return false
      clearSession()
      return false
    } finally {
      stoppingMaaEndConfig.value = false
    }
  }

  const startSession = async (taskId: string, viewOnly = false): Promise<void> => {
    try {
      maaEndConfigLoading.value = true
      const response = await Service.addTaskApiDispatchStartPost({
        taskId,
        mode: TaskCreateIn.mode.SCRIPT_CONFIG,
        viewOnly,
      })
      if (response.code !== 200 || !response.taskId) {
        throw new Error(response.message || t('edit.maaendSessionStartFailed'))
      }

      showMaaEndConfigMask.value = !viewOnly
      showMaaEndViewMask.value = viewOnly
      maaEndTaskId.value = response.taskId
      maaEndSubscriptionIds.value = [
        subscribe({ id: response.taskId, type: WS_TASK_NOTICE }, wsMessage => {
          if (wsMessage.data.level !== 'error') return

          message.error(t('edit.maaendConfigurationErrorP0', { p0: wsMessage.data.message }))
          void stopSession()
        }),
        subscribe({ id: response.taskId, type: WS_TASK_COMPLETED }, () => {
          clearSession()
        }),
      ]
      message.success(viewOnly ? t('edit.maaendViewOpened') : t('edit.maaendSessionOpened'))
      if (viewOnly) {
        // 查看会话：超时静默关闭，不提示也不触发「保存」
        maaEndConfigTimeout = window.setTimeout(() => void stopSession(), SESSION_TIMEOUT_MS)
        return
      }
      maaEndWarningTimeout = window.setTimeout(() => {
        message.warning(t('edit.maaendSessionTimeoutWarn'))
      }, SESSION_TIMEOUT_MS - SESSION_WARNING_ADVANCE_MS)
      maaEndConfigTimeout = window.setTimeout(saveSession, SESSION_TIMEOUT_MS)
    } catch (e) {
      logger.error(e instanceof Error ? e.message : String(e))
      message.error(e instanceof Error ? e.message : t('edit.maaendSessionStartFailed'))
      clearSession()
    } finally {
      maaEndConfigLoading.value = false
    }
  }

  const saveSession = async () => {
    if (!maaEndTaskId.value) return
    if (await stopSession(true)) {
      message.success(t('edit.maaendConfigurationSaved'))
    } else {
      message.error(t('edit.maaendSessionStopFailed'))
    }
  }

  return {
    maaEndConfigLoading,
    maaEndTaskId,
    showMaaEndConfigMask,
    showMaaEndViewMask,
    stoppingMaaEndConfig,
    startSession,
    saveSession,
    stopSession,
  }
}
