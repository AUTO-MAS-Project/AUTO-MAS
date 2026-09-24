// ZZZ-OD 原生设置会话（原生 GUI 直控 / 只读查看）
import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'
import { Service } from '@/api'
import { TaskCreateIn } from '@/api/models/TaskCreateIn'
import { useWebSocket } from '@/composables/useWebSocket'
import { WS_TASK_COMPLETED, WS_TASK_NOTICE } from '@/services/websocket/types'

const logger = window.electronAPI.getLogger('ZZZ-OD配置会话')

/**
 * ZZZ-OD 原生设置会话：打开 zzz-od 原生 GUI 并遮罩等待，保存后结束会话。
 *
 * zzz-od 的 YAML 即唯一事实源，GUI 保存即落盘；会话只负责进程生命周期
 * （WebSocket 订阅、遮罩、30 分钟超时自动保存、卸载清理），不做配置写回。
 *
 * 查看会话（viewOnly）：只读预览（如「查看历史备份」），不显示保存入口，
 * 超时静默关闭；后端不注入基线也不回读字段。
 */
export function useZzzodGuiSession() {
  const { t } = useI18n()
  const { subscribe, unsubscribe } = useWebSocket()

  const zzzodConfigLoading = ref(false)
  const zzzodSubscriptionIds = ref<string[]>([])
  const zzzodWebsocketId = ref<string | null>(null)
  const showZzzodConfigMask = ref(false)
  const showZzzodViewMask = ref(false)
  const stoppingZzzodConfig = ref(false)

  // 原生设置会话超时自动保存的时长与提前提醒的提前量（避免无预告直接中断会话）
  const SESSION_TIMEOUT_MS = 30 * 60 * 1000
  const SESSION_WARNING_ADVANCE_MS = 30 * 1000

  let zzzodConfigTimeout: number | null = null
  let zzzodConfigWarningTimeout: number | null = null

  const clearSession = () => {
    zzzodSubscriptionIds.value.forEach(unsubscribe)
    zzzodSubscriptionIds.value = []
    zzzodWebsocketId.value = null
    showZzzodConfigMask.value = false
    showZzzodViewMask.value = false
    if (zzzodConfigTimeout) {
      window.clearTimeout(zzzodConfigTimeout)
      zzzodConfigTimeout = null
    }
    if (zzzodConfigWarningTimeout) {
      window.clearTimeout(zzzodConfigWarningTimeout)
      zzzodConfigWarningTimeout = null
    }
  }

  const stopSession = async (keepOnFailure = false): Promise<boolean> => {
    const taskId = zzzodWebsocketId.value
    if (!taskId) {
      clearSession()
      return true
    }
    if (stoppingZzzodConfig.value) return false

    stoppingZzzodConfig.value = true
    try {
      const response = await Service.stopTaskApiDispatchStopPost({ taskId })
      if (response.code !== 200) {
        throw new Error(response.message || t('edit.zzzodStopFailed'))
      }
      clearSession()
      return true
    } catch (e) {
      logger.error(e instanceof Error ? e.message : String(e))
      if (keepOnFailure) return false
      clearSession()
      return false
    } finally {
      stoppingZzzodConfig.value = false
    }
  }

  const startSession = async (
    taskId: string,
    viewOnly = false,
    instanceIdx?: number | null
  ): Promise<void> => {
    try {
      zzzodConfigLoading.value = true
      const response = await Service.addTaskApiDispatchStartPost({
        taskId,
        mode: TaskCreateIn.mode.SCRIPT_CONFIG,
        viewOnly,
        instanceIdx: instanceIdx ?? undefined,
      })
      if (response.code !== 200 || !response.taskId) {
        throw new Error(response.message || t('edit.zzzodStartFailed'))
      }

      showZzzodConfigMask.value = !viewOnly
      showZzzodViewMask.value = viewOnly
      zzzodWebsocketId.value = response.taskId
      zzzodSubscriptionIds.value = [
        subscribe({ id: response.taskId, type: WS_TASK_NOTICE }, wsMessage => {
          if (wsMessage.data.level !== 'error') return

          message.error(t('edit.zzzodSessionFailed', { p0: wsMessage.data.message }))
          void stopSession()
        }),
        subscribe({ id: response.taskId, type: WS_TASK_COMPLETED }, () => {
          clearSession()
        }),
      ]
      message.success(viewOnly ? t('edit.zzzodViewOpened') : t('edit.zzzodSessionOpened'))
      if (viewOnly) {
        // 查看会话：超时静默关闭，不提示也不触发「保存」
        zzzodConfigTimeout = window.setTimeout(() => void stopSession(), SESSION_TIMEOUT_MS)
        return
      }
      zzzodConfigWarningTimeout = window.setTimeout(() => {
        message.warning(t('edit.zzzodSessionTimeoutWarn'))
      }, SESSION_TIMEOUT_MS - SESSION_WARNING_ADVANCE_MS)
      zzzodConfigTimeout = window.setTimeout(saveSession, SESSION_TIMEOUT_MS)
    } catch (e) {
      logger.error(e instanceof Error ? e.message : String(e))
      message.error(e instanceof Error ? e.message : t('edit.zzzodStartFailed'))
      clearSession()
    } finally {
      zzzodConfigLoading.value = false
    }
  }

  const saveSession = async () => {
    if (!zzzodWebsocketId.value) return
    if (await stopSession(true)) {
      message.success(t('edit.zzzodSettingsSaved'))
    } else {
      message.error(t('edit.zzzodSettingsSaveFailed'))
    }
  }

  return {
    zzzodConfigLoading,
    zzzodWebsocketId,
    showZzzodConfigMask,
    showZzzodViewMask,
    stoppingZzzodConfig,
    startSession,
    saveSession,
    stopSession,
  }
}
