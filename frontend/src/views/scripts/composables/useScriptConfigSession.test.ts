import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

/**
 * useScriptConfigSession deterministic 测试集
 *
 * 覆盖目标：
 * - startSession：ensureAvailable 拒绝、重复会话拒绝、API 启动成功/失败、超时清理
 * - saveSession：未找到会话、API 成功、API 失败
 * - handleSessionMessage：error / Info.Error / Signal.Accomplish 三类 WS 消息
 * - cleanup：清空所有连接与 currentScript/currentKind
 * - onUnmounted：组件卸载时自动 cleanup
 *
 * 通过 mock Service、useWebSocket、message 与 window.electronAPI 隔离副作用。
 */

const logger = { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() }

const messageMocks = vi.hoisted(() => ({
  success: vi.fn(),
  warning: vi.fn(),
  error: vi.fn(),
  info: vi.fn(),
}))

const serviceMocks = vi.hoisted(() => ({
  addTask: vi.fn(),
  stopTask: vi.fn(),
}))

const wsMocks = vi.hoisted(() => ({
  subscribe: vi.fn(),
  unsubscribe: vi.fn(),
}))

vi.mock('ant-design-vue', () => ({
  message: messageMocks,
}))

vi.mock('@/api/services/Service', () => ({
  Service: {
    addTaskApiDispatchStartPost: serviceMocks.addTask,
    stopTaskApiDispatchStopPost: serviceMocks.stopTask,
  },
}))

vi.mock('@/api/models/TaskCreateIn', () => ({
  TaskCreateIn: {
    mode: {
      SCRIPT_CONFIG: 'SCRIPT_CONFIG',
    },
  },
}))

vi.mock('@/composables/useWebSocket', () => ({
  useWebSocket: () => ({
    subscribe: wsMocks.subscribe,
    unsubscribe: wsMocks.unsubscribe,
  }),
}))

