import { TaskCreateIn } from '@/api/models/TaskCreateIn'

/** 构造启动请求；空数组必须保留为显式用户范围。 */
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
