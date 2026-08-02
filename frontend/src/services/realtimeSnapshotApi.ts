import { OpenAPI } from '@/api/core/OpenAPI'
import { request } from '@/api/core/request'
import type {
  WSDialogRequestData,
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
  scripts: WSTaskScriptIdentityData[]
  task_info: WSTaskScriptInfoData[]
  log: string
}

export interface TaskRuntimeSnapshot {
  tasks: TaskRuntimeSnapshotItem[]
  scheduledScripts: WSTaskScriptIdentityData[]
}

const get = <T>(url: string) => request<T>(OpenAPI, { method: 'GET', url })

/** HTTP 提供连接时点的初始权威状态；主 WS 只承载之后的增量事件。 */
export const realtimeSnapshotApi = {
  getPendingDialogs: () => get<WSDialogRequestData[]>('/api/core/dialogs/pending'),
  getPowerCountdown: () => get<PowerCountdownSnapshot>('/api/dispatch/power/countdown-snapshot'),
  getRuntimeTasks: () => get<TaskRuntimeSnapshot>('/api/dispatch/runtime-snapshot'),
}
