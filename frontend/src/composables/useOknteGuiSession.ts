// OK-NTE 原生设置会话（原生 GUI 直控 / 只读查看）
import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'
import { Service } from '@/api'
import { TaskCreateIn } from '@/api/models/TaskCreateIn'
import { useWebSocket } from '@/composables/useWebSocket'
import { WS_TASK_COMPLETED, WS_TASK_NOTICE } from '@/services/websocket/types'

const logger = window.electronAPI.getLogger('OK-NTE配置会话')

/**
 * OK-NTE 原生设置会话：打开 ok-nte 原生 GUI 并遮罩等待，保存后结束会话。
 *
 * 会话负责进程生命周期（WebSocket 订阅、遮罩、30 分钟超时自动保存、卸载
 * 清理）；配置的下发与回写由 ScriptConfig 任务完成。
 *
 * 查看会话（viewOnly）：只读预览（如「查看历史备份」），不显示保存入口，
 * 超时静默关闭；任务结束不回写 MAS 配置。
 */
export function useOknteGuiSession() {
  const { t } = useI18n()
  const { subscribe, unsubscribe } = useWebSocket()

  const oknteConfigLoading = ref(false)
  const oknteSubscriptionIds = ref<string[]>([])
  const oknteWebsocketId = ref<string | null>(null)
  const showOknteConfigMask = ref(false)
  const showOknteViewMask = ref(false)
  const stoppingOknteConfig = ref(false)

  // 原生设置会话超时自动保存的时长与提前提醒的提前量（避免无预告直接中断会话）
  const SESSION_TIMEOUT_MS = 30 * 60 * 1000
  const SESSION_WARNING_ADVANCE_MS = 30 * 1000

  let oknteConfigTimeout: number | null = null
  let oknteConfigWarningTimeout: number | null = null

  const clearSession = () => {
    oknteSubscriptionIds.value.forEach(unsubscribe)
    oknteSubscriptionIds.value = []
    oknteWebsocketId.value = null
    showOknteConfigMask.value = false
    showOknteViewMask.value = false
    if (oknteConfigTimeout) {
      window.clearTimeout(oknteConfigTimeout)
      oknteConfigTimeout = null
    }
    if (oknteConfigWarningTimeout) {
      window.clearTimeout(oknteConfigWarningTimeout)
      oknteConfigWarningTimeout = null
    }
  }

  const stopSession = async (keepOnFailure = false): Promise<boolean> => {
    const taskId = oknteWebsocketId.value
    if (!taskId) {
      clearSession()
      return true
    }
    if (stoppingOknteConfig.value) return false

    stoppingOknteConfig.value = true
    try {
      const response = await Service.stopTaskApiDispatchStopPost({ taskId })
      if (response.code !== 200) {
        throw new Error(response.message || t('edit.oknteSessionStopFailed'))
      }
      clearSession()
      return true
    } catch (e) {
      logger.error(e instanceof Error ? e.message : String(e))
      if (keepOnFailure) return false
      clearSession()
      return false
    } finally {
      stoppingOknteConfig.value = false
    }
  }

  const startSession = async (taskId: string, viewOnly = false): Promise<void> => {
    try {
      oknteConfigLoading.value = true
      const response = await Service.addTaskApiDispatchStartPost({
        taskId,
        mode: TaskCreateIn.mode.SCRIPT_CONFIG,
        viewOnly,
      })
      if (response.code !== 200 || !response.taskId) {
        throw new Error(response.message || t('edit.oknteSessionStartFailed'))
      }

      showOknteConfigMask.value = !viewOnly
      showOknteViewMask.value = viewOnly
      oknteWebsocketId.value = response.taskId
      oknteSubscriptionIds.value = [
        subscribe({ id: response.taskId, type: WS_TASK_NOTICE }, wsMessage => {
          if (wsMessage.data.level !== 'error') return

          message.error(t('edit.oknteSessionFailed', { p0: wsMessage.data.message }))
          void stopSession()
        }),
        subscribe({ id: response.taskId, type: WS_TASK_COMPLETED }, () => {
          clearSession()
        }),
      ]
      message.success(
        viewOnly ? t('edit.oknteViewOpened') : t('edit.oknteSessionOpened')
      )
      if (viewOnly) {
        // 查看会话：超时静默关闭，不提示也不触发「保存」
        oknteConfigTimeout = window.setTimeout(() => void stopSession(), SESSION_TIMEOUT_MS)
        return
      }
      oknteConfigWarningTimeout = window.setTimeout(() => {
        message.warning(t('edit.oknteSessionTimeoutWarn'))
      }, SESSION_TIMEOUT_MS - SESSION_WARNING_ADVANCE_MS)
      oknteConfigTimeout = window.setTimeout(saveSession, SESSION_TIMEOUT_MS)
    } catch (e) {
      logger.error(e instanceof Error ? e.message : String(e))
      message.error(e instanceof Error ? e.message : t('edit.oknteSessionStartFailed'))
      clearSession()
    } finally {
      oknteConfigLoading.value = false
    }
  }

  const saveSession = async () => {
    if (!oknteWebsocketId.value) return
    if (await stopSession(true)) {
      message.success(t('edit.okNteConfigurationThis'))
    } else {
      message.error(t('edit.couldNotSaveOk'))
    }
  }

  return {
    oknteConfigLoading,
    oknteWebsocketId,
    showOknteConfigMask,
    showOknteViewMask,
    stoppingOknteConfig,
    startSession,
    saveSession,
    stopSession,
  }
}
