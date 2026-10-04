import { TaskCreateIn } from '@/api/models/TaskCreateIn'

/**
 * 全选省略 userIds，由后端执行时筛选；显式集合（含空数组）原样传递。
 *
 * queueUserIds 是队列任务的同一套语义，按托管（脚本ID）分组：缺项表示该托管本次不限制，
 * 空数组表示该托管本次整项跳过，所以这里只判断有没有内容，不做「去重成不限制」的转换。
 */
export const buildStartTaskRequest = (
  taskId: string,
  mode: TaskCreateIn.mode,
  resumeFromScriptId: string | null | undefined,
  selectedUserIds: string[] | undefined,
  queueUserIds?: Record<string, string[]>
): TaskCreateIn => {
  const requestBody: TaskCreateIn = { taskId, mode }
  if (resumeFromScriptId) requestBody.resumeFromScriptId = resumeFromScriptId
  if (mode === TaskCreateIn.mode.AUTO_PROXY && selectedUserIds !== undefined) {
    requestBody.userIds = [...selectedUserIds]
  }
  if (queueUserIds && Object.keys(queueUserIds).length > 0) {
    requestBody.queueUserIds = { ...queueUserIds }
  }
  return requestBody
}
