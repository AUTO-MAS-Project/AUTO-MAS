import { type WSTaskPrefetchData, TaskTriggerReason } from '@/api'
import { applyTaskLogUpdate } from './taskLogBuffer'
import { projectTaskTree } from './taskTreeProjection'
import { computed, ref } from 'vue'
import { realtimeSnapshotApi, type TaskRuntimeSnapshotItem } from '@/services/realtimeSnapshotApi'
import { connectionState, onConnected } from '@/services/websocket/connection'
import { subscribe, unsubscribe } from '@/services/websocket/subscriptions'
import {
  WS_ID_TASK_MANAGER,
  WS_TASK_COMPLETED,
  WS_TASK_CREATED,
  WS_TASK_INFO_UPDATED,
  WS_TASK_LOG_UPDATED,
  WS_TASK_NOTICE,
  type WSTaskLogUpdatedData,
  type WSTaskNoticeData,
  type WSTaskCompletedData,
  type WSTaskCreatedData,
  type WSTaskMode,
  type WSTaskScriptIdentityData,
  type WSTaskScriptInfoData,
} from '@/services/websocket/types'

const logger = window.electronAPI.getLogger('任务运行状态')

const COMPLETED_STATE_RETENTION_MS = 5 * 60 * 1000
const COMPLETED_STATE_CLEANUP_INTERVAL_MS = 30 * 1000
// 快照请求期间有增量事件时隔一拍重取，避免高频增量下背靠背热请求；连续变动超过上限就放弃
// 本轮对账，此时状态本来就在由增量事件持续刷新
const SNAPSHOT_MUTATION_RETRY_DELAY_MS = 500
const SNAPSHOT_MUTATION_RETRY_LIMIT = 5
// 快照拉取失败后延时重试一次，避免状态陈旧到下次重连
const SNAPSHOT_FAILURE_RETRY_DELAY_MS = 3000

export interface TaskRuntimeState {
  taskId: string
  mode: WSTaskMode | null
  scriptId: string | null
  userId: string | null
  stopping: boolean
  trigger: TaskTriggerReason
  scripts: WSTaskScriptIdentityData[]
  taskInfo: WSTaskScriptInfoData[]
  /** 本轮日志的唯一缓冲与序号；标签页只绑定运行 UUID。 */
  log: string
  prefetch: WSTaskPrefetchData | null
  logSeq?: number
  logFirstLine?: number
  phase: 'created' | 'active' | 'completed'
  taskName: string | null
  taskType: string | null
  result: string | null
  outcome: WSTaskCompletedData['outcome'] | null
  error: string | null
  completedAt: number | null
}

export type TaskRuntimeEvent =
  | { type: 'created' | 'info' | 'completed'; state: TaskRuntimeState }
  | { type: 'snapshot'; states: TaskRuntimeState[]; activeTaskIds: ReadonlySet<string> }
  | { type: 'removed'; taskId: string }
  | { type: 'notice'; state: TaskRuntimeState; notice: WSTaskNoticeData }

type TaskRuntimeListener = (event: TaskRuntimeEvent) => void | Promise<void>

const taskStates = ref(new Map<string, TaskRuntimeState>())
const listeners = new Set<TaskRuntimeListener>()
const taskSubscriptionIds = new Map<string, string[]>()
const residentSubscriptionIds: string[] = []
const retainedTasks = new Set<string>()
const resyncingLogs = new Set<string>()

let bootstrapped = false
let disposeConnectedListener: (() => void) | null = null
let completedStateCleanupTimer: number | null = null
let snapshotRetryTimer: number | null = null
let snapshotGeneration = 0
let mutationSequence = 0

const cloneScripts = (scripts?: WSTaskScriptIdentityData[]) =>
  (scripts ?? []).map(script => ({ ...script }))

const setTaskState = (state: TaskRuntimeState): void => {
  const next = new Map(taskStates.value)
  next.set(state.taskId, state)
  taskStates.value = next
}

const emitRuntimeEvent = (event: TaskRuntimeEvent): void => {
  for (const listener of [...listeners]) {
    try {
      const result = listener(event)
      if (result instanceof Promise) {
        void result.catch(error => {
          logger.warn(
            `任务状态监听器异常: ${error instanceof Error ? error.message : String(error)}`
          )
        })
      }
    } catch (error) {
      logger.warn(`任务状态监听器异常: ${error instanceof Error ? error.message : String(error)}`)
    }
  }
}

