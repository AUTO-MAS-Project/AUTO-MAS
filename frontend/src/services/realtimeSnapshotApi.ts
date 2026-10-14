import { GetService } from '@/api'
import type {
  WSTaskCyclePreviewData,
  WSTaskMode,
  WSTaskScriptIdentityData,
  WSTaskScriptInfoData,
} from '@/services/websocket/types'

export interface PowerCountdownSnapshot {
  active: boolean
  operation: string | null
  remaining: number
}

export interface TaskRuntimeSnapshotItem {
  taskId: string
  mode: WSTaskMode
  queueId: string | null
  scriptId: string | null
  userId: string | null
  stopping: boolean
  isCycle: boolean
  scripts: WSTaskScriptIdentityData[]
  task_info: WSTaskScriptInfoData[]
  cycleNextList: WSTaskCyclePreviewData[]
  /** 上次推送的完整日志尾部（≤200,000 字符），与下一条 task.log.updated 增量衔接 */
  log: string
  /** 上次推送的 seq；没有推送过时后端给 0 */
  logSeq?: number
  /** 快照日志第一行在完整日志里的行号 */
  logFirstLine?: number
}

export interface TaskRuntimeSnapshot {
  tasks: TaskRuntimeSnapshotItem[]
  scheduledScripts: WSTaskScriptIdentityData[]
}

/** HTTP 提供连接时点的初始权威状态；主 WS 只承载之后的增量事件。 */
export const realtimeSnapshotApi = {
  getPowerCountdown: async (): Promise<PowerCountdownSnapshot> => {
    const result = await GetService.getPowerCountdownSnapshotApiDispatchPowerCountdownSnapshotGet()
    return {
      active: result.active ?? false,
      operation: result.operation ?? null,
      remaining: result.remaining ?? 0,
    }
  },
  getRuntimeTasks: async (): Promise<TaskRuntimeSnapshot> => {
    const result = await GetService.getTaskRuntimeSnapshotApiDispatchRuntimeSnapshotGet()
    return {
      tasks: (result.tasks ?? []).map(task => ({
        ...task,
        queueId: task.queueId ?? null,
        scriptId: task.scriptId ?? null,
        userId: task.userId ?? null,
        stopping: task.stopping ?? false,
        isCycle: task.isCycle ?? false,
        scripts: task.scripts ?? [],
        task_info: (task.task_info ?? []).map(script => ({
          ...script,
          userList: script.userList ?? [],
        })),
        cycleNextList: (task.cycleNextList ?? []).map(item => ({
          ...item,
          isDue: item.isDue ?? false,
          isRunning: item.isRunning ?? false,
        })),
        log: task.log ?? '',
      })),
      scheduledScripts: result.scheduledScripts ?? [],
    }
  },
}
