// 原生设置会话通用实现（原生 GUI 配置 / 只读查看）
import { h, ref } from 'vue'
import { Button, message, notification } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'
import { Service, TaskOutcome } from '@/api'
import { TaskCreateIn } from '@/api/models/TaskCreateIn'
import { useWebSocket } from '@/composables/useWebSocket'
import { showConfigDiscardWarning } from '@/utils/configSessionDiscard'
import { taskOutcomeNoticeKind } from '@/utils/taskOutcomeNotice'
import {
  WS_TASK_COMPLETED,
  WS_TASK_CONFIG_DISCARDED,
  WS_TASK_NOTICE,
} from '@/services/websocket/types'

/**
 * 原生设置会话状态机（MAA / ok-ww / MaaEnd / BetterGI / OK-NTE / ZZZ-OD 共用）。
 * 查看（view_only）与编辑走同一套状态与终态语义，只有「打开后是否显示保存入口」
 * 与超时后的动作不同。
 */
export type NativeSessionState =
  | 'idle'
  | 'starting'
  | 'open_edit'
  | 'open_view'
  | 'stopping'
  | 'confirming_result'
  | 'saved'
  | 'discarded'
  | 'failed'
  | 'unknown'

/**
 * 打开原生 GUI 并遮罩等待，结束时以任务终态（TaskOutcome）收尾。各专项差异只有
 * 日志名与 i18n 词条，由 options 注入，页面直接解构通用状态即可（专项需要脚本
 * 前缀命名时用薄包装 re-export，见各 use*GuiSession）。
 *
 * 会话负责进程生命周期（WebSocket 订阅、遮罩、30 分钟超时自动保存、卸载清理）；
 * 配置的下发与回写由 ScriptConfig 任务完成。
 *
 * 终态判定一律以 TaskOutcome.outcome 为准：停止接口 HTTP 200 只代表请求被受理，
 * 改动被丢弃（discarded）或任务出错（failed）时绝不提示「已保存」。拿不到终态
 * （响应异常、任务仍在收尾）时进入 unknown，保留会话现场并给出「查询当前状态」，
 * 而不是清掉会话让用户以为保存成功。
 */
