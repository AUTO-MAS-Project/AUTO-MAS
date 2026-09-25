import { computed, ref } from 'vue'
import { realtimeSnapshotApi, type TaskRuntimeSnapshotItem } from '@/services/realtimeSnapshotApi'
import { connectionState, onConnected } from '@/services/websocket/connection'
import { subscribe, unsubscribe } from '@/services/websocket/subscriptions'
import {
  WS_ID_TASK_MANAGER,
  WS_TASK_COMPLETED,
  WS_TASK_CREATED,
  WS_TASK_INFO_UPDATED,
  type WSTaskCompletedData,
  type WSTaskCreatedData,
  type WSTaskCyclePreviewData,
  type WSTaskMode,
  type WSTaskScriptIdentityData,
  type WSTaskScriptInfoData,
} from '@/services/websocket/types'
import { FAILED_TASK_STATUSES, scriptHasStatus } from '@/utils/taskFailures'

const logger = window.electronAPI.getLogger('任务运行状态')

const COMPLETED_STATE_RETENTION_MS = 5 * 60 * 1000
const COMPLETED_STATE_CLEANUP_INTERVAL_MS = 30 * 1000
// 快照请求期间有增量事件时隔一拍重取，避免高频增量下背靠背热请求；连续变动超过上限就放弃
// 本轮对账，此时状态本来就在由增量事件持续刷新
const SNAPSHOT_MUTATION_RETRY_DELAY_MS = 500
const SNAPSHOT_MUTATION_RETRY_LIMIT = 5
// 快照拉取失败后延时重试一次，避免状态陈旧到下次重连
const SNAPSHOT_FAILURE_RETRY_DELAY_MS = 3000
const WAITING_STATUSES = new Set(['等待', '等待中'])
const RUNNING_STATUSES = new Set(['运行', '运行中'])

export interface TaskRuntimeState {
  taskId: string
  mode: WSTaskMode | null
  queueId: string | null
  scriptId: string | null
  userId: string | null
  stopping: boolean
  isCycle: boolean
  scripts: WSTaskScriptIdentityData[]
  taskInfo: WSTaskScriptInfoData[]
  cycleNextList: WSTaskCyclePreviewData[]
  log: string
  /** 快照里日志对应的 seq，供调度台与后续 task.log.updated 增量衔接 */
  logSeq?: number
  phase: 'created' | 'active' | 'completed'
  taskName: string | null
  taskType: string | null
  result: string | null
  outcome: WSTaskCompletedData['outcome'] | null
  error: string | null
  completedAt: number | null
}

interface ScriptRuntimeStatus {
  queued: boolean
  running: boolean
  lastFailed: boolean
}

export type TaskRuntimeEvent =
  | { type: 'created' | 'info' | 'completed'; state: TaskRuntimeState }
  | { type: 'snapshot'; states: TaskRuntimeState[]; activeTaskIds: ReadonlySet<string> }
  | { type: 'removed'; taskId: string }

type TaskRuntimeListener = (event: TaskRuntimeEvent) => void | Promise<void>

const taskStates = ref(new Map<string, TaskRuntimeState>())
const scheduledScriptTypes = ref(new Set<string>())
const lastTerminalFailureByType = ref(new Map<string, boolean>())
const listeners = new Set<TaskRuntimeListener>()
const taskSubscriptionIds = new Map<string, string[]>()
const residentSubscriptionIds: string[] = []

let bootstrapped = false
let disposeConnectedListener: (() => void) | null = null
let completedStateCleanupTimer: number | null = null
let snapshotRetryTimer: number | null = null
let snapshotGeneration = 0
let mutationSequence = 0

const cloneScripts = (scripts?: WSTaskScriptIdentityData[]) =>
  (scripts ?? []).map(script => ({ ...script }))

const cloneTaskInfo = (taskInfo?: WSTaskScriptInfoData[]) =>
  (taskInfo ?? []).map(script => ({
    ...script,
    userList: (script.userList ?? []).map(user => ({ ...user })),
  }))

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
  queueId: null,
  scriptId: null,
  userId: null,
  stopping: false,
  isCycle: false,
  scripts: [],
  taskInfo: [],
  cycleNextList: [],
  log: '',
  phase: 'created',
  taskName: null,
  taskType: null,
  result: null,
  outcome: null,
  error: null,
  completedAt: null,
})

