import { onTaskRuntimeEvent } from '@/composables/useTaskRuntimeState'
import { analyticsScriptType, beginAnalyticsOperation } from '@/utils/analytics'
import type { AnalyticsEventProps } from '@/types/analytics'

type ObservedTask = {
  operation: ReturnType<typeof beginAnalyticsOperation<'task_observed_finished'>>
  mode: AnalyticsEventProps['task_observed_finished']['mode']
  script_type: AnalyticsEventProps['task_observed_finished']['script_type']
}
const observed = new Map<string, ObservedTask>()
const completed = new Set<string>()
let disposeListener: (() => void) | null = null

/** 只统计本窗口收到创建与完成的样本；恢复快照不能制造一次新执行。 */
export function bootstrapTaskAnalytics(): void {
  if (disposeListener) return
  disposeListener = onTaskRuntimeEvent(event => {
    if (event.type === 'snapshot') return
    if (event.type === 'removed') {
      observed.delete(event.taskId)
      return
    }
    const state = event.state
    if (event.type === 'created' && !observed.has(state.taskId) && !completed.has(state.taskId)) {
      if (observed.size >= 128) observed.delete(observed.keys().next().value!)
      const types = new Set(state.scripts.map(item => analyticsScriptType(item.scriptType)))
      observed.set(state.taskId, {
        operation: beginAnalyticsOperation('task_observed_finished'),
        mode: state.mode ?? 'unknown',
        script_type: types.size > 1 ? 'multi' : (types.values().next().value ?? 'unknown'),
      })
    } else if (event.type === 'completed') {
      const entry = observed.get(state.taskId)
      observed.delete(state.taskId)
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

export function disposeTaskAnalytics(): void {
  disposeListener?.()
  disposeListener = null
  observed.clear()
  completed.clear()
}
