import { observeFeature } from '@/utils/featureAnalytics'
import { ApiError, Service, TaskCreateIn, type TaskCreateOut } from '@/api'
import {
  analyticsScriptType,
  beginAnalyticsOperation,
  getAnalyticsScriptType,
} from '@/utils/analytics'
import { getTaskRuntimeStates } from '@/composables/useTaskRuntimeState'
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

export type TaskTargetKind = AnalyticsEventProps['task_start_result']['target_kind']

type TaskStartMetadata = Partial<
  Pick<AnalyticsEventProps['task_start_result'], 'source' | 'target_kind'>
>

function nativeScriptType(taskId: string, targetId = '') {
  const script = getTaskRuntimeStates().find(task => task.taskId === taskId)?.scripts[0]
  return script ? analyticsScriptType(script.scriptType) : getAnalyticsScriptType(targetId)
}

export type NativeConfigStopAction = 'save' | 'close' | 'timeout'

/** 仅记录停止请求的受理结果；不能由停止成功推断原生配置已经保存。 */
export async function stopNativeConfig(taskId: string, action: NativeConfigStopAction = 'close') {
  const operation = beginAnalyticsOperation('native_config_action_finished')
  const script_type = nativeScriptType(taskId)
  try {
    const response = await Service.stopTaskApiDispatchStopPost({ taskId })
    operation.finish({
      script_type,
      operation: action,
      outcome: response.code === 200 ? 'accepted' : 'failure',
    })
    return response
  } catch (error) {
    operation.finish({ script_type, operation: action, outcome: 'failure' })
    throw error
  }
}

/** 保留原始接口返回语义，供配置会话和更新入口复用同一个请求计数边界。 */
export async function requestTaskStart(
  request: TaskCreateIn,
  metadata: TaskStartMetadata = {}
): Promise<TaskCreateOut> {
  const operation = beginAnalyticsOperation('task_start_result')
  const nativeOperation =
    request.mode === TaskCreateIn.mode.SCRIPT_CONFIG
      ? beginAnalyticsOperation('native_config_action_finished')
      : null
  const nativeAction = request.viewOnly ? 'view' : 'open'
  const executable =
    request.mode === TaskCreateIn.mode.AUTO_PROXY || request.mode === TaskCreateIn.mode.CYCLE_RUN
  const fromScript =
    request.mode === TaskCreateIn.mode.AUTO_PROXY && Boolean(request.resumeFromScriptId)
  const scopeKind =
    request.queueUserIds && Object.keys(request.queueUserIds).length
      ? ('queue_users' as const)
      : request.userId || request.userIds != null
        ? ('script_users' as const)
        : ('all' as const)
  const resumeOperation =
    executable && (fromScript || scopeKind !== 'all')
      ? beginAnalyticsOperation('task_resume_requested')
      : null
  const resumeDimensions = {
    source: metadata.source ?? 'unknown',
    resume_kind: fromScript
      ? scopeKind === 'all'
        ? ('from_script' as const)
        : ('from_script_scoped_users' as const)
      : ('scoped_users' as const),
    scope_kind: scopeKind,
  }
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
    resumeOperation?.finish({ ...resumeDimensions, request_outcome: 'failure' })
    nativeOperation?.finish({
      script_type: getAnalyticsScriptType(request.taskId),
      operation: nativeAction,
      outcome: 'failure',
    })
    operation.finish({ ...dimensions, outcome: 'failure' })
    throw error
  }
  resumeOperation?.finish({
    ...resumeDimensions,
    request_outcome: response.code === 200 && response.taskId ? 'accepted' : 'failure',
  })
  nativeOperation?.finish({
    script_type: nativeScriptType(response.taskId ?? '', request.taskId),
    operation: nativeAction,
    outcome: response.code === 200 && response.taskId ? 'accepted' : 'failure',
  })
  operation.finish({
    ...dimensions,
    outcome: response.code === 200 && response.taskId ? 'accepted' : 'failure',
  })
  return response
}

/** 配置会话明确使用独立任务模式，保留后端原始响应。 */
export function requestScriptConfigStart(
  taskId: string,
  viewOnly?: boolean,
  targetKind: TaskTargetKind = 'unknown'
): Promise<TaskCreateOut> {
  return requestTaskStart(
    {
      taskId,
      mode: TaskCreateIn.mode.SCRIPT_CONFIG,
      ...(viewOnly === undefined ? {} : { viewOnly }),
    },
    { source: 'script_config', target_kind: targetKind }
  )
}

export function requestUserUpdateStart(
  userId: string,
  scriptType: AnalyticsEventProps['adapter_setup_finished']['script_type']
): Promise<TaskCreateOut> {
  return observeFeature(
    'adapter_setup_finished',
    {
      script_type: scriptType,
      operation_kind: 'update',
      engine_kind: 'unknown',
    },
    () =>
      requestTaskStart(
        { taskId: userId, mode: TaskCreateIn.mode.UPDATE },
        { source: 'script_update', target_kind: 'user' }
      ),
    result => (result.code === 200 && result.taskId ? 'accepted' : 'rejected')
  )
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

  const stopTask = async (
    taskId: string,
    metadata: Partial<Pick<AnalyticsEventProps['task_stop_result'], 'source'>> = {}
  ): Promise<void> => {
    const operation = beginAnalyticsOperation('task_stop_result')
    const state = getTaskRuntimeStates().find(task => task.taskId === taskId)
    const dimensions = {
      source: metadata.source ?? 'unknown',
      mode: state?.mode ?? ('unknown' as const),
    }
    try {
      const response = await Service.stopTaskApiDispatchStopPost({ taskId })
      if (response.code !== 200) {
        throw new Error(response.message)
      }
      operation.finish({ ...dimensions, request_outcome: 'accepted' })
    } catch (error) {
      operation.finish({ ...dimensions, request_outcome: 'failure' })
      throw taskRequestError(error)
    }
  }

  return { startTask, stopTask }
}
