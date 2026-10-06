import { computed, ref } from 'vue'
import { realtimeSnapshotApi } from '@/services/realtimeSnapshotApi'
import { connectionState, onConnected } from '@/services/websocket/connection'
import { subscribe, unsubscribe } from '@/services/websocket/subscriptions'
import {
  WS_ID_TASK_MANAGER,
  WS_TASK_COMPLETED,
  WS_TASK_CREATED,
  WS_TASK_INFO_UPDATED,
  type TaskItemPayload,
  type TaskScriptItemPayload,
  type WSTaskCompletedData,
  type WSTaskCreatedData,
  WSTaskMode,
  type WSTaskScriptIdentityData,
} from '@/services/websocket/types'

const logger = window.electronAPI.getLogger('任务运行状态')

const COMPLETED_STATE_RETENTION_MS = 5 * 60 * 1000
const COMPLETED_STATE_CLEANUP_INTERVAL_MS = 30 * 1000
const WAITING_STATUSES = new Set(['等待', '等待中', 'pending'])
const RUNNING_STATUSES = new Set(['运行', '运行中'])
const FAILED_STATUSES = new Set(['异常'])

export interface TaskRuntimeState {
  taskId: string
  mode: WSTaskMode | null
  queueId: string | null
  scriptId: string | null
  userId: string | null
  /** 关联脚本静态标识（创建通知带类型；/get 刷新时尽量保留已有类型） */
  scripts: WSTaskScriptIdentityData[]
  /** TaskItem API 载荷 */
  task: TaskItemPayload | null
  log: string
  phase: 'created' | 'active' | 'completed'
  taskName: string | null
  taskType: string | null
  result: string | null
  outcome: WSTaskCompletedData['outcome'] | null
  error: string | null
  completedAt: number | null
}

export interface ScriptRuntimeStatus {
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
const lastTerminalFailureByType = ref(new Map<string, boolean>())
const listeners = new Set<TaskRuntimeListener>()
const taskSubscriptionIds = new Map<string, string[]>()
const residentSubscriptionIds: string[] = []

let bootstrapped = false
let disposeConnectedListener: (() => void) | null = null
let completedStateCleanupTimer: number | null = null
let snapshotGeneration = 0
let mutationSequence = 0

const emptyTask = (): TaskItemPayload => ({
  info: {
    mode: WSTaskMode.AUTO_PROXY,
    queue_id: null,
    script_id: null,
    user_id: null,
  },
  current: { index: null },
  scripts: {},
})

const cloneTask = (task?: TaskItemPayload | null): TaskItemPayload | null => {
  if (!task) return null
  return structuredClone(task)
}

const currentLog = (task: TaskItemPayload | null | undefined): string => {
  // 优先任务级 Virtual log；旧载荷无该字段时再从当前脚本 current.log 取
  if (task?.current?.log) return task.current.log
  if (!task?.current?.index) return ''
  const script = task.scripts?.[task.current.index]
  return script?.current?.log ?? ''
}

/** 从 TaskItem.scripts 合并脚本标识；已有 scriptType 优先保留。 */
const identitiesFromTask = (
  task: TaskItemPayload,
  previous?: WSTaskScriptIdentityData[]
): WSTaskScriptIdentityData[] => {
  const prevById = new Map((previous ?? []).map(item => [item.scriptId, item.scriptType]))
  return Object.keys(task.scripts ?? {}).map(scriptId => ({
    scriptId,
    scriptType: prevById.get(scriptId) ?? '',
  }))
}

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
  scripts: [],
  task: null,
  log: '',
  phase: 'created',
  taskName: null,
  taskType: null,
  result: null,
  outcome: null,
  error: null,
  completedAt: null,
})

const applyTaskPayload = (
  base: TaskRuntimeState,
  task: TaskItemPayload,
  patch: Partial<TaskRuntimeState> = {}
): TaskRuntimeState => {
  const cloned = cloneTask(task) ?? emptyTask()
  return {
    ...base,
    mode: cloned.info.mode ?? base.mode,
    queueId: cloned.info.queue_id ?? null,
    scriptId: cloned.info.script_id ?? null,
    userId: cloned.info.user_id ?? null,
    scripts: identitiesFromTask(cloned, base.scripts),
    task: cloned,
    log: currentLog(cloned),
    ...patch,
  }
}

