import { ApiError, Service, TaskCreateIn, type TaskCreateOut } from '@/api'
import { beginAnalyticsOperation } from '@/utils/analytics'
import type { AnalyticsEventProps } from '@/types/analytics'

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

type TaskStartMetadata = Partial<
  Pick<AnalyticsEventProps['task_start_result'], 'source' | 'target_kind'>
>

/** 保留原始接口返回语义，供配置会话和更新入口复用同一个请求计数边界。 */
export async function requestTaskStart(
  request: TaskCreateIn,
  metadata: TaskStartMetadata = {}
): Promise<TaskCreateOut> {
  const operation = beginAnalyticsOperation('task_start_result')
  const dimensions = {
    source: metadata.source ?? 'unknown',
    target_kind:
      metadata.target_kind ?? (request.userId ? ('user' as const) : ('unknown' as const)),
    mode: request.mode,
  }
  let response: TaskCreateOut
  try {
    response = await Service.addTaskApiDispatchStartPost(request)
  } catch (error) {
    operation.finish({ ...dimensions, outcome: 'failure' })
    throw error
  }
  operation.finish({
    ...dimensions,
    outcome: response.code === 200 && response.taskId ? 'accepted' : 'failure',
  })
  return response
}

/** 配置会话明确使用独立任务模式，保留后端原始响应。 */
export function requestScriptConfigStart(
  taskId: string,
  viewOnly?: boolean
): Promise<TaskCreateOut> {
  return requestTaskStart(
    {
      taskId,
      mode: TaskCreateIn.mode.SCRIPT_CONFIG,
      ...(viewOnly === undefined ? {} : { viewOnly }),
    },
    { source: 'script_config' }
  )
}

export function requestScriptUpdateStart(taskId: string): Promise<TaskCreateOut> {
  return requestTaskStart({ taskId, mode: TaskCreateIn.mode.UPDATE }, { source: 'script_update' })
}

/** 共用任务操作只处理请求结果；缺少后端说明时，提示文案由入口负责。 */
export function useTaskApi() {
  const startTask = async (
    request: TaskCreateIn,
    metadata: TaskStartMetadata = {}
  ): Promise<TaskCreateOut> => {
    let response: TaskCreateOut
    try {
      response = await requestTaskStart(request, metadata)
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