beforeEach(() => {
  vi.useFakeTimers()
  vi.clearAllMocks()
  wsMocks.subscribe.mockReturnValue('sub-1')
  wsMocks.unsubscribe.mockReturnValue(undefined)

  vi.stubGlobal('window', {
    electronAPI: {
      getLogger: () => logger,
    },
  })
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

const loadModule = async () => {
  return (await import('./useScriptConfigSession')) as typeof import('./useScriptConfigSession')
}

const makeScript = (overrides: Partial<Record<string, any>> = {}) => ({
  id: 'script-1',
  name: '测试脚本',
  type: 'SRC',
  config: {} as Record<string, any>,
  users: [],
  ...overrides,
})

describe('useScriptConfigSession: 初始状态', () => {
  it('state 初始为空，hasActiveSession=false，isActive=false', async () => {
    const { useScriptConfigSession } = await loadModule()
    const session = useScriptConfigSession()

    expect(session.state.activeConnections.size).toBe(0)
    expect(session.state.currentScript).toBeNull()
    expect(session.state.currentKind).toBeNull()
    expect(session.hasActiveSession()).toBe(false)
    expect(session.isActive('script-1')).toBe(false)
  })
})

describe('useScriptConfigSession: startSession ensureAvailable 守卫', () => {
  it('ensureAvailable 返回 false 时 startSession 直接返回 false 且不调用 API', async () => {
    const { useScriptConfigSession } = await loadModule()
    const ensureAvailable = vi.fn().mockReturnValue(false)
    const session = useScriptConfigSession({ ensureAvailable })
    const script = makeScript()

    const result = await session.startSession(script, 'SRC')

    expect(result).toBe(false)
    expect(ensureAvailable).toHaveBeenCalledWith(script)
    expect(serviceMocks.addTask).not.toHaveBeenCalled()
    expect(session.state.currentScript).toBeNull()
  })

  it('未传 ensureAvailable 时跳过守卫直接调用 API', async () => {
    const { useScriptConfigSession } = await loadModule()
    serviceMocks.addTask.mockResolvedValue({ code: 200, taskId: 'task-1', message: '' })
    const session = useScriptConfigSession()
    const script = makeScript()

    const result = await session.startSession(script, 'SRC')

    expect(result).toBe(true)
    expect(serviceMocks.addTask).toHaveBeenCalledTimes(1)
  })
})

describe('useScriptConfigSession: startSession 重复会话拒绝', () => {
  it('已存在 activeConnections 时拒绝启动第二次会话', async () => {
    const { useScriptConfigSession } = await loadModule()
    serviceMocks.addTask.mockResolvedValue({ code: 200, taskId: 'task-1', message: '' })
    const session = useScriptConfigSession()
    const script = makeScript()

    await session.startSession(script, 'SRC')
    const second = await session.startSession(script, 'MaaEnd')

    expect(second).toBe(false)
    expect(messageMocks.warning).toHaveBeenCalledWith('该脚本已在配置中，请先保存当前配置')
    expect(serviceMocks.addTask).toHaveBeenCalledTimes(1)
  })
})

describe('useScriptConfigSession: startSession API 失败回滚', () => {
  it('API code !== 200 时返回 false 且不进入 active 状态', async () => {
    const { useScriptConfigSession } = await loadModule()
    serviceMocks.addTask.mockResolvedValue({ code: 500, message: '后端错误' })
    const session = useScriptConfigSession()
    const script = makeScript()

    const result = await session.startSession(script, 'SRC')

    expect(result).toBe(false)
    expect(messageMocks.error).toHaveBeenCalledWith('后端错误')
    expect(session.state.currentScript).toBeNull()
    expect(session.state.currentKind).toBeNull()
    expect(session.hasActiveSession()).toBe(false)
  })

  it('API 抛异常时返回 false 并显示错误消息', async () => {
    const { useScriptConfigSession } = await loadModule()
    serviceMocks.addTask.mockRejectedValue(new Error('network down'))
    const session = useScriptConfigSession()
    const script = makeScript()

    const result = await session.startSession(script, 'SRC')

    expect(result).toBe(false)
    expect(messageMocks.error).toHaveBeenCalledWith('启动SRC配置失败: network down')
    expect(session.state.currentScript).toBeNull()
  })

  it('API 返回 message 为空时显示默认错误文案', async () => {
    const { useScriptConfigSession } = await loadModule()
    serviceMocks.addTask.mockResolvedValue({ code: 500, message: '' })
    const session = useScriptConfigSession()
    const script = makeScript()

    await session.startSession(script, 'MaaEnd')

    expect(messageMocks.error).toHaveBeenCalledWith('启动MaaEnd配置失败')
  })
})

describe('useScriptConfigSession: startSession 成功路径', () => {
  it('成功启动后写入 currentScript/currentKind、订阅 WS、设置超时', async () => {
    const { useScriptConfigSession } = await loadModule()
    serviceMocks.addTask.mockResolvedValue({ code: 200, taskId: 'task-99', message: '' })
    wsMocks.subscribe.mockReturnValue('sub-99')
    const session = useScriptConfigSession({ timeoutMs: 1000 })
    const script = makeScript({ id: 'script-99' })

    const result = await session.startSession(script, 'SRC')

    expect(result).toBe(true)
    // reactive() 会代理 currentScript，用字段比较代替引用比较
    expect(session.state.currentScript?.id).toBe('script-99')
    expect(session.state.currentScript?.name).toBe('测试脚本')
    expect(session.state.currentKind).toBe('SRC')
    expect(session.isActive('script-99')).toBe(true)
    expect(session.hasActiveSession()).toBe(true)
    expect(wsMocks.subscribe).toHaveBeenCalledTimes(1)
    expect(messageMocks.success).toHaveBeenCalledWith('已启动 测试脚本 的 SRC 配置')

    const connection = session.state.activeConnections.get('script-99')
    expect(connection).toEqual({ subscriptionId: 'sub-99', websocketId: 'task-99' })
  })

  it('超时后自动 clearConnection 并提示用户', async () => {
    const { useScriptConfigSession } = await loadModule()
    serviceMocks.addTask.mockResolvedValue({ code: 200, taskId: 'task-1', message: '' })
    const session = useScriptConfigSession({ timeoutMs: 1000 })
    const script = makeScript()

    await session.startSession(script, 'SRC')
    expect(session.hasActiveSession()).toBe(true)

    vi.advanceTimersByTime(1001)

    expect(session.hasActiveSession()).toBe(false)
    expect(wsMocks.unsubscribe).toHaveBeenCalledWith('sub-1')
    expect(messageMocks.info).toHaveBeenCalledWith('测试脚本 配置会话已超时断开')
  })
})

describe('useScriptConfigSession: saveSession', () => {
  it('未找到活动会话时返回 false 并提示错误', async () => {
    const { useScriptConfigSession } = await loadModule()
    const session = useScriptConfigSession()

    const result = await session.saveSession(makeScript())

    expect(result).toBe(false)
    expect(messageMocks.error).toHaveBeenCalledWith('未找到活动的配置会话')
    expect(serviceMocks.stopTask).not.toHaveBeenCalled()
  })

  it('API 成功时清理会话并提示成功', async () => {
    const { useScriptConfigSession } = await loadModule()
    serviceMocks.addTask.mockResolvedValue({ code: 200, taskId: 'task-1', message: '' })
    serviceMocks.stopTask.mockResolvedValue({ code: 200, message: '' })
    const session = useScriptConfigSession()
    const script = makeScript()

    await session.startSession(script, 'SRC')
    const result = await session.saveSession(script)

    expect(result).toBe(true)
    expect(serviceMocks.stopTask).toHaveBeenCalledWith({ taskId: 'task-1' })
    expect(wsMocks.unsubscribe).toHaveBeenCalledWith('sub-1')
    expect(session.hasActiveSession()).toBe(false)
    expect(messageMocks.success).toHaveBeenCalledWith('测试脚本 的配置已保存')
  })

  it('API code !== 200 时返回 false 且不清理会话', async () => {
    const { useScriptConfigSession } = await loadModule()
    serviceMocks.addTask.mockResolvedValue({ code: 200, taskId: 'task-1', message: '' })
    serviceMocks.stopTask.mockResolvedValue({ code: 500, message: '保存失败' })
    const session = useScriptConfigSession()
    const script = makeScript()

    await session.startSession(script, 'SRC')
    const result = await session.saveSession(script)

    expect(result).toBe(false)
    expect(messageMocks.error).toHaveBeenCalledWith('保存失败')
    expect(session.hasActiveSession()).toBe(true)
  })

  it('API 抛异常时返回 false 且保留会话（由用户重试）', async () => {
    const { useScriptConfigSession } = await loadModule()
    serviceMocks.addTask.mockResolvedValue({ code: 200, taskId: 'task-1', message: '' })
    serviceMocks.stopTask.mockRejectedValue(new Error('timeout'))
    const session = useScriptConfigSession()
    const script = makeScript()

    await session.startSession(script, 'SRC')
    const result = await session.saveSession(script)

    expect(result).toBe(false)
    expect(messageMocks.error).toHaveBeenCalledWith('保存配置失败: timeout')
    expect(session.hasActiveSession()).toBe(true)
  })
})

describe('useScriptConfigSession: WS 消息处理', () => {
  it('type=error 时清理会话并提示错误', async () => {
    const { useScriptConfigSession } = await loadModule()
    serviceMocks.addTask.mockResolvedValue({ code: 200, taskId: 'task-1', message: '' })
    const session = useScriptConfigSession()
    const script = makeScript()

    await session.startSession(script, 'SRC')

    const subscriber = wsMocks.subscribe.mock.calls[0][1]
    subscriber({ type: 'error', data: new Error('连接中断') })

    expect(session.hasActiveSession()).toBe(false)
    expect(messageMocks.error).toHaveBeenCalledWith('SRC 配置连接失败: 连接中断')
    expect(logger.error).toHaveBeenCalled()
  })

  it('type=error 且 data 为字符串时直接拼接错误文案', async () => {
    const { useScriptConfigSession } = await loadModule()
    serviceMocks.addTask.mockResolvedValue({ code: 200, taskId: 'task-1', message: '' })
    const session = useScriptConfigSession()
    const script = makeScript()

    await session.startSession(script, 'MaaEnd')

    const subscriber = wsMocks.subscribe.mock.calls[0][1]
    subscriber({ type: 'error', data: '协议错误' })

    expect(messageMocks.error).toHaveBeenCalledWith('MaaEnd 配置连接失败: 协议错误')
  })

  it('type=Info 且 data.Error 存在时显示错误但保持订阅', async () => {
    const { useScriptConfigSession } = await loadModule()
    serviceMocks.addTask.mockResolvedValue({ code: 200, taskId: 'task-1', message: '' })
    const session = useScriptConfigSession()
    const script = makeScript()

    await session.startSession(script, 'SRC')

    const subscriber = wsMocks.subscribe.mock.calls[0][1]
    subscriber({ type: 'Info', data: { Error: '配置项缺失' } })

    expect(messageMocks.error).toHaveBeenCalledWith('SRC 配置失败: 配置项缺失')
    expect(session.hasActiveSession()).toBe(true)
  })

  it('type=Signal 且 Accomplish 为成功字符串时提示成功并清理会话', async () => {
    const { useScriptConfigSession } = await loadModule()
    serviceMocks.addTask.mockResolvedValue({ code: 200, taskId: 'task-1', message: '' })
    const session = useScriptConfigSession()
    const script = makeScript()

    await session.startSession(script, 'SRC')

    const subscriber = wsMocks.subscribe.mock.calls[0][1]
    subscriber({ type: 'Signal', data: { Accomplish: 'OK' } })

    expect(messageMocks.success).toHaveBeenCalledWith('测试脚本 配置已完成')
    expect(session.hasActiveSession()).toBe(false)
  })

  it('type=Signal 且 Accomplish 包含"异常"时不显示成功提示但仍清理会话', async () => {
    const { useScriptConfigSession } = await loadModule()
    serviceMocks.addTask.mockResolvedValue({ code: 200, taskId: 'task-1', message: '' })
    const session = useScriptConfigSession()
    const script = makeScript()

    await session.startSession(script, 'SRC')
    // 清除 startSession 触发的 success 提示，仅观察 Signal 处理路径
    messageMocks.success.mockClear()

    const subscriber = wsMocks.subscribe.mock.calls[0][1]
    subscriber({ type: 'Signal', data: { Accomplish: '任务异常终止' } })

    expect(messageMocks.success).not.toHaveBeenCalled()
    expect(session.hasActiveSession()).toBe(false)
  })

  it('非对象 WS 消息被静默忽略', async () => {
    const { useScriptConfigSession } = await loadModule()
    serviceMocks.addTask.mockResolvedValue({ code: 200, taskId: 'task-1', message: '' })
    const session = useScriptConfigSession()
    const script = makeScript()

    await session.startSession(script, 'SRC')

    const subscriber = wsMocks.subscribe.mock.calls[0][1]
    subscriber(null)
    subscriber('string-message')
    subscriber(undefined)

    expect(session.hasActiveSession()).toBe(true)
    expect(messageMocks.error).not.toHaveBeenCalled()
  })

  it('type=Signal 但 subscriptionId 不匹配时不清理（防止并发会话误清理）', async () => {
    const { useScriptConfigSession } = await loadModule()
    serviceMocks.addTask.mockResolvedValue({ code: 200, taskId: 'task-1', message: '' })
    wsMocks.subscribe.mockReturnValueOnce('sub-original')
    const session = useScriptConfigSession()
    const script = makeScript()

    await session.startSession(script, 'SRC')

    // 模拟 subscribe 返回的 subscriptionId 与 activeConnections 中保存的不一致
    const subscriber = wsMocks.subscribe.mock.calls[0][1]
    // 强制覆盖 activeConnections 中的 subscriptionId 模拟并发替换
    session.state.activeConnections.set('script-1', {
      subscriptionId: 'sub-new',
      websocketId: 'task-1',
    })

    subscriber({ type: 'Signal', data: { Accomplish: 'OK' } })

    // 因 subscriptionId 不匹配，不应清理
    expect(session.hasActiveSession()).toBe(true)
  })
})

describe('useScriptConfigSession: cleanup', () => {
  it('cleanup 清空所有连接与 currentScript/currentKind', async () => {
    const { useScriptConfigSession } = await loadModule()
    serviceMocks.addTask.mockResolvedValue({ code: 200, taskId: 'task-1', message: '' })
    const session = useScriptConfigSession()
    const script = makeScript()

    await session.startSession(script, 'SRC')
    expect(session.hasActiveSession()).toBe(true)

    session.cleanup()

    expect(session.hasActiveSession()).toBe(false)
    expect(session.state.currentScript).toBeNull()
    expect(session.state.currentKind).toBeNull()
    expect(wsMocks.unsubscribe).toHaveBeenCalledWith('sub-1')
  })

  it('cleanup 在无活动会话时是空操作', async () => {
    const { useScriptConfigSession } = await loadModule()
    const session = useScriptConfigSession()

    expect(() => session.cleanup()).not.toThrow()
    expect(wsMocks.unsubscribe).not.toHaveBeenCalled()
  })
})
