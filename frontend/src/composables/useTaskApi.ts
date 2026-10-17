import { ApiError, Service, type TaskCreateIn, type TaskCreateOut } from '@/api'

function taskRequestError(error: unknown): Error {
  if (error instanceof ApiError) {
    const body: unknown = error.body
    if (
      body &&
      typeof body === 'object' &&
      'message' in body &&
      typeof body.message === 'string' &&
      body.message
    ) {
      return new Error(body.message)
    }
  }
  return error instanceof Error ? error : new Error(String(error))
}

/** 共用任务操作只处理请求结果；缺少后端说明时，提示文案由入口负责。 */
export function useTaskApi() {
  const startTask = async (request: TaskCreateIn): Promise<TaskCreateOut> => {
    let response: TaskCreateOut
    try {
      response = await Service.addTaskApiDispatchStartPost(request)
    } catch (error) {
      throw taskRequestError(error)
    }
    if (response.code !== 200 || !response.taskId) {
      throw new Error(response.message)
    }
    return response
  }

  const stopTask = async (taskId: string): Promise<void> => {
    try {
      const response = await Service.stopTaskApiDispatchStopPost({ taskId })
      if (response.code !== 200) {
        throw new Error(response.message)
      }
    } catch (error) {
      throw taskRequestError(error)
    }
  }

  return { startTask, stopTask }
}
