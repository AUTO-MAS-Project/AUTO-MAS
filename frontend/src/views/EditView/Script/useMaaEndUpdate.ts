import { onUnmounted, reactive } from 'vue'
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

  const clearSession = () => {
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

  const stopSession = async (): Promise<boolean> => {
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
      return true
    } catch (e) {
      logger.error(e instanceof Error ? e.message : String(e))
      return false
    } finally {
      clearSession()
    }
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
    logResyncing = true
    try {
      const snapshot = await realtimeSnapshotApi.getRuntimeTasks()
      const item = (snapshot.tasks ?? []).find(task => task.taskId === updateSession.taskId)
      resyncRetries = 0
      if (!item) return false
      updateModal.log = item.log ?? ''
      logSeq = item.logSeq ?? null
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
      if (!updateModal.open) {
        // 请求在途的那几百毫秒里用户已经把窗关了：让它隐形跑起来，等于一整轮
        // 「看不见进度、配置又被锁住、按钮还点不动」
        await stopSession()
        updateModal.running = false
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
            // 弹窗留着：具体原因就在里面那几行日志里
            void stopSession()
          }
        }),
        subscribe({ id: response.taskId, type: WS_TASK_COMPLETED }, () => {
          if (!errored && !aborted) {
            message.success(t('edit.endfieldUpdateTask'))
          }
          updateModal.running = false
          updateModal.done = true
          // 不关弹窗：后端为这次检查专门推的结论（「已是最新版本 x」/「已更新至 x」）
          // 就在日志里，一关掉用户只剩一句「已结束」
          void stopSession()
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
      message.error(e instanceof Error ? e.message : t('edit.endfieldUpdateStartFailed'))
    } finally {
      updateModal.starting = false
    }
  }

  const closeAndStop = async () => {
    const running = updateModal.running
    // 先置位：停止接口要等任务真收尾才返回，而完成事件在那之前就已经发出去了
    aborted = true
    const stopped = running ? await stopSession() : true
    updateModal.running = false
    updateModal.done = false
    updateModal.open = false
    // 后端没答应停止，就还在写游戏目录；只把窗口收起来会让人以为已经中止
    if (running && !stopped) message.error(t('edit.endfieldUpdateStopFailed'))
  }

  const handleUpdateModalCancel = () => {
    // 每轮开头都会清掉暂存目录，跨轮不复用：中止等于已下载的增量白下，先问一句
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

  onUnmounted(() => {
    void stopSession()
  })

  return { updateModal, handleCheckUpdate, startUpdate, handleUpdateModalCancel }
}
