import axios from 'axios'
import { computed, onUnmounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import { OpenAPI } from '@/api'
import { useWebSocket, type WebSocketBaseMessage } from '@/composables/useWebSocket'
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

const resolveRequestUrl = (path: string) => (path.startsWith('/') ? `${OpenAPI.BASE}${path}` : `${OpenAPI.BASE}/${path}`)

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

export const useSchemaActionRunner = (options?: {
  onRefresh?: () => Promise<void> | void
}) => {
  const { subscribe, unsubscribe } = useWebSocket()
  const actionLoadingId = ref('')
  const sessionStopping = ref(false)
  const activeSession = ref<ActiveSession | null>(null)

  const sessionVisible = computed(() => Boolean(activeSession.value))
  const sessionTitle = computed(
    () => activeSession.value?.session.overlay_title || activeSession.value?.action.label || '正在执行配置动作'
  )
  const sessionDescription = computed(
    () =>
      activeSession.value?.session.overlay_description ||
      '请在外部窗口完成相关设置，然后回到这里结束会话。'
  )
  const sessionStopLabel = computed(
    () => activeSession.value?.session.stop_label || '结束会话'
  )

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

    const completionType = session.completion_type || 'Signal'
    const completionField = session.completion_field || 'Accomplish'
    const errorField = session.error_field || 'Error'

    const subscriptionId = subscribe({ id: websocketId }, async (wsMessage: WebSocketBaseMessage) => {
      if (wsMessage.type === 'error') {
        const errorMsg =
          wsMessage.data instanceof Error ? wsMessage.data.message : String(wsMessage.data)
        message.error(`会话连接失败: ${errorMsg}`)
        logger.error(`会话连接失败: ${errorMsg}`)
        await cleanupSession(false)
        return
      }

      if (
        wsMessage.type === 'Info' &&
        wsMessage.data &&
        typeof wsMessage.data === 'object' &&
        errorField in wsMessage.data
      ) {
        message.error(String((wsMessage.data as Record<string, unknown>)[errorField] || '会话执行失败'))
        return
      }

      if (
        wsMessage.type === completionType &&
        wsMessage.data &&
        typeof wsMessage.data === 'object' &&
        completionField in wsMessage.data
      ) {
        const result = String((wsMessage.data as Record<string, unknown>)[completionField] || '')
        if (result && !result.includes('异常') && !result.includes('错误')) {
          const successText = resolveTemplateValue(
            session.success_message || `${action.label || '配置动作'}已完成`,
            sessionContext
          )
          message.success(String(successText))
        }
        await cleanupSession(Boolean(action.refresh))
      }
    })

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
      const payload = resolveTemplateValue(action.payload ?? {}, context)
      const data = await requestAction<any>(action.path, method, payload)
      unwrapResponseError(data)

      if (action.session) {
        await bindSessionEvents(field, action, action.session, context, data)
        const startText = resolveTemplateValue(
          action.session.start_message || `${action.label || '配置动作'}已启动`,
          context
        )
        message.success(String(startText))
      } else {
        message.success(`${action.label || '配置动作'}已执行`)
        if (action.refresh && options?.onRefresh) {
          await options.onRefresh()
        }
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
        current.session.stop_message ||
          (fromTimeout ? '配置会话已自动结束' : '配置会话已结束'),
        current.context
      )
      message.success(String(stopMessage))
      await cleanupSession(Boolean(current.action.refresh))
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
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