const releaseTaskSubscriptions = (taskId: string): void => {
  for (const subscriptionId of taskSubscriptionIds.get(taskId) ?? []) {
    unsubscribe(subscriptionId)
  }
  taskSubscriptionIds.delete(taskId)
}

const createUnknownTaskState = (taskId: string): TaskRuntimeState => ({
  taskId,
  mode: null,
  scriptId: null,
  userId: null,
  stopping: false,
  trigger: TaskTriggerReason.MANUAL,
  scripts: [],
  taskInfo: [],
  log: '',
  prefetch: null,
  phase: 'created',
  taskName: null,
  taskType: null,
  result: null,
  outcome: null,
  error: null,
  completedAt: null,
})

const handleLogUpdated = (taskId: string, data: WSTaskLogUpdatedData): void => {
  const state = taskStates.value.get(taskId)
  if (!state || state.phase === 'completed') return
  // 日志字段就地更新，不复制整张运行表，也不广播生命周期事件。
  if (applyTaskLogUpdate(state, data) !== 'resync' || resyncingLogs.has(taskId)) return
  resyncingLogs.add(taskId)
  void refreshTaskRuntimeSnapshot().finally(() => resyncingLogs.delete(taskId))
}

const ensureTaskSubscriptions = (taskId: string): void => {
  if (taskSubscriptionIds.has(taskId)) return
  taskSubscriptionIds.set(taskId, [
    subscribe({ id: taskId, type: WS_TASK_LOG_UPDATED }, message => {
      handleLogUpdated(taskId, message.data)
    }),
    subscribe({ id: taskId, type: WS_TASK_NOTICE }, message => {
      const state = taskStates.value.get(taskId)
      if (state) emitRuntimeEvent({ type: 'notice', state, notice: message.data })
    }),
    subscribe({ id: taskId, type: WS_TASK_INFO_UPDATED }, message => {
      mutationSequence++
      const current = taskStates.value.get(taskId)
      const state: TaskRuntimeState = {
        ...(current ?? createUnknownTaskState(taskId)),
        phase: 'active',
        mode: message.data.info?.mode ?? null,
        trigger: message.data.info?.trigger ?? current?.trigger ?? TaskTriggerReason.MANUAL,
        taskInfo: projectTaskTree(message.data),
        prefetch: message.data.current?.prefetch ?? null,
        taskName: message.data.info?.name ?? current?.taskName ?? null,
      }
      setTaskState(state)
      emitRuntimeEvent({ type: 'info', state })
    }),
    subscribe({ id: taskId, type: WS_TASK_COMPLETED }, message => {
      handleTaskCompleted(taskId, message.data)
    }),
  ])
}

const handleTaskCreated = (data: WSTaskCreatedData): void => {
  mutationSequence++
  const current = taskStates.value.get(data.taskId)
  const state: TaskRuntimeState = {
    ...(current ?? createUnknownTaskState(data.taskId)),
    mode: data.mode,
    trigger: data.trigger ?? TaskTriggerReason.MANUAL,
    scriptId: data.scripts[0]?.scriptId ?? null,
    scripts: cloneScripts(data.scripts),
    phase: 'created',
    taskName: data.taskName ?? null,
    taskType: data.taskType ?? null,
    result: null,
    outcome: null,
    error: null,
    completedAt: null,
  }
  setTaskState(state)
  ensureTaskSubscriptions(data.taskId)
  emitRuntimeEvent({ type: 'created', state })
}

const handleTaskCompleted = (taskId: string, data: WSTaskCompletedData): void => {
  mutationSequence++
  const current = taskStates.value.get(taskId)
  const state: TaskRuntimeState = {
    ...(current ?? createUnknownTaskState(taskId)),
    phase: 'completed',
    prefetch: null,
    taskInfo: projectTaskTree(data.task),
    taskName: data.task.info?.name ?? current?.taskName ?? null,
    log: current?.log ?? '',
    result: data.result,
    outcome: data.outcome,
    error: data.error ?? null,
    completedAt: Date.now(),
  }
  setTaskState(state)
  releaseTaskSubscriptions(taskId)
  emitRuntimeEvent({ type: 'completed', state })
}