const ensureTaskSubscriptions = (taskId: string): void => {
  if (taskSubscriptionIds.has(taskId)) return
  taskSubscriptionIds.set(taskId, [
    subscribe({ id: taskId, type: WS_TASK_INFO_UPDATED }, message => {
      mutationSequence++
      const current = taskStates.value.get(taskId)
      const state: TaskRuntimeState = {
        ...(current ?? createUnknownTaskState(taskId)),
        phase: 'active',
        taskInfo: cloneTaskInfo(message.data.task_info),
        cycleNextList: message.data.cycleNextList ?? [],
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
    isCycle: data.mode === 'CycleRun',
    queueId: data.queueId ?? null,
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
    taskInfo: cloneTaskInfo(data.task_info),
    result: data.result,
    outcome: data.outcome,
    error: data.error ?? null,
    completedAt: Date.now(),
  }
  setTaskState(state)
  updateLastTerminalFailures(state)
  releaseTaskSubscriptions(taskId)
  emitRuntimeEvent({ type: 'completed', state })
}

const stateFromSnapshot = (
  item: TaskRuntimeSnapshotItem,
  current?: TaskRuntimeState
): TaskRuntimeState => ({
  ...(current ?? createUnknownTaskState(item.taskId)),
  taskId: item.taskId,
  mode: item.mode,
  queueId: item.queueId,
  scriptId: item.scriptId,
  userId: item.userId,
  stopping: item.stopping,
  isCycle: item.isCycle,
  scripts: cloneScripts(item.scripts),
  taskInfo: cloneTaskInfo(item.task_info),
  cycleNextList: item.cycleNextList ?? [],
  log: item.log,
  logSeq: item.logSeq,
  phase: 'active',
  result: null,
  outcome: null,
  error: null,
  completedAt: null,
})

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

    scheduledScriptTypes.value = new Set(
      (snapshot.scheduledScripts ?? []).map(script => script.scriptType)
    )

    for (const item of snapshot.tasks ?? []) {
      const state = stateFromSnapshot(item, next.get(item.taskId))
      next.set(item.taskId, state)
      activeStates.push(state)
      ensureTaskSubscriptions(item.taskId)
    }

    for (const [taskId, state] of next) {
      if (state.phase === 'completed' || activeTaskIds.has(taskId)) continue
      next.delete(taskId)
      releaseTaskSubscriptions(taskId)
      removedTaskIds.push(taskId)
    }

    taskStates.value = next
    emitRuntimeEvent({ type: 'snapshot', states: activeStates, activeTaskIds })
    removedTaskIds.forEach(taskId => emitRuntimeEvent({ type: 'removed', taskId }))
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

const getOrCreateScriptStatus = (
  statuses: Map<string, ScriptRuntimeStatus>,
  scriptType: string
) => {
  let status = statuses.get(scriptType)
  if (!status) {
    status = { queued: false, running: false, lastFailed: false }
    statuses.set(scriptType, status)
  }
  return status
}

const updateLastTerminalFailures = (task: TaskRuntimeState): void => {
  if (task.mode === 'ScriptConfig') return

  const failedScriptIds = new Set(
    task.taskInfo
      .filter(info => scriptHasStatus(info, FAILED_TASK_STATUSES))
      .map(info => info.script_id)
  )
  const failAllTypes = task.outcome === 'error' && failedScriptIds.size === 0
  const failureByType = new Map<string, boolean>()

  for (const identity of task.scripts) {
    const failed = failAllTypes || failedScriptIds.has(identity.scriptId)
    failureByType.set(
      identity.scriptType,
      (failureByType.get(identity.scriptType) ?? false) || failed
    )
  }

  if (failureByType.size === 0) return
  const next = new Map(lastTerminalFailureByType.value)
  failureByType.forEach((failed, scriptType) => next.set(scriptType, failed))
  lastTerminalFailureByType.value = next
}

const scriptStatusesByType = computed(() => {
  const statuses = new Map<string, ScriptRuntimeStatus>()

  for (const scriptType of scheduledScriptTypes.value) {
    getOrCreateScriptStatus(statuses, scriptType).queued = true
  }

  for (const task of taskStates.value.values()) {
    if (task.mode === 'ScriptConfig' || task.phase === 'completed') continue

    const infoByScriptId = new Map(task.taskInfo.map(info => [info.script_id, info]))
    for (const identity of task.scripts) {
      const status = getOrCreateScriptStatus(statuses, identity.scriptType)
      const scriptInfo = infoByScriptId.get(identity.scriptId)

      if (!scriptInfo || scriptHasStatus(scriptInfo, WAITING_STATUSES)) status.queued = true
      if (scriptInfo && scriptHasStatus(scriptInfo, RUNNING_STATUSES)) status.running = true
    }
  }

  lastTerminalFailureByType.value.forEach((failed, scriptType) => {
    getOrCreateScriptStatus(statuses, scriptType).lastFailed = failed
  })

  return statuses
})

const pruneCompletedStates = (): void => {
  const now = Date.now()
  const next = new Map(taskStates.value)
  let changed = false

  for (const [taskId, state] of next) {
    if (
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
  scheduledScriptTypes.value = new Set()
  lastTerminalFailureByType.value = new Map()
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
    scriptStatusesByType,
    refresh: refreshTaskRuntimeSnapshot,
  }
}
