import { onScopeDispose, reactive } from 'vue'
import { useI18n } from 'vue-i18n'
import { Modal, message } from 'ant-design-vue'
import { Service, TaskCreateIn } from '@/api'
import { useWebSocket } from '@/composables/useWebSocket'
import { realtimeSnapshotApi } from '@/services/realtimeSnapshotApi'
import {
  WS_TASK_COMPLETED,
  WS_TASK_LOG_UPDATED,
  WS_TASK_NOTICE,
  type WSTaskLogUpdatedData,
  type WSTaskNoticeData,
} from '@/services/websocket/types'

/** 单次更新日志的缓冲上限 */
const UPDATE_LOG_MAX_CHARS = 200_000
/**
 * 一行新日志都没有，多久就向后端对一次账。整文件成员的拷贝与校验可以在一行都不出的
 * 情况下跑十几分钟，所以到点不等于卡住：任务还在运行列表里就重新计时接着等，确实不在
 * 才算结束。一轮更新的时限由后端到点自终止。
 */
const MAAEND_UPDATE_IDLE_MS = 15 * 60 * 1000

/**
 * MaaEnd 脚本页「检查更新」手动入口。
 *
 * 更新对象是脚本级的终末地 PC 客户端（`Game.Path`），所以直接把脚本 uid 当任务 ID 提交
 * `Update` 模式，后端落到该脚本的客户端目录。`getScriptId` 传取值器而不是快照值。
 */
