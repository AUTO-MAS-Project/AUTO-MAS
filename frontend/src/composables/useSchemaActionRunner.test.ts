import { beforeEach, describe, expect, it, vi } from 'vitest'

const axiosMocks = vi.hoisted(() => ({
  request: vi.fn(),
}))

const messageMocks = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
  warning: vi.fn(),
}))

const websocketMocks = vi.hoisted(() => ({
  handler: null as
    | null
    | ((message: { id?: string; type: string; data?: unknown }) => Promise<void>),
  subscribe: vi.fn(),
  unsubscribe: vi.fn(),
}))

vi.mock('axios', () => ({
  default: {
    request: axiosMocks.request,
    isAxiosError: (error: unknown) =>
      Boolean(error && typeof error === 'object' && 'isAxiosError' in error),
  },
}))

vi.mock('ant-design-vue', () => ({
  message: messageMocks,
}))

vi.mock('@/api', () => ({
  OpenAPI: { BASE: 'http://127.0.0.1:36163' },
}))

vi.mock('@/composables/useWebSocket', () => ({
  useWebSocket: () => ({
    subscribe: websocketMocks.subscribe.mockImplementation(
      (
        _filter: { id?: string; type?: string },
        handler: (message: { id?: string; type: string; data?: unknown }) => Promise<void>
      ) => {
        websocketMocks.handler = handler
        return 'schema_session_subscription'
      }
    ),
    unsubscribe: websocketMocks.unsubscribe,
  }),
}))

vi.mock('vue', async () => {
  const actual = await vi.importActual<typeof import('vue')>('vue')
  return { ...actual, onUnmounted: vi.fn() }
})

const logger = {
  debug: vi.fn(),
  info: vi.fn(),
  warn: vi.fn(),
  error: vi.fn(),
}

const loadRunner = async () => {
  vi.resetModules()
  const { useSchemaActionRunner } = await import('./useSchemaActionRunner')
  return useSchemaActionRunner()
}

const sessionField = {
  type: 'button',
  action: {
    label: '准备运行环境',
    path: '/api/dispatch/start',
    method: 'POST',
    session: {
      response_task_id_key: 'taskId',
      stop_path: '/api/dispatch/stop',
      stop_method: 'POST',
      stop_payload: { taskId: '{{session.websocketId}}' },
    },
  },
}

beforeEach(() => {
  vi.clearAllMocks()
  websocketMocks.handler = null
  vi.stubGlobal('window', {
    electronAPI: { getLogger: () => logger },
    setTimeout,
    clearTimeout,
  })
})

describe('useSchemaActionRunner WS v2 会话完成协议', () => {
  it('task.completed 结束成功会话并清理订阅', async () => {
    axiosMocks.request.mockResolvedValueOnce({ data: { taskId: 'task-success' } })
    const runner = await loadRunner()

    await runner.runFieldAction('prepare', sessionField, {})
    expect(runner.sessionVisible.value).toBe(true)
    messageMocks.success.mockClear()

    await websocketMocks.handler?.({
      id: 'task-success',
      type: 'task.completed',
      data: { result: '执行完成', task_info: [] },
    })

    expect(messageMocks.success).toHaveBeenCalledWith('准备运行环境已完成')
    expect(runner.sessionVisible.value).toBe(false)
    expect(websocketMocks.unsubscribe).toHaveBeenCalledWith('schema_session_subscription')
  })

  it('task.notice error 展示具体错误，随后 task.completed 只清理而不假报成功', async () => {
    axiosMocks.request.mockResolvedValueOnce({ data: { taskId: 'task-error' } })
    const runner = await loadRunner()

    await runner.runFieldAction('prepare', sessionField, {})
    messageMocks.success.mockClear()
    await websocketMocks.handler?.({
      id: 'task-error',
      type: 'task.notice',
      data: { level: 'error', message: '项目目录缺少 interface.json' },
    })
    await websocketMocks.handler?.({
      id: 'task-error',
      type: 'task.completed',
      data: { result: '任务未加载', task_info: [] },
    })

    expect(messageMocks.error).toHaveBeenCalledWith('项目目录缺少 interface.json')
    expect(messageMocks.success).not.toHaveBeenCalled()
    expect(runner.sessionVisible.value).toBe(false)
  })

  it('停止接口报告任务已不存在时仍清理本地会话遮罩', async () => {
    axiosMocks.request
      .mockResolvedValueOnce({ data: { taskId: 'task-already-finished' } })
      .mockRejectedValueOnce({
        isAxiosError: true,
        message: 'Request failed with status code 500',
        response: { status: 500, data: { detail: '未找到对应任务' } },
      })
    const runner = await loadRunner()

    await runner.runFieldAction('prepare', sessionField, {})
    expect(runner.sessionVisible.value).toBe(true)
    await runner.stopActiveSession()

    expect(runner.sessionVisible.value).toBe(false)
    expect(websocketMocks.unsubscribe).toHaveBeenCalledWith('schema_session_subscription')
    expect(messageMocks.error).not.toHaveBeenCalled()
  })
})
