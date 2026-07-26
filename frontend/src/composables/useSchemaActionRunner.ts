import axios from 'axios'
import { computed, onUnmounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import { OpenAPI } from '@/api'
import { useWebSocket, type WebSocketBaseMessage } from '@/composables/useWebSocket'
import {
  WS_TASK_COMPLETED,
  WS_TASK_NOTICE,
  type WSTaskCompletedData,
  type WSTaskNoticeData,
} from '@/services/websocket/types'
import type {
  SchemaActionDefinition,
  SchemaActionSessionDefinition,
  SchemaFieldDefinition,
} from '@/types/schemaForm'

const logger = window.electronAPI.getLogger('SchemaActionRunner')

type ActionContext = Record<string, any>

type ActiveSession = {
  actionId: string
  action: SchemaActionDefinition
  session: SchemaActionSessionDefinition
  context: ActionContext
  subscriptionId: string | null
  websocketId: string
  timeoutId: number | null
}

const isPlainObject = (value: unknown): value is Record<string, unknown> =>
  Object.prototype.toString.call(value) === '[object Object]'

const getErrorMessage = (error: unknown): string => {
  if (axios.isAxiosError(error)) {
    const payload = error.response?.data
    if (isPlainObject(payload)) {
      for (const key of ['detail', 'message', 'error']) {
        const value = payload[key]
        if (typeof value === 'string' && value.trim()) return value
      }
    }
  }
  return error instanceof Error ? error.message : String(error)
}

const isAlreadyFinishedSessionError = (error: unknown, errorMessage: string): boolean => {
  const status = axios.isAxiosError(error) ? error.response?.status : undefined
  return (
    status === 404 ||
    status === 410 ||
    /未找到对应任务|任务(?:已经)?(?:结束|完成|不存在)|task\s+not\s+found/i.test(errorMessage)
  )
}

const taskResultLooksFailed = (result: string): boolean =>
  /异常|错误|失败|\berror\b|\bfailed\b/i.test(result)
const getContextValue = (context: ActionContext, path: string): unknown => {
  return path.split('.').reduce<unknown>((current, segment) => {
    if (current && typeof current === 'object' && segment in (current as Record<string, unknown>)) {
      return (current as Record<string, unknown>)[segment]
    }
    return undefined
  }, context)
}

const resolveTemplateValue = (value: unknown, context: ActionContext): unknown => {
  if (typeof value === 'string') {
    const exactMatch = value.match(/^\{\{\s*([^}]+)\s*\}\}$/)
    if (exactMatch) {
      return getContextValue(context, exactMatch[1].trim())
    }
    return value.replace(/\{\{\s*([^}]+)\s*\}\}/g, (_, expr: string) => {
      const resolved = getContextValue(context, expr.trim())
      return resolved == null ? '' : String(resolved)
    })
  }

  if (Array.isArray(value)) {
    return value.map(item => resolveTemplateValue(item, context))
  }

  if (isPlainObject(value)) {
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [key, resolveTemplateValue(item, context)])
    )
  }

  return value
}

const ensureAction = (fieldSchema: SchemaFieldDefinition): SchemaActionDefinition | null => {
  const action = fieldSchema.action || fieldSchema.button
  if (!action || typeof action !== 'object') {
    return null
  }
  return action
}

const resolveRequestUrl = (path: string) =>
  path.startsWith('/') ? `${OpenAPI.BASE}${path}` : `${OpenAPI.BASE}/${path}`

const requestAction = async <T = any>(
  path: string,
  method: string,
  payload: unknown
): Promise<T> => {
  const normalizedMethod = method.toUpperCase()
  const { data } = await axios.request<T>({
    method: normalizedMethod,
    url: resolveRequestUrl(path),
    params: normalizedMethod === 'GET' ? payload : undefined,
    data: normalizedMethod === 'GET' ? undefined : payload,
  })
  return data
}

const unwrapResponseError = (data: any) => {
  if (data && typeof data === 'object' && 'code' in data && Number(data.code) !== 200) {
    throw new Error(String(data.message || '动作执行失败'))
  }
}

const toSerializableValue = <T>(value: T): T => {
  if (value == null) {
    return value
  }
  return JSON.parse(JSON.stringify(value)) as T
}

