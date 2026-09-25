import { TaskCreateIn } from '@/api/models/TaskCreateIn'
import type { SchedulerTab } from './schedulerConstants'

/**
 * 按调度台当前的选择组装启动任务的请求体。
 *
 * 指定单个用户与从某用户开始都只对自动代理有意义，其他模式后端一律拒绝，
 * 切走模式后不再带上；二者互斥，界面上已保证只选其一，这里再按单独运行优先兜一次。
 */
export const buildStartTaskRequest = (
  taskId: string,
  mode: TaskCreateIn.mode,
  scope: Pick<SchedulerTab, 'resumeFromScriptId' | 'selectedUserId' | 'resumeFromUserId'>
): TaskCreateIn => {
  const requestBody: TaskCreateIn = { taskId, mode }
  if (scope.resumeFromScriptId) {
    requestBody.resumeFromScriptId = scope.resumeFromScriptId
  }
  if (mode === TaskCreateIn.mode.AUTO_PROXY) {
    if (scope.selectedUserId) {
      requestBody.userId = scope.selectedUserId
    } else if (scope.resumeFromUserId) {
      requestBody.resumeFromUserId = scope.resumeFromUserId
    }
  }
  return requestBody
}