export function useNativeGuiSession(options: {
  loggerName: string
  keys: {
    /** 停止请求本身失败时的日志文案（用户可见的兜底是 unknown 提示） */
    stopFailed: string
    startFailed: string
    /** WS 错误通知的正文词条（{p0} 为后端错误消息） */
    setupFailed: string
    opened: string
    viewOpened: string
    timeoutWarn: string
    saved: string
  }
}) {
  const { t } = useI18n()
  const { subscribe, unsubscribe } = useWebSocket()
  const keys = options.keys

  const logger = window.electronAPI.getLogger(options.loggerName)

  const state = ref<NativeSessionState>('idle')
  const outcome = ref<TaskOutcome | null>(null)
  const viewOnly = ref(false)
  const configLoading = ref(false)
  const subscriptionIds = ref<string[]>([])
  const taskId = ref<string | null>(null)
  const showConfigMask = ref(false)
  const showViewMask = ref(false)
  const stopping = ref(false)
  let stoppingPromise: Promise<boolean> | null = null
  let querying = false
  // 本次会话的改动是否已被后端丢弃（原因见后端 WSTaskConfigDiscardedData）
  let discardedReason: string | null = null
  let discardWarningShown = false
  let unknownNoticeShown = false
  // 已应用过的终态（taskId|finishedAt）：断线补发的重复终态帧只应用一次
  let appliedStamp = ''

  // 原生设置会话超时自动保存的时长与提前提醒的提前量（避免无预告直接中断会话）
  const SESSION_TIMEOUT_MS = 30 * 60 * 1000
  const SESSION_WARNING_ADVANCE_MS = 30 * 1000
  // 停止响应与 WebSocket 消息跨连接到达，留一个回合接收最终结果。
  const DISCARD_FRAME_GRACE_MS = 300
  // 完成帧先于终态落库发出，查询要给它留出重试窗口，否则会把「刚结束」误判成未知。
  const OUTCOME_QUERY_ATTEMPTS = 5
  const OUTCOME_QUERY_RETRY_MS = 300
  const UNKNOWN_NOTICE_KEY = 'native-config-session-outcome-unknown'

  let configTimeout: number | null = null
  let warningTimeout: number | null = null

  const wait = (ms: number) => new Promise(resolve => window.setTimeout(resolve, ms))

  const closeUnknownNotice = () => {
    if (!unknownNoticeShown) return
    unknownNoticeShown = false
    notification.close(UNKNOWN_NOTICE_KEY)
  }

  // 清空会话现场：订阅、遮罩、自动保存定时器与 taskId。
  const resetSession = () => {
    subscriptionIds.value.forEach(unsubscribe)
    subscriptionIds.value = []
    taskId.value = null
    showConfigMask.value = false
    showViewMask.value = false
    stopping.value = false
    if (configTimeout) {
      window.clearTimeout(configTimeout)
      configTimeout = null
    }
    if (warningTimeout) {
      window.clearTimeout(warningTimeout)
      warningTimeout = null
    }
  }

  // 完成帧与保存流程都会走到会话收尾，提示只弹一次
  const showDiscardWarning = (reason: string) => {
    if (discardWarningShown) return
    discardWarningShown = true
    showConfigDiscardWarning(t, reason)
  }

  // 结果无法确认：保留 taskId 与订阅，给出可执行的下一步（查询当前状态）。
  const enterUnknown = () => {
    state.value = 'unknown'
    if (unknownNoticeShown) return
    unknownNoticeShown = true
    notification.warning({
      key: UNKNOWN_NOTICE_KEY,
      message: t('resultUnknown.title'),
      description: t('resultUnknown.description'),
      duration: 0,
      btn: () =>
        h(Button, { size: 'small', type: 'primary', onClick: () => void querySession() }, () =>
          t('resultUnknown.query')
        ),
    })
  }

  // 按 taskId 取权威终态；任务刚结束但终态还没落库时重试几次，仍取不到返回 null。
  const fetchOutcome = async (id: string): Promise<TaskOutcome | null> => {
    for (let attempt = 0; attempt < OUTCOME_QUERY_ATTEMPTS; attempt += 1) {
      try {
        const status = await Service.getTaskStatusApiDispatchTaskTaskIdGet(id)
        if (status?.taskOutcome) return status.taskOutcome
      } catch (e) {
        logger.error(e instanceof Error ? e.message : String(e))
      }
      await wait(OUTCOME_QUERY_RETRY_MS)
    }
    return null
  }

  /**
   * 按终态收尾：只有 saved 才提示「已保存」，discarded 弹丢弃说明，failed 提示失败，
   * completed_without_write（只读查看、未回写）与 cancelled 静默收尾。
   */
  const applyOutcome = (
    result: TaskOutcome,
    announceSaved: boolean
  ): ReturnType<typeof taskOutcomeNoticeKind> => {
    // 断线补发会对同一终态重放：同一 taskId + finishedAt 只应用一次
    const stamp = `${result.taskId}|${result.finishedAt}`
    if (appliedStamp === stamp) return taskOutcomeNoticeKind(result)
    appliedStamp = stamp

    outcome.value = result
    closeUnknownNotice()
    // 分类统一走 utils/taskOutcomeNotice，各入口不再各写一套结果判断
    const kind = taskOutcomeNoticeKind(result)

    if (kind === 'unknown') {
      enterUnknown()
      return kind
    }

    if (kind === 'saved') {
      resetSession()
      state.value = 'saved'
      if (announceSaved) message.success(t(keys.saved))
      return kind
    }

    if (kind === 'discarded') {
      const reason = result.reason || discardedReason || 'unknown'
      resetSession()
      state.value = 'discarded'
      showDiscardWarning(reason)
      return kind
    }

    if (kind === 'failed') {
      resetSession()
      state.value = 'failed'
      message.error(t('taskOutcome.failed'))
      return kind
    }

    if (kind === 'without_write') {
      const wasViewOnly = viewOnly.value
      resetSession()
      state.value = 'discarded'
      // 查看会话本来就不回写，静默收尾；编辑会话没写盘则明确告知，避免误以为已保存
      if (!wasViewOnly) message.info(t('taskOutcome.completedWithoutWrite'))
      return kind
    }

    // cancelled（用户主动停止）/ completed（非配置任务）：静默收尾，绝不提示已保存
    resetSession()
    state.value = 'discarded'
    return kind
  }

  // 启动响应返回后主动对账一次，覆盖任务在订阅建立前已经结束的竞态。
  const reconcileStartedTask = async (id: string) => {
    try {
      const result = await fetchOutcome(id)
      if (result && taskId.value === id) applyOutcome(result, false)
    } catch (e) {
      // WS 仍是实时通道；启动后的单次对账失败不提前制造 unknown。
      logger.warn(`启动后查询配置会话终态失败: ${e instanceof Error ? e.message : String(e)}`)
    }
  }

  // 原生 GUI 自己结束（用户在其中保存/关闭）时，任务终态只能查，不能凭帧猜。
  const settleOnTaskEnd = async () => {
    const id = taskId.value
    if (!id) return
    if (state.value === 'stopping' || state.value === 'confirming_result') return
    state.value = 'confirming_result'
    stopping.value = true
    try {
      // 丢弃帧与完成帧分属两条链路，先等一个回合再取终态，避免漏掉丢弃原因
      await wait(DISCARD_FRAME_GRACE_MS)
      const result = await fetchOutcome(id)
      if (result) applyOutcome(result, false)
      else enterUnknown()
    } finally {
      stopping.value = false
    }
  }

  // 未知终态下用户点「查询当前状态」：查到即按终态收尾，查不到继续保持未知。
  const querySession = async (): Promise<void> => {
    if (querying) return
    const id = taskId.value
    if (!id) return
    querying = true
    state.value = 'confirming_result'
    stopping.value = true
    try {
      const result = await fetchOutcome(id)
      if (result) applyOutcome(result, true)
      else enterUnknown()
    } finally {
      querying = false
      stopping.value = false
    }
  }

  const runStop = async (announceSaved: boolean): Promise<boolean> => {
    const currentTaskId = taskId.value
    if (!currentTaskId) {
      resetSession()
      return true
    }
    state.value = 'stopping'
    stopping.value = true
    try {
      const response = await Service.stopTaskApiDispatchStopPost({ taskId: currentTaskId })
      if (response.code !== 200) {
        // HTTP 非 200：请求没被受理，不能清会话——现场留着才能重试或查询
        logger.error(`${t(keys.stopFailed)}: code=${response.code} ${response.message ?? ''}`)
        enterUnknown()
        return false
      }
      // 丢弃帧先于停止响应发出，但到达顺序不保证，等完这一回合再判该不该提示「已保存」
      await wait(DISCARD_FRAME_GRACE_MS)
      const kind = applyOutcome(response, announceSaved)
      return kind !== 'unknown'
    } catch (e) {
      logger.error(e instanceof Error ? e.message : String(e))
      enterUnknown()
      return false
    } finally {
      stopping.value = false
    }
  }

  const stopSession = (announceSaved = false): Promise<boolean> => {
    if (stoppingPromise) return stoppingPromise
    stoppingPromise = runStop(announceSaved).finally(() => {
      stoppingPromise = null
    })
    return stoppingPromise
  }

  const startSession = async (
    startTaskId: string,
    isViewOnly = false,
    instanceIdx?: number | null
  ): Promise<boolean> => {
    try {
      configLoading.value = true
      resetSession()
      closeUnknownNotice()
      outcome.value = null
      discardedReason = null
      discardWarningShown = false
      appliedStamp = ''
      viewOnly.value = isViewOnly
      state.value = 'starting'
      const response = await Service.addTaskApiDispatchStartPost({
        taskId: startTaskId,
        mode: TaskCreateIn.mode.SCRIPT_CONFIG,
        viewOnly: isViewOnly,
        instanceIdx: instanceIdx ?? undefined,
      })
      if (response.code !== 200 || !response.taskId) {
        throw new Error(response.message || t(keys.startFailed))
      }

      showConfigMask.value = !isViewOnly
      showViewMask.value = isViewOnly
      taskId.value = response.taskId
      state.value = isViewOnly ? 'open_view' : 'open_edit'
      subscriptionIds.value = [
        subscribe({ id: response.taskId, type: WS_TASK_NOTICE }, wsMessage => {
          if (wsMessage.data.level !== 'error') return

          message.error(t(keys.setupFailed, { p0: wsMessage.data.message }))
          void stopSession()
        }),
        subscribe({ id: response.taskId, type: WS_TASK_CONFIG_DISCARDED }, wsMessage => {
          discardedReason = wsMessage.data.reason
          logger.info(`收到配置会话丢弃通知: reason=${discardedReason}`)
          // 未知终态期间拿到丢弃结论，立即改判，别让用户继续等一个永远不会来的结果
          if (state.value === 'unknown') {
            applyOutcome(
              {
                taskId: taskId.value ?? '',
                outcome: TaskOutcome.outcome.DISCARDED,
                reason: discardedReason,
              },
              false
            )
          }
        }),
        subscribe({ id: response.taskId, type: WS_TASK_COMPLETED }, () => {
          void settleOnTaskEnd()
        }),
      ]
      void reconcileStartedTask(response.taskId)
      message.success(isViewOnly ? t(keys.viewOpened) : t(keys.opened))
      if (isViewOnly) {
        // 查看会话：超时静默关闭，不提示也不触发「保存」
        configTimeout = window.setTimeout(() => void stopSession(), SESSION_TIMEOUT_MS)
        return true
      }
      warningTimeout = window.setTimeout(() => {
        message.warning(t(keys.timeoutWarn))
      }, SESSION_TIMEOUT_MS - SESSION_WARNING_ADVANCE_MS)
      configTimeout = window.setTimeout(() => void saveSession(), SESSION_TIMEOUT_MS)
      return true
    } catch (e) {
      logger.error(e instanceof Error ? e.message : String(e))
      message.error(e instanceof Error ? e.message : t(keys.startFailed))
      resetSession()
      state.value = 'idle'
      return false
    } finally {
      configLoading.value = false
    }
  }

  const saveSession = async (): Promise<void> => {
    if (!taskId.value) return
    // 保存流程按「已保存」口径提示；丢/失败/未知一律由终态判定接管，绝不谎报成功
    await stopSession(true)
  }

  // 页面卸载：静默停止会话（保存与否仍以终态为准）
  const dispose = async (): Promise<boolean> => {
    return await stopSession()
  }

  return {
    state,
    outcome,
    viewOnly,
    configLoading,
    taskId,
    showConfigMask,
    showViewMask,
    stopping,
    startSession,
    saveSession,
    stopSession,
    querySession,
    dispose,
  }
}
