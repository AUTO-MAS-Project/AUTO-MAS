import { OpenAPI } from '@/api/core/OpenAPI'
import { request } from '@/api/core/request'
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
  log: string
}

export interface TaskRuntimeSnapshot {
  tasks: TaskRuntimeSnapshotItem[]
  scheduledScripts: WSTaskScriptIdentityData[]
}

const get = <T>(url: string) => request<T>(OpenAPI, { method: 'GET', url })

/** HTTP 提供连接时点的初始权威状态；主 WS 只承载之后的增量事件。 */
export const realtimeSnapshotApi = {
  getPowerCountdown: () => get<PowerCountdownSnapshot>('/api/dispatch/power/countdown-snapshot'),
  getRuntimeTasks: () => get<TaskRuntimeSnapshot>('/api/dispatch/runtime-snapshot'),
}
