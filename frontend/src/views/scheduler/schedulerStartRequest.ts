import type { TaskCreateIn } from '@/api/models/TaskCreateIn'
import { TaskMode } from '@/api/models/TaskMode'

/** 构造新调度契约；队列起点由脚本和用户组成。 */
export const buildStartTaskRequest = (
  targetId: string,
  isQueue: boolean,
  startScriptId?: string | null,
  startUserId?: string | null
): TaskCreateIn => {
  if (!isQueue) return { mode: TaskMode.AUTO_PROXY, scriptId: targetId }

  const request: TaskCreateIn = { mode: TaskMode.AUTO_PROXY, queueId: targetId }
  if (startScriptId) request.scriptId = startScriptId
  if (startScriptId && startUserId) request.userId = startUserId
  return request
}
