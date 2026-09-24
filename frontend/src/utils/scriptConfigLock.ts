import type { TaskRuntimeState } from '@/composables/useTaskRuntimeState'
import type { WSTaskScriptInfoData } from '@/services/websocket/types'

const RUNNING_STATUSES = new Set(['运行', '运行中'])

const scriptInfoIsRunning = (script: WSTaskScriptInfoData) =>
  (script.status !== undefined && RUNNING_STATUSES.has(script.status)) ||
  (script.userList ?? []).some(
    user => user.status !== undefined && RUNNING_STATUSES.has(user.status)
  )

export function isScriptConfigLocked(
  tasks: readonly TaskRuntimeState[],
  scriptId: string
): boolean {
  return tasks.some(task => {
    if (task.phase === 'completed') return false

    if (task.mode === 'CycleRun' || task.isCycle) {
      return (
        task.cycleNextList.some(item => item.scriptId === scriptId && item.isRunning) ||
        task.taskInfo.some(info => info.script_id === scriptId && scriptInfoIsRunning(info))
      )
    }

    if (task.queueId !== null) {
      return task.taskInfo.some(info => info.script_id === scriptId && scriptInfoIsRunning(info))
    }

    return task.scriptId === scriptId || task.scripts.some(script => script.scriptId === scriptId)
  })
}
