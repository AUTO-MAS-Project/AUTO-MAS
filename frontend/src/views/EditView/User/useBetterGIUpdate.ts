import { onUnmounted, reactive } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
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
 * 卡住的判定：这么久一行新日志都没有就收工。
 *
 * 这里刻意不是「整轮时限」——多 GB 的增量在慢网下跑上一两个小时也算正常，按总时长掐表
 * 只会把正在推进的更新拦腰掐断；反过来，半天不出一行字才是真出了问题。
 */
const UPDATE_IDLE_MS = 5 * 60 * 1000

/**
 * BetterGI 用户页「检查更新」手动入口。
 *
 * 游戏客户端路径是**用户级**配置（`Switch.GamePath`，留空跟随 BetterGI 全局），
 * 所以入口挂在用户页：目标用户即当前正在编辑的用户，提交 `Update` 模式任务时
 * 直接把它的 uid 当任务 ID，由后端落到该用户的客户端。
 *
 * Args:
 *   getUserId: 当前编辑用户的 uid 取值器。新建用户时 uid 是保存后才补上的，
 *     所以这里取函数而不是快照值。
 */
export function useBetterGIUpdate(getUserId: () => string) {
  const { t } = useI18n()
  const logger = window.electronAPI.getLogger('BetterGI用户更新')
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
  })

  // 任务日志增量协议：append 为假 → 整体替换并记 seq；append 为真且 seq 连续 → 追加；
  // 否则视为失步（订阅登记前已经错过首条整体替换、或漏了消息）：丢弃本条，拉一次运行
  // 快照用它的 log/logSeq 重建，重建期间到达的增量一并丢弃。
  let logSeq: number | null = null
  let logResyncing = false
  // 报错后任务随即也会走完成事件，用它抑制紧随其后的「任务已结束」成功提示
  let errored = false

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
        throw new Error(response.message || t('edit.bettergiUpdateStopFailed'))
      }
      return true
    } catch (e) {
      logger.error(e instanceof Error ? e.message : String(e))
      return false
    } finally {
      clearSession()
    }
  }

  /** 重新起「多久没进展就算卡住」的表；每来一条新日志都续一次 */
  const armIdleTimer = () => {
    if (updateSession.timeout) {
      window.clearTimeout(updateSession.timeout)
    }
    updateSession.timeout = window.setTimeout(() => {
      message.error(t('edit.bettergiUpdateTimed'))
      // 状态一定要落回不运行，否则弹窗会一直停在「进行中」出不来
      updateModal.running = false
      updateModal.done = true
      void stopSession()
    }, UPDATE_IDLE_MS)
  }

  const resyncLog = async () => {
    if (logResyncing || !updateSession.taskId) return
    logResyncing = true
    try {
      const snapshot = await realtimeSnapshotApi.getRuntimeTasks()
      const item = (snapshot.tasks ?? []).find(task => task.taskId === updateSession.taskId)
      if (!item) return
      updateModal.log = item.log ?? ''
      logSeq = item.logSeq ?? null
    } catch (e) {
      logger.warn(`重建原神更新日志失败: ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      logResyncing = false
    }
  }

  const applyLog = (data: { log: string; seq?: number; append?: boolean }) => {
    if (!data.append) {
      updateModal.log = data.log
      logSeq = data.seq ?? null
    } else if (logSeq !== null && data.seq === logSeq + 1) {
      updateModal.log += data.log
      logSeq = data.seq
    } else {
      logSeq = null
      void resyncLog()
      return
    }
    armIdleTimer()
    if (updateModal.log.length > UPDATE_LOG_MAX_CHARS) {
      updateModal.log = updateModal.log.slice(-UPDATE_LOG_MAX_CHARS)
    }
  }

  const handleCheckUpdate = () => {
    if (updateModal.running || !getUserId()) return
    updateModal.log = ''
    updateModal.done = false
    logSeq = null
    updateModal.open = true
  }

  const startUpdate = async () => {
    const userId = getUserId()
    if (!userId) return
    updateModal.starting = true
    try {
      const response = await Service.addTaskApiDispatchStartPost({
        taskId: userId,
        mode: TaskCreateIn.mode.UPDATE,
      })
      if (response.code !== 200 || !response.taskId) {
        throw new Error(response.message || t('edit.bettergiUpdateStartFailed'))
      }
      updateModal.running = true
      updateModal.done = false
      updateSession.taskId = response.taskId
      errored = false
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
            message.error(t('edit.bettergiUpdateFailed', { p0: data.message }))
            updateModal.running = false
            updateModal.done = true
            // 弹窗留着：具体原因就在里面那几行日志里
            void stopSession()
          }
        }),
        subscribe({ id: response.taskId, type: WS_TASK_COMPLETED }, () => {
          if (!errored) {
            message.success(t('edit.bettergiUpdateTask'))
          }
          updateModal.running = false
          updateModal.done = true
          // 不关弹窗：后端为这次检查专门推的结论（「当前为最新版本（x）」/
          // 「更新完成 x -> y」）就在日志里，一关掉用户只剩一句「已结束」
          void stopSession()
        }),
      ]
      armIdleTimer()
    } catch (e) {
      logger.error(e instanceof Error ? e.message : String(e))
      message.error(e instanceof Error ? e.message : t('edit.bettergiUpdateStartFailed'))
    } finally {
      updateModal.starting = false
    }
  }

  const handleUpdateModalCancel = () => {
    if (updateModal.running) {
      void stopSession()
    }
    updateModal.running = false
    updateModal.done = false
    updateModal.open = false
  }

  onUnmounted(() => {
    void stopSession()
  })

  return { updateModal, handleCheckUpdate, startUpdate, handleUpdateModalCancel }
}