const stateFromSnapshot = (
  item: TaskRuntimeSnapshotItem,
  current?: TaskRuntimeState
): TaskRuntimeState => {
  const state: TaskRuntimeState = {
    ...(current ?? createUnknownTaskState(item.taskId)),
    taskId: item.taskId,
    mode: item.mode,
    scriptId: item.scriptId ?? null,
    userId: item.userId ?? null,
    stopping: item.stopping ?? false,
    trigger: item.trigger ?? item.task.info?.trigger ?? TaskTriggerReason.MANUAL,
    scripts: cloneScripts(item.scripts),
    taskInfo: projectTaskTree(item.task),
    prefetch: item.task.current?.prefetch ?? null,
    taskName: item.task.info?.name ?? current?.taskName ?? null,
    phase: 'active',
    result: null,
    outcome: null,
    error: null,
    completedAt: null,
  }
  // 请求途中的日志增量不使整次快照失效；只拒绝较旧或过程态的日志基线。
  if (current?.logSeq === undefined || (item.logSeq != null && item.logSeq >= current.logSeq)) {
    applyTaskLogUpdate(state, {
      log: item.log ?? item.task.current?.log ?? '',
      seq: item.logSeq ?? 0,
      append: false,
      firstLine: item.logFirstLine ?? 1,
    })
    state.logSeq = item.logSeq ?? undefined
  }
  return state
}

const clearSnapshotRetryTimer = (): void => {
  if (snapshotRetryTimer !== null) {
    window.clearTimeout(snapshotRetryTimer)
    snapshotRetryTimer = null
  }
}

const scheduleSnapshotRetry = (delayMs: number, retry: () => void): void => {
  clearSnapshotRetryTimer()
  snapshotRetryTimer = window.setTimeout(() => {
    snapshotRetryTimer = null
    retry()
  }, delayMs)
}

/**
 * 拉取运行任务快照并与增量事件对账。
 *
 * @param mutationRetries 已因请求期间有增量事件而重取的次数
 * @param failureRetried 本轮是否已做过失败重试
 */
const loadTaskRuntimeSnapshot = async (
  mutationRetries: number,
  failureRetried: boolean
): Promise<void> => {
  // 新一轮拉取取代尚未触发的重试
  clearSnapshotRetryTimer()
  const generation = ++snapshotGeneration
  const startedAtMutation = mutationSequence
  try {
    const snapshot = await realtimeSnapshotApi.getRuntimeTasks()
    if (generation !== snapshotGeneration) return
    if (startedAtMutation !== mutationSequence) {
      if (mutationRetries >= SNAPSHOT_MUTATION_RETRY_LIMIT) {
        logger.warn('运行任务快照请求期间持续有增量事件，放弃本轮对账')
        return
      }
      scheduleSnapshotRetry(SNAPSHOT_MUTATION_RETRY_DELAY_MS, () => {
        void loadTaskRuntimeSnapshot(mutationRetries + 1, failureRetried)
      })
      return
    }

    const activeTaskIds = new Set((snapshot.tasks ?? []).map(item => item.taskId))
    const next = new Map(taskStates.value)
    const activeStates: TaskRuntimeState[] = []
    const removedTaskIds: string[] = []

    for (const item of snapshot.tasks ?? []) {
      const state = stateFromSnapshot(item, next.get(item.taskId))
      next.set(item.taskId, state)
      activeStates.push(state)
      ensureTaskSubscriptions(item.taskId)
    }

    for (const [taskId, state] of next) {
      if (state.phase === 'completed' || activeTaskIds.has(taskId)) continue
      // 无完成消息时只确认“不再运行”，保留已显示内容，不编造任务结果。
      next.set(taskId, { ...state, prefetch: null, phase: 'completed', completedAt: Date.now() })
      releaseTaskSubscriptions(taskId)
      removedTaskIds.push(taskId)
    }

    // 刷新后仅保存过绑定的已结束标签，仍可确认“不再运行”；不伪造结果或日志。
    retainedTasks.forEach(taskId => {
      if (!next.has(taskId) && !activeTaskIds.has(taskId)) {
        next.set(taskId, {
          ...createUnknownTaskState(taskId),
          phase: 'completed',
          completedAt: Date.now(),
        })
      }
    })

    taskStates.value = next
    emitRuntimeEvent({ type: 'snapshot', states: activeStates, activeTaskIds })
    removedTaskIds.forEach(taskId => emitRuntimeEvent({ type: 'removed', taskId }))
    // 事务过程态可能已推送、尚未提交；复用已有重试以取得可追加的日志基线。
    if (
      (snapshot.tasks ?? []).some(item => item.logSeq === null) &&
      mutationRetries < SNAPSHOT_MUTATION_RETRY_LIMIT
    ) {
      scheduleSnapshotRetry(SNAPSHOT_MUTATION_RETRY_DELAY_MS, () => {
        void loadTaskRuntimeSnapshot(mutationRetries + 1, failureRetried)
      })
    }
  } catch (error) {
    logger.warn(
      `读取运行任务 HTTP 快照失败: ${error instanceof Error ? error.message : String(error)}`
    )
    // 已被新一轮拉取取代或已释放时不再重试；只重试一次，之后交给下次重连
    if (generation !== snapshotGeneration || failureRetried) return
    scheduleSnapshotRetry(SNAPSHOT_FAILURE_RETRY_DELAY_MS, () => {
      // 期间又断开了：重新连上时 onConnected 会再拉一次
      if (connectionState().value !== 'open') return
      void loadTaskRuntimeSnapshot(0, true)
    })
  }
}

