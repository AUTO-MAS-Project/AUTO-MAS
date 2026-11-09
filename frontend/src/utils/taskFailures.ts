import type { WSTaskScriptInfoData } from '@/services/websocket/types'
import type { TaskCompletionView } from '@/composables/taskTreeProjection'

/** 任务总览里算作失败的脚本 / 用户状态 */
export const FAILED_TASK_STATUSES: ReadonlySet<string> = new Set(['异常'])

const statusMatches = (status: string | undefined, values: ReadonlySet<string>) =>
  Boolean(status && values.has(status))

/** 脚本自身或它的任一用户处在给定状态之一 */
export const scriptHasStatus = (script: WSTaskScriptInfoData, values: ReadonlySet<string>) =>
  statusMatches(script.status, values) ||
  (script.userList ?? []).some(user => statusMatches(user.status, values))

export interface TaskFailureCount {
  /** 自身异常或有用户异常的脚本数 */
  scripts: number
  /** 异常的用户数 */
  users: number
}

/** 按任务总览数出失败的脚本与用户；task_info 缺失时都是 0 */
export function countTaskFailures(
  taskInfo: readonly WSTaskScriptInfoData[] | null | undefined
): TaskFailureCount {
  let scripts = 0
  let users = 0
  const scriptList: readonly WSTaskScriptInfoData[] = Array.isArray(taskInfo) ? taskInfo : []
  for (const script of scriptList) {
    if (scriptHasStatus(script, FAILED_TASK_STATUSES)) scripts += 1
    users += (script.userList ?? []).filter(user =>
      statusMatches(user.status, FAILED_TASK_STATUSES)
    ).length
  }
  return { scripts, users }
}

export type TaskCompletionFeedback =
  | { kind: 'error' }
  | { kind: 'cancelled' }
  | { kind: 'success' }
  | { kind: 'partialFailure'; failures: TaskFailureCount }

/**
 * 调度台收尾先消费机器终态，再检查树投影中的异常用户/托管，保留各专项汇总口径。
 */
export function resolveTaskCompletionFeedback(
  data: Pick<TaskCompletionView, 'outcome' | 'task_info'>
): TaskCompletionFeedback {
  if (data.outcome === 'error') return { kind: 'error' }
  if (data.outcome === 'cancelled') return { kind: 'cancelled' }
  const failures = countTaskFailures(data.task_info)
  if (failures.scripts > 0 || failures.users > 0) return { kind: 'partialFailure', failures }
  return { kind: 'success' }
}