const ensureTaskSubscriptions = (taskId: string): void => {
  if (taskSubscriptionIds.has(taskId)) return
  taskSubscriptionIds.set(taskId, [
    subscribe({ id: taskId, type: WS_TASK_INFO_UPDATED }, message => {
      mutationSequence++
      const current = taskStates.value.get(taskId) ?? createUnknownTaskState(taskId)
      const state = applyTaskPayload(current, message.data, { phase: 'active' })
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
    queueId: data.queueId ?? null,
    scriptId: data.scriptId ?? null,
    userId: data.userId ?? null,
    // 创建事件不再带脚本列表；脚本标识随首个 task.info.updated 的 TaskItem 载荷补齐
    scripts: current?.scripts ?? [],
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
  const current = taskStates.value.get(taskId) ?? createUnknownTaskState(taskId)
  const state = applyTaskPayload(current, data.task ?? emptyTask(), {
    phase: 'completed',
    result: data.result,
    outcome: data.outcome,
    error: data.error ?? null,
    completedAt: Date.now(),
  })
  setTaskState(state)
  updateLastTerminalFailures(state)
  releaseTaskSubscriptions(taskId)
  emitRuntimeEvent({ type: 'completed', state })
}

export async function refreshTaskRuntimeSnapshot(): Promise<void> {
  const generation = ++snapshotGeneration
  const startedAtMutation = mutationSequence
  try {
    const response = await realtimeSnapshotApi.getTasks()
    if (generation !== snapshotGeneration) return
    if (startedAtMutation !== mutationSequence) {
      void refreshTaskRuntimeSnapshot()
      return
    }

    const data = response.data ?? {}
    const activeTaskIds = new Set(Object.keys(data))
    const next = new Map(taskStates.value)
    const activeStates: TaskRuntimeState[] = []
    const removedTaskIds: string[] = []

    for (const [taskId, task] of Object.entries(data)) {
      const current = next.get(taskId) ?? createUnknownTaskState(taskId)
      const state = applyTaskPayload(current, task, {
        phase: 'active',
        result: null,
        outcome: null,
        error: null,
        completedAt: null,
      })
      next.set(taskId, state)
      activeStates.push(state)
      ensureTaskSubscriptions(taskId)
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
      `读取任务信息失败: ${error instanceof Error ? error.message : String(error)}`
    )
  }
}

const statusMatches = (status: string | undefined, values: ReadonlySet<string>) =>
  Boolean(status && values.has(status))

const scriptHasStatus = (script: TaskScriptItemPayload | undefined, values: ReadonlySet<string>) => {
  if (!script) return false
  if (statusMatches(script.info?.status, values)) return true
  return Object.values(script.users ?? {}).some(user => statusMatches(user.info?.status, values))
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
  if (task.mode === WSTaskMode.SCRIPT_CONFIG) return

  const scripts = task.task?.scripts ?? {}
  const failedScriptIds = new Set(
    Object.entries(scripts)
      .filter(([, script]) => scriptHasStatus(script, FAILED_STATUSES))
      .map(([scriptId]) => scriptId)
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

  for (const task of taskStates.value.values()) {
    if (task.mode === WSTaskMode.SCRIPT_CONFIG || task.phase === 'completed') continue

    const scripts = task.task?.scripts ?? {}
    for (const identity of task.scripts) {
      const status = getOrCreateScriptStatus(statuses, identity.scriptType)
      const scriptInfo = scripts[identity.scriptId]

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
  disposeConnectedListener?.()
  disposeConnectedListener = null
  residentSubscriptionIds.splice(0).forEach(unsubscribe)
  for (const taskId of [...taskSubscriptionIds.keys()]) releaseTaskSubscriptions(taskId)
  if (completedStateCleanupTimer !== null) {
    window.clearInterval(completedStateCleanupTimer)
    completedStateCleanupTimer = null
  }
  taskStates.value = new Map()
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

/** 把 TaskItem.scripts 压成总览树仍在用的扁平列表（仅 UI 适配）。 */
export function flattenTaskScripts(task: TaskItemPayload | null | undefined) {
  if (!task?.scripts) return []
  return Object.entries(task.scripts).map(([scriptId, script]) => ({
    script_id: scriptId,
    name: script.info?.name || '未知脚本',
    status: script.info?.status || '等待',
    userList: Object.entries(script.users ?? {}).map(([userId, user]) => ({
      user_id: userId,
      name: user.info?.name || '',
      status: user.info?.status || '',
    })),
  }))
}

export function useTaskRuntimeState() {
  return {
    tasks: computed(() => taskStates.value),
    scriptStatusesByType,
    refresh: refreshTaskRuntimeSnapshot,
  }
}
