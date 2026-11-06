import { configSessionRequest } from './useTaskOptions'
import { TaskMode } from '@/api'
import { observeFeature } from '@/utils/featureAnalytics'
import { ApiError, Service, type TaskCreateIn, type TaskCreateOut, type TaskParams } from '@/api'
import {
  analyticsScriptType,
  beginAnalyticsOperation,
  getAnalyticsScriptType,
} from '@/utils/analytics'
import {
  getTaskRuntimeStates,
  registerAcceptedTask,
  reconcileStoppedTask,
} from '@/composables/useTaskRuntimeState'
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
  const root = Object.values(request.tasks)[0]
  const children = Object.values(root?.children ?? {})
  const executable = request.mode === TaskMode.AUTO_PROXY
  const queue = executable && root?.uid !== '-'
  const targetId = executable
    ? queue
      ? (root?.uid ?? '')
      : (children[0]?.uid ?? '')
    : (root?.uid ?? '')
  const operation = beginAnalyticsOperation('task_start_result')
  const nativeOperation = executable
    ? null
    : beginAnalyticsOperation('native_config_action_finished')
  const nativeAction = request.mode === TaskMode.SCRIPT_VIEW ? 'view' : 'open'
  const scoped =
    executable &&
    (queue
      ? children.length > 0
      : children.some(node => Object.keys(node.children ?? {}).length > 0))
  const scopeKind = scoped
    ? queue
      ? ('queue_users' as const)
      : ('script_users' as const)
    : ('all' as const)
  const resumeOperation = scoped ? beginAnalyticsOperation('task_resume_requested') : null
  const resumeDimensions = {
    source: metadata.source ?? 'unknown',
    resume_kind: 'scoped_users' as const,
    scope_kind: scopeKind,
  }
  const dimensions = {
    source: metadata.source ?? 'unknown',
    target_kind: metadata.target_kind ?? (queue ? ('queue' as const) : ('script' as const)),
    mode: request.mode,
  }
  let response: TaskCreateOut
  try {
    response = await Service.addTaskApiDispatchStartPost(request)
  } catch (error) {
    resumeOperation?.finish({ ...resumeDimensions, request_outcome: 'failure' })
    nativeOperation?.finish({
      script_type: getAnalyticsScriptType(targetId),
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
    script_type: nativeScriptType(response.taskId ?? '', targetId),
    operation: nativeAction,
    outcome: response.code === 200 && response.taskId ? 'accepted' : 'failure',
  })
  operation.finish({
    ...dimensions,
    outcome: response.code === 200 && response.taskId ? 'accepted' : 'failure',
  })
  if (response.code === 200 && response.taskId) registerAcceptedTask(response.taskId, request.mode)
  return response
}

/** [兼容旧专项] 存量配置按钮按目标 UUID 接入；新插件直接提供标准要求树。 */
export async function requestScriptConfigStart(
  taskId: string,
  viewOnly = false,
  targetKind: TaskTargetKind = 'unknown',
  params: TaskParams = {}
): Promise<TaskCreateOut> {
  const mode = viewOnly ? TaskMode.SCRIPT_VIEW : TaskMode.SCRIPT_CONFIG
  const request = await configSessionRequest(taskId, mode, targetKind, params)
  return requestTaskStart(request, { source: 'script_config', target_kind: targetKind })
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
    () => requestMaintenanceStart(userId),
    result => (result.code === 200 && result.taskId ? 'accepted' : 'rejected')
  )
}

// TODO(插件迁移，#1845)：存量维护继续使用兼容入口，操作标识、查询和停止待插件统一适配。
export async function requestMaintenanceStart(
  targetId: string,
  metadata: TaskStartMetadata = {}
): Promise<TaskCreateOut> {
  // 维护已移出调度模式，沿用既有统计类别以保持请求受理口径。
  const operation = beginAnalyticsOperation('task_start_result')
  const dimensions = {
    source: metadata.source ?? ('script_update' as const),
    target_kind: metadata.target_kind ?? ('unknown' as const),
    mode: 'Update' as const,
  }
  try {
    const response = await Service.startOperationApiScriptsOperationsStartPost({ targetId })
    operation.finish({
      ...dimensions,
      outcome: response.code === 200 && response.taskId ? 'accepted' : 'failure',
    })
    return { ...response, taskId: response.taskId ?? '' }
  } catch (error) {
    operation.finish({ ...dimensions, outcome: 'failure' })
    throw error
  }
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
      void reconcileStoppedTask(taskId)
    } catch (error) {
      operation.finish({ ...dimensions, request_outcome: 'failure' })
      throw taskRequestError(error)
    }
  }

  return { startTask, stopTask }
}
