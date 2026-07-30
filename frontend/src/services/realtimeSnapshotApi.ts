import { OpenAPI } from '@/api/core/OpenAPI'
import { request } from '@/api/core/request'
import type { WSDialogRequestData, WSTaskScriptInfoData } from '@/services/websocket/types'

export interface PowerCountdownSnapshot {
  active: boolean
  operation: string | null
  remaining: number
}

export type TaskRuntimeMode = 'AutoProxy' | 'ManualReview' | 'ScriptConfig'

export interface TaskRuntimeSnapshotItem {
  taskId: string
  mode: TaskRuntimeMode
  queueId: string | null
  scriptId: string | null
  userId: string | null
  stopping: boolean
  task_info: WSTaskScriptInfoData[]
  log: string
}

export interface TaskRuntimeSnapshot {
  tasks: TaskRuntimeSnapshotItem[]
}

export interface ScriptDispatchState {
  queued: boolean
  running: boolean
  activeFailed: boolean
  recentFailed: boolean
}

export interface ScriptDispatchStateSnapshot {
  states: Record<string, ScriptDispatchState>
}

const get = <T>(url: string) => request<T>(OpenAPI, { method: 'GET', url })

/** HTTP 提供连接时点的初始权威状态；主 WS 只承载之后的增量事件。 */
export const realtimeSnapshotApi = {
  getPendingDialogs: () => get<WSDialogRequestData[]>('/api/core/dialogs/pending'),
  getPowerCountdown: () => get<PowerCountdownSnapshot>('/api/dispatch/power/countdown-snapshot'),
  getRuntimeTasks: () => get<TaskRuntimeSnapshot>('/api/dispatch/runtime-snapshot'),
  getScriptStates: () => get<ScriptDispatchStateSnapshot>('/api/dispatch/script-states-snapshot'),
}
