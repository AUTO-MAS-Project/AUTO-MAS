import { OpenAPI } from '@/api/core/OpenAPI'
import { request } from '@/api/core/request'
import type { TaskItemPayload, WSDialogRequestData } from '@/services/websocket/types'

export interface PowerCountdownSnapshot {
  active: boolean
  operation: string | null
  remaining: number
}

/** ``POST /api/dispatch/get`` 响应（任务信息载荷即 TaskItem） */
export interface TaskGetOut {
  code?: number
  status?: string
  message?: string
  order?: Array<{ uid: string; type: string }>
  data?: Record<string, TaskItemPayload>
}

const get = <T>(url: string) => request<T>(OpenAPI, { method: 'GET', url })

const post = <T>(url: string, body?: Record<string, unknown>) =>
  request<T>(OpenAPI, { method: 'POST', url, body, mediaType: 'application/json' })

/** HTTP 提供连接时点的初始权威状态；主 WS 只承载之后的增量事件。 */
export const realtimeSnapshotApi = {
  getPendingDialogs: () => get<WSDialogRequestData[]>('/api/core/dialogs/pending'),
  getPowerCountdown: () => get<PowerCountdownSnapshot>('/api/dispatch/power/countdown-snapshot'),
  /** 查询 TaskInfo；``taskId`` 省略时返回全部，载荷为 TaskItem。 */
  getTasks: (taskId?: string | null) =>
    post<TaskGetOut>('/api/dispatch/get', taskId ? { taskId } : {}),
}
