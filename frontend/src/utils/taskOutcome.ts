import { Service, type TaskOutcome } from '@/api'

const OUTCOME_QUERY_ATTEMPTS = 5
const OUTCOME_QUERY_RETRY_MS = 300

/** 完成事件先于最近结果落库时，给单点查询留出短暂重试窗口。 */
export const queryTaskOutcome = async (taskId: string): Promise<TaskOutcome | null> => {
  for (let attempt = 0; attempt < OUTCOME_QUERY_ATTEMPTS; attempt += 1) {
    try {
      const status = await Service.getTaskStatusApiDispatchTaskTaskIdGet(taskId)
      if (status?.taskOutcome) return status.taskOutcome
    } catch {
      // 下一轮重试；调用方仍可依赖 WebSocket 作为实时通道。
    }
    if (attempt < OUTCOME_QUERY_ATTEMPTS - 1) {
      await new Promise(resolve => setTimeout(resolve, OUTCOME_QUERY_RETRY_MS))
    }
  }
  return null
}