export function refreshTaskRuntimeSnapshot(): Promise<void> {
  return loadTaskRuntimeSnapshot(0, false)
}

const pruneCompletedStates = (): void => {
  const now = Date.now()
  const next = new Map(taskStates.value)
  let changed = false

  for (const [taskId, state] of next) {
    if (
      !retainedTasks.has(taskId) &&
      state.phase === 'completed' &&
      state.completedAt !== null &&
      now - state.completedAt > COMPLETED_STATE_RETENTION_MS
    ) {
      next.delete(taskId)
      changed = true
    }
  }

  if (changed) taskStates.value = next
}

export function bootstrapTaskRuntimeState(): void {
  if (bootstrapped) return
  bootstrapped = true
  residentSubscriptionIds.push(
    subscribe({ id: WS_ID_TASK_MANAGER, type: WS_TASK_CREATED }, message =>
      handleTaskCreated(message.data)
    )
  )
  disposeConnectedListener = onConnected(refreshTaskRuntimeSnapshot)
  completedStateCleanupTimer = window.setInterval(
    pruneCompletedStates,
    COMPLETED_STATE_CLEANUP_INTERVAL_MS
  )
  if (connectionState().value === 'open') void refreshTaskRuntimeSnapshot()
}

export function disposeTaskRuntimeState(): void {
  snapshotGeneration++
  clearSnapshotRetryTimer()
  disposeConnectedListener?.()
  disposeConnectedListener = null
  residentSubscriptionIds.splice(0).forEach(unsubscribe)
  for (const taskId of [...taskSubscriptionIds.keys()]) releaseTaskSubscriptions(taskId)
  if (completedStateCleanupTimer !== null) {
    window.clearInterval(completedStateCleanupTimer)
    completedStateCleanupTimer = null
  }
  taskStates.value = new Map()
  retainedTasks.clear()
  resyncingLogs.clear()
  bootstrapped = false
}

export function onTaskRuntimeEvent(listener: TaskRuntimeListener): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function getTaskRuntimeState(taskId: string): TaskRuntimeState | undefined {
  return taskStates.value.get(taskId)
}

export function getTaskRuntimeStates(): TaskRuntimeState[] {
  return [...taskStates.value.values()]
}

export function useTaskRuntimeState() {
  return {
    tasks: computed(() => taskStates.value),
    refresh: refreshTaskRuntimeSnapshot,
  }
}

/** HTTP 受理只补齐订阅；早到的创建、日志、终态保持原对象数据。 */
export function registerAcceptedTask(taskId: string, mode: WSTaskMode): void {
  if (taskStates.value.has(taskId)) return
  const state = { ...createUnknownTaskState(taskId), mode }
  setTaskState(state)
  ensureTaskSubscriptions(taskId)
  emitRuntimeEvent({ type: 'created', state })
  void refreshTaskRuntimeSnapshot()
}

export function retainTaskRuntime(taskId: string): void {
  retainedTasks.add(taskId)
}

export function releaseTaskRuntime(taskId: string): void {
  retainedTasks.delete(taskId)
}

/** stop 已等待服务端收尾；先留出完成事件窗口，断线时再通过快照确认。 */
export async function reconcileStoppedTask(taskId: string): Promise<void> {
  await new Promise<void>(resolve => window.setTimeout(resolve, 1500))
  if (taskStates.value.get(taskId)?.phase !== 'completed') await refreshTaskRuntimeSnapshot()
}
