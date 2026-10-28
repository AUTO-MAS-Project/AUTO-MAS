import {
  requestTaskStart,
  stopNativeConfig,
  type NativeConfigStopAction,
} from '@/composables/useTaskApi'
// 原生设置会话通用实现（原生 GUI 配置 / 只读查看）
import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'
import { TaskCreateIn } from '@/api/models/TaskCreateIn'
import { useWebSocket } from '@/composables/useWebSocket'
import { showConfigDiscardWarning } from '@/utils/configSessionDiscard'
import {
  WS_TASK_COMPLETED,
  WS_TASK_CONFIG_DISCARDED,
  WS_TASK_NOTICE,
} from '@/services/websocket/types'

/**
 * 原生设置会话：打开原生 GUI 并遮罩等待，保存后结束会话。
 * 专项提供启动参数、日志名与 i18n 词条，页面直接解构
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
    viewStartFailed?: string
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
  const currentSessionViewOnly = ref(false)
  const stopping = ref(false)
  let startingPromise: Promise<boolean> | null = null
  let stoppingPromise: Promise<boolean> | null = null
  let savingPromise: Promise<void> | null = null
  let keepFailedSession = false
  let keepDiscardFrames = false
  // 本次会话的改动是否已被后端丢弃（原因见后端 WSTaskConfigDiscardedData）
  let discardedReason: string | null = null

  // 原生设置会话超时自动保存的时长与提前提醒的提前量（避免无预告直接中断会话）
  const SESSION_TIMEOUT_MS = 30 * 60 * 1000
  const SESSION_WARNING_ADVANCE_MS = 30 * 1000
  // 停止响应返回后，再给后端已写出的 WebSocket 帧留一个回合，避免「已保存」
  // 提示抢先于「改动被丢弃」弹窗（后端在停止响应前就发出了丢弃帧）
  const DISCARD_FRAME_GRACE_MS = 300

  let configTimeout: number | null = null
  let warningTimeout: number | null = null

  // keepSubscriptions=true 时保留订阅：丢弃帧先于停止响应发出，但到达顺序不保证，
  // 保存流程要等完这一回合才能判断该不该提示「已保存」。
  const clearSession = (keepSubscriptions = false) => {
    if (!keepSubscriptions) {
      subscriptionIds.value.forEach(unsubscribe)
      subscriptionIds.value = []
    }
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

  const stopSession = (
    keepOnFailure = false,
    keepSubscriptions = false,
    action: NativeConfigStopAction = 'close'
  ): Promise<boolean> => {
    // 页面退出须等启动请求交回任务 ID，再停止并归档，不能遗留迟到的会话。
    if (startingPromise) {
      return startingPromise.then(() => stopSession(keepOnFailure, keepSubscriptions, action))
    }
    if (stoppingPromise) {
      keepFailedSession ||= keepOnFailure
      keepDiscardFrames ||= keepSubscriptions
      return stoppingPromise
    }
    const currentTaskId = taskId.value
    if (!currentTaskId) {
      clearSession(keepDiscardFrames)
      return Promise.resolve(true)
    }
    keepFailedSession = keepOnFailure
    keepDiscardFrames = keepSubscriptions
    stopping.value = true
    stoppingPromise = Promise.resolve().then(async () => {
      try {
        const response = await stopNativeConfig(currentTaskId, action)
        if (response.code !== 200) {
          throw new Error(response.message || t(keys.stopFailed))
        }
        clearSession(keepDiscardFrames)
        return true
      } catch (e) {
        logger.error(e instanceof Error ? e.message : String(e))
        // 任一等待者要求保留失败会话，就保留现场供重试，不能由另一调用者清空。
        if (!keepFailedSession) clearSession()
        return false
      } finally {
        stopping.value = false
        stoppingPromise = null
        if (taskId.value) keepDiscardFrames = false
      }
    })
    return stoppingPromise
  }

  const startSession = (
    startTaskId: string,
    viewOnly = false,
    startOptions: Pick<TaskCreateIn, 'instanceIdx'> = {}
  ): Promise<boolean> => {
    // 同一页面只持有一条会话；收尾帧窗口结束前也不覆盖旧订阅。
    if (startingPromise || taskId.value || stoppingPromise || savingPromise) {
      return Promise.resolve(false)
    }
    configLoading.value = true
    currentSessionViewOnly.value = viewOnly
    startingPromise = Promise.resolve().then(async () => {
      try {
        discardedReason = null
        keepDiscardFrames = false
        const response = await requestTaskStart(
          {
            ...startOptions,
            taskId: startTaskId,
            mode: TaskCreateIn.mode.SCRIPT_CONFIG,
            viewOnly,
          },
          { source: 'script_config' }
        )
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
          subscribe({ id: response.taskId, type: WS_TASK_CONFIG_DISCARDED }, wsMessage => {
            discardedReason = wsMessage.data.reason
            showConfigDiscardWarning(t, wsMessage.data.reason)
          }),
          subscribe({ id: response.taskId, type: WS_TASK_COMPLETED }, () => {
            // 完成帧可能先于 HTTP 响应到达，保存中的丢弃订阅仍要留到宽限期结束。
            clearSession(keepDiscardFrames)
          }),
        ]
        message.success(viewOnly ? t(keys.viewOpened) : t(keys.opened))
        if (viewOnly) {
          // 查看会话：超时静默关闭，不提示也不触发「保存」
          configTimeout = window.setTimeout(
            () => void stopSession(false, false, 'timeout'),
            SESSION_TIMEOUT_MS
          )
          return true
        }
        warningTimeout = window.setTimeout(() => {
          message.warning(t(keys.timeoutWarn))
        }, SESSION_TIMEOUT_MS - SESSION_WARNING_ADVANCE_MS)
        configTimeout = window.setTimeout(() => void saveSession('timeout'), SESSION_TIMEOUT_MS)
        return true
      } catch (e) {
        logger.error(e instanceof Error ? e.message : String(e))
        message.error(
          e instanceof Error
            ? e.message
            : t(viewOnly ? (keys.viewStartFailed ?? keys.startFailed) : keys.startFailed)
        )
        clearSession()
        return false
      } finally {
        configLoading.value = false
        startingPromise = null
      }
    })
    return startingPromise
  }

  const saveSession = (action: 'save' | 'timeout' = 'save'): Promise<void> => {
    if (savingPromise) return savingPromise
    if (!taskId.value) return Promise.resolve()
    if (currentSessionViewOnly.value) {
      // 查看会话只有关闭语义，不发送保存动作，也不提示已保存。
      return stopSession().then(() => {})
    }
    savingPromise = (async () => {
      if (!(await stopSession(true, true, action))) {
        message.error(t(keys.saveFailed))
        return
      }
      await new Promise(resolve => window.setTimeout(resolve, DISCARD_FRAME_GRACE_MS))
      // 改动已被丢弃时不再提示「已保存」——弹窗已经说明去向，两条提示互相矛盾。
      if (!discardedReason) message.success(t(keys.saved))
    })().finally(() => {
      keepDiscardFrames = false
      if (!taskId.value) clearSession()
      savingPromise = null
    })
    return savingPromise
  }

  const dispose = async () => {
    // 页面按「先停会话，再归档」调用；必须等后端完成收尾。
    await stopSession()
  }

  return {
    configLoading,
    taskId,
    showConfigMask,
    showViewMask,
    currentSessionViewOnly,
    stopping,
    startSession,
    saveSession,
    stopSession,
    dispose,
  }
}
