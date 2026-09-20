// 原生设置会话通用实现（原生 GUI 配置 / 只读查看）
import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'
import { Service } from '@/api'
import { TaskCreateIn } from '@/api/models/TaskCreateIn'
import { useWebSocket } from '@/composables/useWebSocket'
import { WS_TASK_COMPLETED, WS_TASK_NOTICE } from '@/services/websocket/types'

/**
 * 原生设置会话（MAA / ok-ww / MaaEnd 共用）：打开原生 GUI 并遮罩等待，保存后
 * 结束会话。各专项差异只有日志名与 i18n 词条，由 options 注入，页面直接解构
 * 通用状态即可（专项需要脚本前缀命名时用薄包装 re-export，见各 use*GuiSession）。
 *
 * 会话负责进程生命周期（WebSocket 订阅、遮罩、30 分钟超时自动保存、卸载
 * 清理）；配置的下发与回写由 ScriptConfig 任务完成。
 *
 * 查看会话（viewOnly）：只读预览（如「查看历史备份」），不显示保存入口，
 * 超时静默关闭；任务结束不回写 MAS 配置。
 */
export function useNativeGuiSession(options: {
  loggerName: string
  keys: {
    stopFailed: string
    startFailed: string
    /** WS 错误通知的正文词条（{p0} 为后端错误消息） */
    setupFailed: string
    opened: string
    viewOpened: string
    timeoutWarn: string
    saved: string
    saveFailed: string
  }
}) {
  const { t } = useI18n()
  const { subscribe, unsubscribe } = useWebSocket()
  const keys = options.keys

  const logger = window.electronAPI.getLogger(options.loggerName)

  const configLoading = ref(false)
  const subscriptionIds = ref<string[]>([])
  const taskId = ref<string | null>(null)
  const showConfigMask = ref(false)
  const showViewMask = ref(false)
  const stopping = ref(false)

  // 原生设置会话超时自动保存的时长与提前提醒的提前量（避免无预告直接中断会话）
  const SESSION_TIMEOUT_MS = 30 * 60 * 1000
  const SESSION_WARNING_ADVANCE_MS = 30 * 1000

  let configTimeout: number | null = null
  let warningTimeout: number | null = null

  const clearSession = () => {
    subscriptionIds.value.forEach(unsubscribe)
    subscriptionIds.value = []
    taskId.value = null
    showConfigMask.value = false
    showViewMask.value = false
    if (configTimeout) {
      window.clearTimeout(configTimeout)
      configTimeout = null
    }
    if (warningTimeout) {
      window.clearTimeout(warningTimeout)
      warningTimeout = null
    }
  }

  const stopSession = async (keepOnFailure = false): Promise<boolean> => {
    const currentTaskId = taskId.value
    if (!currentTaskId) {
      clearSession()
      return true
    }
    if (stopping.value) return false

    stopping.value = true
    try {
      const response = await Service.stopTaskApiDispatchStopPost({ taskId: currentTaskId })
      if (response.code !== 200) {
        throw new Error(response.message || t(keys.stopFailed))
      }
      clearSession()
      return true
    } catch (e) {
      logger.error(e instanceof Error ? e.message : String(e))
      if (keepOnFailure) return false
      clearSession()
      return false
    } finally {
      stopping.value = false
    }
  }

  const startSession = async (startTaskId: string, viewOnly = false): Promise<void> => {
    try {
      configLoading.value = true
      const response = await Service.addTaskApiDispatchStartPost({
        taskId: startTaskId,
        mode: TaskCreateIn.mode.SCRIPT_CONFIG,
        viewOnly,
      })
      if (response.code !== 200 || !response.taskId) {
        throw new Error(response.message || t(keys.startFailed))
      }

      showConfigMask.value = !viewOnly
      showViewMask.value = viewOnly
      taskId.value = response.taskId
      subscriptionIds.value = [
        subscribe({ id: response.taskId, type: WS_TASK_NOTICE }, wsMessage => {
          if (wsMessage.data.level !== 'error') return

          message.error(t(keys.setupFailed, { p0: wsMessage.data.message }))
          void stopSession()
        }),
        subscribe({ id: response.taskId, type: WS_TASK_COMPLETED }, () => {
          clearSession()
        }),
      ]
      message.success(viewOnly ? t(keys.viewOpened) : t(keys.opened))
      if (viewOnly) {
        // 查看会话：超时静默关闭，不提示也不触发「保存」
        configTimeout = window.setTimeout(() => void stopSession(), SESSION_TIMEOUT_MS)
        return
      }
      warningTimeout = window.setTimeout(() => {
        message.warning(t(keys.timeoutWarn))
      }, SESSION_TIMEOUT_MS - SESSION_WARNING_ADVANCE_MS)
      configTimeout = window.setTimeout(saveSession, SESSION_TIMEOUT_MS)
    } catch (e) {
      logger.error(e instanceof Error ? e.message : String(e))
      message.error(e instanceof Error ? e.message : t(keys.startFailed))
      clearSession()
    } finally {
      configLoading.value = false
    }
  }

  const saveSession = async () => {
    if (!taskId.value) return
    if (await stopSession(true)) {
      message.success(t(keys.saved))
    } else {
      message.error(t(keys.saveFailed))
    }
  }

  return {
    configLoading,
    taskId,
    showConfigMask,
    showViewMask,
    stopping,
    startSession,
    saveSession,
    stopSession,
  }
}
