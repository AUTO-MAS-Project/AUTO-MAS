import type {
  TaskRuntimeEvent,
  TaskRuntimeState,
  ScriptRuntimeStatus,
} from '@/composables/useTaskRuntimeState'
export type TaskFlash = 'start' | 'success' | 'error' | 'cancelled'

/** 徽标只读 running，不把 scheduled/queued 当成正在执行。 */
export function runningSpecializations(
  statuses: ReadonlyMap<string, ScriptRuntimeStatus>
): string[] {
  return [...statuses].filter(([, status]) => status.running).map(([type]) => type)
}

/** 每次入页先播种已知任务；快照只对账，绝不重播历史。 */
export class TaskFeedback {
  private started = new Set<string>()
  private completed = new Set<string>()
  private remember(set: Set<string>, taskId: string): void {
    set.add(taskId)
    // 共享运行态会淘汰旧结果，装饰的去重缓存也保持有界。
    if (set.size > 512) set.delete(set.values().next().value!)
  }
  constructor(states: readonly TaskRuntimeState[]) {
    this.seed(states)
  }
  private seed(states: readonly TaskRuntimeState[]): void {
    for (const state of states) {
      this.remember(this.started, state.taskId)
      if (state.phase === 'completed') this.remember(this.completed, state.taskId)
    }
  }
  consume(event: TaskRuntimeEvent): TaskFlash | null {
    if (event.type === 'snapshot') {
      this.seed(event.states)
      return null
    }
    if (event.type === 'removed') {
      this.started.delete(event.taskId)
      this.completed.delete(event.taskId)
      return null
    }
    const state = event.state
    if (state.mode === 'ScriptConfig') return null
    if (event.type === 'completed') {
      if (this.completed.has(state.taskId)) return null
      this.remember(this.completed, state.taskId)
      return state.outcome
    }
    // created 是任务生命周期开始；不使用 HTTP 受理结果，也不把 scripts 全部标成运行。
    if (event.type === 'created' && !this.started.has(state.taskId)) {
      this.remember(this.started, state.taskId)
      return 'start'
    }
    return null
  }
}