export const useSchemaActionRunner = (options?: {
  onRefresh?: () => Promise<void> | void
  onActionSuccess?: (params: {
    field: string
    action: SchemaActionDefinition
    fieldSchema: SchemaFieldDefinition
    context: ActionContext
    response: any
  }) => Promise<boolean | void> | boolean | void
}) => {
  const { subscribe, unsubscribe } = useWebSocket()
  const actionLoadingId = ref('')
  const sessionStopping = ref(false)
  const activeSession = ref<ActiveSession | null>(null)

  const sessionVisible = computed(() => Boolean(activeSession.value))
  const sessionTitle = computed(
    () =>
      activeSession.value?.session.overlay_title ||
      activeSession.value?.action.label ||
      '正在执行配置动作'
  )
  const sessionDescription = computed(
    () =>
      activeSession.value?.session.overlay_description ||
      '请在外部窗口完成相关设置，然后回到这里结束会话。'
  )
  const sessionStopLabel = computed(() => activeSession.value?.session.stop_label || '结束会话')

  const cleanupSession = async (shouldRefresh = false) => {
    const current = activeSession.value
    if (!current) {
      return
    }

    if (current.timeoutId) {
      window.clearTimeout(current.timeoutId)
    }
    if (current.subscriptionId) {
      unsubscribe(current.subscriptionId)
    }

    activeSession.value = null
    sessionStopping.value = false

    if (shouldRefresh && options?.onRefresh) {
      await options.onRefresh()
    }
  }

  const bindSessionEvents = async (
    actionId: string,
    action: SchemaActionDefinition,
    session: SchemaActionSessionDefinition,
    context: ActionContext,
    response: any
  ) => {
    const responseTaskIdKey = session.response_task_id_key || 'taskId'
    const websocketIdRaw = response?.[responseTaskIdKey]
    const websocketId = typeof websocketIdRaw === 'string' ? websocketIdRaw : ''
    if (!websocketId) {
      throw new Error(`会话动作缺少 ${responseTaskIdKey} 返回值`)
    }

    const sessionContext = {
      ...context,
      session: {
        websocketId,
      },
    }

    const completionType = session.completion_type?.trim() || ''
    const completionField = session.completion_field || 'Accomplish'
    const errorField = session.error_field || 'Error'
    let sessionFailed = false

    const showSuccess = () => {
      const successText = resolveTemplateValue(
        session.success_message || `${action.label || '配置动作'}已完成`,
        sessionContext
      )
      message.success(String(successText))
    }

    const subscriptionId = subscribe(
      { id: websocketId },
      async (wsMessage: WebSocketBaseMessage) => {
        if (wsMessage.type === 'error') {
          const errorMsg =
            wsMessage.data instanceof Error ? wsMessage.data.message : String(wsMessage.data)
          message.error(`会话连接失败: ${errorMsg}`)
          logger.error(`会话连接失败: ${errorMsg}`)
          await cleanupSession(false)
          return
        }

        if (wsMessage.type === WS_TASK_NOTICE && isPlainObject(wsMessage.data)) {
          const notice = wsMessage.data as Partial<WSTaskNoticeData>
          if (notice.level === 'error') {
            sessionFailed = true
            const errorMsg = notice.message || '会话执行失败'
            message.error(errorMsg)
            logger.error(`Schema 会话任务失败: ${errorMsg}`)
          } else if (notice.level === 'warning' && notice.message) {
            message.warning(notice.message)
          }
          return
        }

        if (wsMessage.type === WS_TASK_COMPLETED) {
          const completed = isPlainObject(wsMessage.data)
            ? (wsMessage.data as Partial<WSTaskCompletedData>)
            : {}
          const result = typeof completed.result === 'string' ? completed.result : ''
          const failed = sessionFailed || taskResultLooksFailed(result)
          if (!failed) {
            showSuccess()
          } else if (!sessionFailed && result) {
            message.error(result)
          }
          await cleanupSession(Boolean(action.refresh))
          return
        }

        // 显式声明旧协议 completion_type 的 schema 仍保持可配置兼容；
        // 未声明时以 WS v2 的 task.completed 作为唯一正式完成信号。
        if (
          wsMessage.type === 'Info' &&
          isPlainObject(wsMessage.data) &&
          errorField in wsMessage.data
        ) {
          sessionFailed = true
          message.error(String(wsMessage.data[errorField] || '会话执行失败'))
          return
        }

        if (
          completionType &&
          wsMessage.type === completionType &&
          isPlainObject(wsMessage.data) &&
          completionField in wsMessage.data
        ) {
          const result = String(wsMessage.data[completionField] || '')
          if (!sessionFailed && !taskResultLooksFailed(result)) {
            showSuccess()
          }
          await cleanupSession(Boolean(action.refresh))
        }
      }
    )

    let timeoutId: number | null = null
    const timeoutMs = Number(session.timeout_ms || 0)
    if (timeoutMs > 0 && session.timeout_auto_stop) {
      timeoutId = window.setTimeout(async () => {
        const timeoutText = resolveTemplateValue(
          session.timeout_message || '当前配置会话已超时，正在自动结束会话...',
          sessionContext
        )
        message.warning(String(timeoutText))
        await stopActiveSession(true)
      }, timeoutMs)
    }

    activeSession.value = {
      actionId,
      action,
      session,
      context: sessionContext,
      subscriptionId,
      websocketId,
      timeoutId,
    }
  }

  const runFieldAction = async (
    field: string,
    fieldSchema: SchemaFieldDefinition,
    context: ActionContext
  ) => {
    const action = ensureAction(fieldSchema)
    if (!action || !action.path) {
      message.warning('Schema 按钮缺少 action.path 声明')
      return
    }

    actionLoadingId.value = field
    try {
      const method = action.method || 'POST'
      let actionContext = context
      if (action.file_picker) {
        const filters = toSerializableValue(action.file_picker.filters ?? [])
        const selectedFiles = await window.electronAPI.selectFile(filters)
        const pickedFile = Array.isArray(selectedFiles) ? selectedFiles[0] : null
        if (!pickedFile) {
          return
        }
        actionContext = {
          ...context,
          pickedFile,
        }
      }

      const payload = resolveTemplateValue(action.payload ?? {}, actionContext)
      const data = await requestAction<any>(action.path, method, payload)
      unwrapResponseError(data)

      if (action.session) {
        await bindSessionEvents(field, action, action.session, actionContext, data)
        const startText = resolveTemplateValue(
          action.session.start_message || `${action.label || '配置动作'}已启动`,
          actionContext
        )
        message.success(String(startText))
      } else {
        const handledRefresh = await options?.onActionSuccess?.({
          field,
          action,
          fieldSchema,
          context: actionContext,
          response: data,
        })
        if (action.refresh && !handledRefresh && options?.onRefresh) {
          await options.onRefresh()
        }
        message.success(`${action.label || '配置动作'}已执行`)
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`执行 schema 动作失败: field=${field}, error=${errorMsg}`)
      message.error(errorMsg)
    } finally {
      actionLoadingId.value = ''
    }
  }

  const stopActiveSession = async (fromTimeout = false) => {
    const current = activeSession.value
    if (!current || sessionStopping.value) {
      return
    }

    sessionStopping.value = true
    try {
      const stopPath = current.session.stop_path
      if (stopPath) {
        const stopMethod = current.session.stop_method || 'POST'
        const payload = resolveTemplateValue(current.session.stop_payload ?? {}, current.context)
        const data = await requestAction<any>(stopPath, stopMethod, payload)
        unwrapResponseError(data)
      }

      const stopMessage = resolveTemplateValue(
        current.session.stop_message || (fromTimeout ? '配置会话已自动结束' : '配置会话已结束'),
        current.context
      )
      message.success(String(stopMessage))
      await cleanupSession(Boolean(current.action.refresh))
    } catch (error) {
      const errorMsg = getErrorMessage(error)
      if (isAlreadyFinishedSessionError(error, errorMsg)) {
        logger.warn(`后端任务已结束，清理本地 schema 会话: ${errorMsg}`)
        await cleanupSession(Boolean(current.action.refresh))
        return
      }
      logger.error(`结束 schema 会话失败: ${errorMsg}`)
      message.error(errorMsg)
      sessionStopping.value = false
    }
  }

  onUnmounted(() => {
    void cleanupSession(false)
  })

  return {
    actionLoadingId,
    sessionVisible,
    sessionTitle,
    sessionDescription,
    sessionStopLabel,
    sessionStopping,
    runFieldAction,
    stopActiveSession,
  }
}
