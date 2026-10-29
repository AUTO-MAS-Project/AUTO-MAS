import { onTaskRuntimeEvent } from '@/composables/useTaskRuntimeState'
import { subscribe, unsubscribe } from '@/services/websocket/subscriptions'
import {
  WS_ID_TASK_MANAGER,
  WS_TASK_SCRIPT_STARTED,
  WS_TASK_SCRIPT_FINISHED,
  WS_TASK_CONFIG_DISCARDED,
} from '@/services/websocket/types'
import {
  analyticsScriptType,
  beginAnalyticsOperation,
  captureAnalyticsContext,
  recordAnalyticsEvent,
} from '@/utils/analytics'
import type { AnalyticsEventProps } from '@/types/analytics'

type ObservedTask = {
  operation: ReturnType<typeof beginAnalyticsOperation<'task_observed_finished'>>
  mode: AnalyticsEventProps['task_observed_finished']['mode']
  script_type: AnalyticsEventProps['task_observed_finished']['script_type']
  discardSubscription?: string
}
const observed = new Map<string, ObservedTask>()
const completed = new Set<string>()
type ObservedScript = {
  taskId: string
  operation: ReturnType<typeof beginAnalyticsOperation<'script_run_finished'>>
  props: AnalyticsEventProps['script_run_started']
}
const scriptRuns = new Map<string, ObservedScript>()
const completedRuns = new Set<string>()
const subscriptions: string[] = []
let disposeListener: (() => void) | null = null

/** 只统计本窗口收到创建与完成的样本；恢复快照不能制造一次新执行。 */
export function bootstrapTaskAnalytics(): void {
  if (disposeListener) return
  subscriptions.push(
    subscribe({ id: WS_ID_TASK_MANAGER, type: WS_TASK_SCRIPT_STARTED }, ({ data }) => {
      if (data.mode !== 'AutoProxy' && data.mode !== 'CycleRun') return
      if (scriptRuns.has(data.runId) || completedRuns.has(data.runId)) return
      if (scriptRuns.size >= 128) scriptRuns.delete(scriptRuns.keys().next().value!)
      const context = captureAnalyticsContext()
      const props = { mode: data.mode, script_type: analyticsScriptType(data.scriptType) }
      scriptRuns.set(data.runId, {
        taskId: data.taskId,
        operation: beginAnalyticsOperation('script_run_finished', context),
        props,
      })
      recordAnalyticsEvent(context, { name: 'script_run_started', props })
    }),
    subscribe({ id: WS_ID_TASK_MANAGER, type: WS_TASK_SCRIPT_FINISHED }, ({ data }) => {
      if (completedRuns.has(data.runId)) return
      if (completedRuns.size >= 128) completedRuns.delete(completedRuns.values().next().value!)
      completedRuns.add(data.runId)
      const entry = scriptRuns.get(data.runId)
      scriptRuns.delete(data.runId)
      if (entry && entry.taskId === data.taskId)
        entry.operation.finish({
          ...entry.props,
          outcome: data.outcome,
          partial_failure:
            data.partialFailure === 'yes' || data.partialFailure === 'no'
              ? data.partialFailure
              : 'unknown',
        })
    })
  )
  disposeListener = onTaskRuntimeEvent(event => {
    if (event.type === 'snapshot') return
    if (event.type === 'removed') {
      removeObservedTask(event.taskId)
      clearTaskScriptRuns(event.taskId)
      return
    }
    const state = event.state
    if (event.type === 'created' && !observed.has(state.taskId) && !completed.has(state.taskId)) {
      if (observed.size >= 128) removeObservedTask(observed.keys().next().value!)
      const types = new Set(state.scripts.map(item => analyticsScriptType(item.scriptType)))
      observed.set(state.taskId, {
        operation: beginAnalyticsOperation('task_observed_finished'),
        mode: state.mode ?? 'unknown',
        script_type: types.size > 1 ? 'multi' : (types.values().next().value ?? 'unknown'),
      })
      if (state.mode === 'ScriptConfig') {
        const entry = observed.get(state.taskId)!
        const discard = beginAnalyticsOperation('native_config_action_finished')
        entry.discardSubscription = subscribe(
          { id: state.taskId, type: WS_TASK_CONFIG_DISCARDED },
          () =>
            discard.finish({
              script_type: entry.script_type,
              operation: 'discard',
              outcome: 'discarded',
            })
        )
      }
    } else if (event.type === 'completed') {
      // 逐轮消息独立后台发送，最后一轮的终态可能晚于整任务完成。
      const entry = removeObservedTask(state.taskId)
      if (!completed.has(state.taskId)) {
        if (completed.size >= 128) completed.delete(completed.values().next().value!)
        completed.add(state.taskId)
      }
      if (entry && state.outcome)
        entry.operation.finish({
          mode: entry.mode,
          script_type: entry.script_type,
          outcome: state.outcome,
        })
    }
  })
}

function removeObservedTask(taskId: string): ObservedTask | undefined {
  const entry = observed.get(taskId)
  if (entry?.discardSubscription) unsubscribe(entry.discardSubscription)
  observed.delete(taskId)
  return entry
}

function clearTaskScriptRuns(taskId: string): void {
  for (const [runId, entry] of scriptRuns) {
    if (entry.taskId === taskId) scriptRuns.delete(runId)
  }
}

export function disposeTaskAnalytics(): void {
  disposeListener?.()
  disposeListener = null
  for (const entry of observed.values()) {
    if (entry.discardSubscription) unsubscribe(entry.discardSubscription)
  }
  observed.clear()
  completed.clear()
  subscriptions.splice(0).forEach(unsubscribe)
  scriptRuns.clear()
  completedRuns.clear()
}
