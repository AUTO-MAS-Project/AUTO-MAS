import { TaskCreateIn } from '@/api/models/TaskCreateIn'

/** 全选省略 userIds，由后端执行时筛选；显式集合（含空数组）原样传递。 */
export const buildStartTaskRequest = (
  taskId: string,
  mode: TaskCreateIn.mode,
  resumeFromScriptId: string | null | undefined,
  selectedUserIds: string[] | undefined
): TaskCreateIn => {
  const requestBody: TaskCreateIn = { taskId, mode }
  if (resumeFromScriptId) requestBody.resumeFromScriptId = resumeFromScriptId
  if (mode === TaskCreateIn.mode.AUTO_PROXY && selectedUserIds !== undefined) {
    requestBody.userIds = [...selectedUserIds]
  }
  return requestBody
}