export function useMaaEndUpdate(getScriptId: () => string) {
  const { t } = useI18n()
  const logger = window.electronAPI.getLogger('MaaEnd脚本更新')
  const { subscribe, unsubscribe } = useWebSocket()

  const updateModal = reactive({
    open: false,
    running: false,
    starting: false,
    /** 这一轮已经出结论（完成、报错或卡住）：日志要留在弹窗里给用户看 */
    done: false,
    log: '',
  })

  const updateSession = reactive({
    subscriptionIds: [] as string[],
    taskId: '',
    timeout: null as number | null,
    /** 订阅后补的那几次对账，任务正常收尾时一并撤掉 */
    retries: [] as number[],
  })

  // 任务日志增量协议：append 为假 → 整体替换并记 seq；append 为真且 seq 连续 → 追加；
  // 否则视为失步（订阅登记前已经错过首条整体替换、或漏了消息）：丢弃本条，拉一次运行
  // 快照用它的 log/logSeq 重建，重建期间到达的增量一并丢弃。
  let logSeq: number | null = null
  let logResyncing = false
  // 连续拉失败的对账次数，拉到一次成功就归零
  let resyncRetries = 0
  // 报错后任务随即也会走完成事件，用它抑制紧随其后的「任务已结束」成功提示
  let errored = false
  // 关弹窗中止的那一轮同理：停止接口返回前完成事件就已经发出去了，不抑制就会在
  // 用户自己按了「仍要关闭」之后再补一句成功提示
  let aborted = false
  // 组件已销毁：此后不得再登记订阅、起定时器或弹提示。启动请求在途时用户离开页面
  // 会走到这里，那时 updateSession.taskId 还是空的，光靠 stopSession 拦不住
  let disposed = false
  // 会话代次：每次清会话自增。在途的异步结果（快照）据此判断自己是不是已经过期
  let sessionGeneration = 0
  // 日志变更次数：快照属于「发起请求那一刻」的世界，回来后日志已被更新就别再覆盖
  let logRevision = 0

  const clearSession = () => {
    sessionGeneration += 1
    // 对账预算跟着会话走：上一轮把快照接口连挂三次，不该让后面每一轮都失去失步恢复
    resyncRetries = 0
    for (const subscriptionId of updateSession.subscriptionIds) {
      unsubscribe(subscriptionId)
    }
    updateSession.subscriptionIds = []
    updateSession.taskId = ''
    if (updateSession.timeout) {
      window.clearTimeout(updateSession.timeout)
      updateSession.timeout = null
    }
    for (const retry of updateSession.retries) {
      window.clearTimeout(retry)
    }
    updateSession.retries = []
  }

  /**
   * 请求后端停止本轮更新。
   *
   * `clearOnFailure` 默认关：停不下来时后端还在写游戏目录，把会话清掉用户就再没有重试的
   * 入口了（taskId 与订阅都没了）。只有调用方确认这一轮已经不需要收口——任务已结束、
   * 或组件已销毁——才传 true 把会话收干净。
   */
  const stopSession = async (clearOnFailure = false): Promise<boolean> => {
    const taskId = updateSession.taskId
    if (!taskId) {
      clearSession()
      return true
    }
    try {
      const response = await Service.stopTaskApiDispatchStopPost({ taskId })
      if (response.code !== 200) {
        throw new Error(response.message || t('edit.endfieldUpdateStopFailed'))
      }
    } catch (e) {
      logger.error(e instanceof Error ? e.message : String(e))
      if (clearOnFailure) clearSession()
      return false
    }
    clearSession()
    return true
  }

  /** 重新起「这么久没新日志就去对一次账」的表；每来一条新日志都续一次 */
  const armIdleTimer = () => {
    if (updateSession.timeout) {
      window.clearTimeout(updateSession.timeout)
    }
    updateSession.timeout = window.setTimeout(() => void settleOnIdle(), MAAEND_UPDATE_IDLE_MS)
  }

  /**
   * 排一次 5 秒后的补对账。
   *
   * 上限 3 次：快照接口一直失败时不能变成每 5 秒一次的无界轮询，15 分钟那一表的对账仍在等它。
   */
  const scheduleResync = () => {
    if (resyncRetries >= 3) return
    resyncRetries += 1
    updateSession.retries.push(
      window.setTimeout(() => {
        if (updateModal.running && updateSession.taskId) void settleIfFinished()
      }, 5000)
    )
  }

  /** 重扫一次日志快照；返回这个任务是否还在运行列表里 */
  const resyncLog = async (): Promise<boolean> => {
    if (logResyncing || !updateSession.taskId) return true
    // 快照属于「发起请求那一刻」的世界：把当时的口径先记下，回来对不上就整条丢弃，
    // 否则旧快照会把新一轮判成「已结束」、或把已经收到的最终结论覆盖回去
    const generation = sessionGeneration
    const taskId = updateSession.taskId
    const revision = logRevision
    logResyncing = true
    try {
      const snapshot = await realtimeSnapshotApi.getRuntimeTasks()
      if (generation !== sessionGeneration || taskId !== updateSession.taskId) {
        return true
      }
      const item = (snapshot.tasks ?? []).find(task => task.taskId === taskId)
      resyncRetries = 0
      if (!item) return false
      // 期间已有更新的日志就不拿这份旧的覆盖
      if (revision === logRevision) {
        updateModal.log = item.log ?? ''
        logSeq = item.logSeq ?? null
      }
    } catch (e) {
      logger.warn(`重建终末地更新日志失败: ${e instanceof Error ? e.message : String(e)}`)
      // 请求失败不代表任务已经结束：任务可能正在跑，只是这一眼的快照没拿到
      scheduleResync()
    } finally {
      logResyncing = false
    }
    return true
  }

  /**
   * 订阅之后与日志失步时对一次账：任务可能已经不在运行列表里了。
   * WebSocket 不重放历史事件，派发与订阅之间就结束的那一轮只能靠补对账收口。
   * 返回这个任务是否还需要继续等下去。
   */
  const settleIfFinished = async (): Promise<boolean> => {
    if (await resyncLog()) return true
    updateModal.running = false
    updateModal.done = true
    updateModal.log ||= t('edit.endfieldUpdateAlreadyFinished')
    clearSession()
    return false
  }

  /**
   * 空闲到点的对账：还在运行列表里就重新起表接着等。安静十几分钟是整文件拷贝与校验的
   * 正常形状，拿一次没查到的状态去中止一轮推进中的更新，代价比多等一轮大。
   */
  const settleOnIdle = async () => {
    if ((await settleIfFinished()) && updateModal.running) armIdleTimer()
  }

  const applyLog = (data: { log: string; seq?: number; append?: boolean }) => {
    if (!data.append) {
      updateModal.log = data.log
      logSeq = data.seq ?? null
    } else if (logSeq !== null && data.seq === logSeq + 1) {
      updateModal.log += data.log
      logSeq = data.seq
    } else {
      // 序号对不上（丢包或重连）就整段重扫，期间不追加半截行。表必须先续上：重扫一旦
      // 失败，这一段就没有下一次对账了
      logSeq = null
      armIdleTimer()
      void settleIfFinished()
      return
    }
    logRevision += 1
    armIdleTimer()
    if (updateModal.log.length > UPDATE_LOG_MAX_CHARS) {
      updateModal.log = updateModal.log.slice(-UPDATE_LOG_MAX_CHARS)
    }
  }

  const handleCheckUpdate = () => {
    if (updateModal.running || !getScriptId()) return
    updateModal.log = ''
    updateModal.done = false
    logSeq = null
    updateModal.open = true
  }

  const startUpdate = async () => {
    const scriptId = getScriptId()
    if (!scriptId) return
    updateModal.starting = true
    try {
      const response = await Service.addTaskApiDispatchStartPost({
        taskId: scriptId,
        mode: TaskCreateIn.mode.UPDATE,
      })
      if (response.code !== 200 || !response.taskId) {
        throw new Error(response.message || t('edit.endfieldUpdateStartFailed'))
      }
      updateModal.running = true
      updateModal.done = false
      updateSession.taskId = response.taskId
      if (disposed || !updateModal.open) {
        // 请求在途的那几百毫秒里用户把窗关了、或直接离开了这个页面：让它隐形跑起来，等于
        // 一整轮「看不见进度、配置又被锁住、按钮还点不动」，页面已经销毁时连进度都没了
        // 只有组件已经没了才把会话收干净：停不下来的话这一轮还在写游戏目录，页面还在就该
        // 留着 taskId，让他离开这一页时那条 stopSession 还能追上这一轮
        const stopped = await stopSession(disposed)
        updateModal.running = false
        if (!disposed && !stopped) message.error(t('edit.endfieldUpdateStopFailed'))
        return
      }
      errored = false
      aborted = false
      updateSession.subscriptionIds = [
        subscribe({ id: response.taskId, type: WS_TASK_LOG_UPDATED }, wsMessage => {
          applyLog(
            wsMessage.data as unknown as WSTaskLogUpdatedData & { seq?: number; append?: boolean }
          )
        }),
        subscribe({ id: response.taskId, type: WS_TASK_NOTICE }, wsMessage => {
          const data = wsMessage.data as unknown as WSTaskNoticeData
          if (data.level === 'error') {
            errored = true
            message.error(t('edit.endfieldUpdateFailed', { p0: data.message }))
            updateModal.running = false
            updateModal.done = true
            // 弹窗留着：具体原因就在里面那几行日志里。任务已经报错收尾，会话可以清干净
            void stopSession(true)
          }
        }),
        subscribe({ id: response.taskId, type: WS_TASK_COMPLETED }, () => {
          if (!errored && !aborted) {
            message.success(t('edit.endfieldUpdateTask'))
          }
          updateModal.running = false
          updateModal.done = true
          // 不关弹窗：后端为这次检查专门推的结论（「已是最新版本 x」/「已更新至 x」）
          // 就在日志里，一关掉用户只剩一句「已结束」。任务已结束，会话可以清干净
          void stopSession(true)
        }),
      ]
      armIdleTimer()
      // 订阅登记完先对一次账：派发与订阅之间就结束的那一轮，事件已经过去了。任务从运行
      // 表里摘掉发生在完成之后，这一刻仍可能查得到它，所以过几秒再确认两次
      void settleIfFinished()
      for (const delay of [2000, 5000]) {
        updateSession.retries.push(
          window.setTimeout(() => {
            if (updateModal.running) {
              void settleIfFinished()
            }
          }, delay)
        )
      }
    } catch (e) {
      logger.error(e instanceof Error ? e.message : String(e))
      // 页面已经销毁就别再往别处弹提示：那条错误属于一个用户已经离开的页面
      if (!disposed) {
        message.error(e instanceof Error ? e.message : t('edit.endfieldUpdateStartFailed'))
      }
    } finally {
      updateModal.starting = false
    }
  }

  const closeAndStop = async () => {
    const running = updateModal.running
    // 先置位：停止接口要等任务真收尾才返回，而完成事件在那之前就已经发出去了
    aborted = true
    const stopped = running ? await stopSession() : true
    if (running && !stopped) {
      // 后端没答应停止，就还在写游戏目录。这时把弹窗收起来、会话清掉，用户就只剩一句
      // 三秒即散的提示，连再按一次「仍要关闭」的入口都没有了——保持打开让他能重试
      message.error(t('edit.endfieldUpdateStopFailed'))
      return
    }
    updateModal.running = false
    updateModal.done = false
    updateModal.open = false
  }

  const handleUpdateModalCancel = () => {
    // 中止会白下这一轮已下载的部分（下一轮能续传，但这一轮到此为止），先问一句
    if (updateModal.running) {
      Modal.confirm({
        title: t('edit.endfieldUpdateAbortTitle'),
        content: t('edit.endfieldUpdateCloseConfirm'),
        okText: t('edit.endfieldUpdateAbortConfirm'),
        cancelText: t('edit.cancel'),
        onOk: closeAndStop,
      })
      return
    }
    closeAndStop()
  }

  onScopeDispose(() => {
    // 组件没了，任何提示都无处可落；会话也必须收干净，否则订阅与定时器会一直挂着。
    // 置位要在停之前：启动请求在途时 taskId 还是空的，晚置位会让回来的响应又登记一批
    disposed = true
    aborted = true
    void stopSession(true)
  })

  return { updateModal, handleCheckUpdate, startUpdate, handleUpdateModalCancel }
}
