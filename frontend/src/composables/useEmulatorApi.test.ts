/**
 * useEmulatorManagement 行为与契约测试（Node 环境，无 DOM）。
 *
 * 覆盖 Lane 10 要求的 provider matrix、轮询、retry、timeout、partial、
 * 卸载后迟到响应、失败传播等场景。所有测试使用 fake Service，不启动真实
 * 后端/模拟器/游戏。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { effectScope, nextTick } from 'vue'

const logger = { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() }

const mockApi = vi.hoisted(() => ({
  getEmulatorApiEmulatorGetPost: vi.fn(),
  addEmulatorApiEmulatorAddPost: vi.fn(),
  updateEmulatorApiEmulatorUpdatePost: vi.fn(),
  deleteEmulatorApiEmulatorDeletePost: vi.fn(),
  operationEmulatorApiEmulatorOperatePost: vi.fn(),
  getStatusApiEmulatorStatusPost: vi.fn(),
  searchEmulatorsApiEmulatorEmulatorSearchPost: vi.fn(),
}))

const messageMock = vi.hoisted(() => ({
  info: vi.fn(),
  success: vi.fn(),
  error: vi.fn(),
  warning: vi.fn(),
}))
const websocketMocks = vi.hoisted(() => ({
  handler: null as
    | null
    | ((message: { id: string; type: string; data: Record<string, unknown> }) => void),
  subscribe: vi.fn(),
  unsubscribe: vi.fn(),
}))

const unmountCallbacks = vi.hoisted(() => [] as Array<() => void>)

vi.mock('ant-design-vue', () => ({
  message: messageMock,
}))

vi.mock('@/api', () => ({
  Service: mockApi,
  EmulatorOperateIn: { operate: { OPEN: 'open', CLOSE: 'close', SHOW: 'show' } },
}))

vi.mock('@/api/core/CancelablePromise', () => ({
  CancelError: class CancelError extends Error {
    constructor(message: string) {
      super(message)
      this.name = 'CancelError'
    }
    get isCancelled() {
      return true
    }
  },
}))
vi.mock('@/services/websocket/subscriptions', () => ({
  subscribe: websocketMocks.subscribe.mockImplementation(
    (
      _filter: { id?: string; type?: string },
      handler: (message: { id: string; type: string; data: Record<string, unknown> }) => void
    ) => {
      websocketMocks.handler = handler
      return 'emulator_notice_subscription'
    }
  ),
  unsubscribe: websocketMocks.unsubscribe,
}))

vi.mock('@vueuse/core', () => ({
  useEventListener: vi.fn(),
}))

// useEmulatorManagement 在 Node 环境下调用 onUnmounted 会产生 Vue warn。
// 这里将 onUnmounted 替换为空函数，保持其他 Vue API 为真实实现。
vi.mock('vue', async () => {
  const actual = await vi.importActual<typeof import('vue')>('vue')
  return {
    ...actual,
    onUnmounted: vi.fn((callback: () => void) => unmountCallbacks.push(callback)),
  }
})

const loadComposable = async () => {
  vi.resetModules()
  return await import('./useEmulatorApi')
}

/**
 * 在 effect scope 中创建 useEmulatorManagement 实例，避免 Node 环境下
 * onUnmounted 警告，并确保响应式 effect 可被正确清理。
 */
const createManagement = async (pollOptions: Record<string, unknown> = {}) => {
  const { useEmulatorManagement } = await loadComposable()
  const scope = effectScope()
  const instance = scope.run(() => useEmulatorManagement(pollOptions))
  return { scope, instance }
}

beforeEach(() => {
  websocketMocks.handler = null
  websocketMocks.subscribe.mockClear()
  websocketMocks.unsubscribe.mockClear()
  unmountCallbacks.length = 0
  // useEmulatorManagement 内部读取 localStorage 并通过 useEventListener 监听 document/window。
  // Node 环境无 DOM，需提前 stub。
  vi.stubGlobal('localStorage', {
    getItem: vi.fn(() => ''),
    setItem: vi.fn(),
    removeItem: vi.fn(),
  })
  vi.stubGlobal('document', {
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  })
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('useEmulatorApi 能力矩阵 (FE-CAPABILITY-*)', () => {
  beforeEach(() => {
    vi.stubGlobal('window', {
      electronAPI: { getLogger: () => logger },
    })
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('general 类型支持 open/close/show/boss_key，不支持 force_kill', async () => {
    const { getEmulatorCapabilities } = await loadComposable()
    expect(getEmulatorCapabilities('general')).toEqual({
      open: true,
      close: true,
      show: true,
      force_kill: false,
      boss_key: true,
    })
  })

  it('mumu 类型支持 open/close/show/force_kill，不支持 boss_key', async () => {
    const { getEmulatorCapabilities } = await loadComposable()
    expect(getEmulatorCapabilities('mumu')).toEqual({
      open: true,
      close: true,
      show: true,
      force_kill: true,
      boss_key: false,
    })
  })

  it('ldplayer 类型支持 open/close/show/boss_key，不支持 force_kill', async () => {
    const { getEmulatorCapabilities } = await loadComposable()
    expect(getEmulatorCapabilities('ldplayer')).toEqual({
      open: true,
      close: true,
      show: true,
      force_kill: false,
      boss_key: true,
    })
  })

  it('未选择类型时没有任何能力', async () => {
    const { getEmulatorCapabilities } = await loadComposable()
    expect(getEmulatorCapabilities('')).toEqual({
      open: false,
      close: false,
      show: false,
      force_kill: false,
      boss_key: false,
    })
  })
})

describe('useEmulatorApi 设备操作状态 (FE-ACTION-*)', () => {
  beforeEach(() => {
    vi.stubGlobal('window', {
      electronAPI: { getLogger: () => logger },
    })
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('mumu 不支持 boss_key，前端按钮应 disabled 并提示原因（inferred）', async () => {
    const { getEmulatorCapabilities } = await loadComposable()
    expect(getEmulatorCapabilities('mumu').boss_key).toBe(false)
  })

  it('未配置路径时 open 操作 disabled 并提示路径缺失', async () => {
    const { getDeviceActionState, DeviceStatus } = await loadComposable()
    const state = getDeviceActionState('open', DeviceStatus.OFFLINE, 'general', false, false)
    expect(state.disabled).toBe(true)
    expect(state.reason).toContain('路径')
  })

  it('操作进行中显示 loading', async () => {
    const { getDeviceActionState, DeviceStatus } = await loadComposable()
    const state = getDeviceActionState('open', DeviceStatus.OFFLINE, 'general', true, true)
    expect(state.loading).toBe(true)
    expect(state.disabled).toBe(true)
  })

  it('在线设备不可启动', async () => {
    const { getDeviceActionState, DeviceStatus } = await loadComposable()
    const state = getDeviceActionState('open', DeviceStatus.ONLINE, 'general', true, false)
    expect(state.disabled).toBe(true)
    expect(state.reason).toContain('在线')
  })

  it('离线设备不可关闭', async () => {
    const { getDeviceActionState, DeviceStatus } = await loadComposable()
    const state = getDeviceActionState('close', DeviceStatus.OFFLINE, 'general', true, false)
    expect(state.disabled).toBe(true)
    expect(state.reason).toContain('离线')
  })

  it('仅在线设备可显示', async () => {
    const { getDeviceActionState, DeviceStatus } = await loadComposable()
    expect(getDeviceActionState('show', DeviceStatus.ONLINE, 'general', true, false).disabled).toBe(
      false
    )
    expect(
      getDeviceActionState('show', DeviceStatus.OFFLINE, 'general', true, false).disabled
    ).toBe(true)
  })
})

describe('useEmulatorApi withTimeoutAndRetry (FE-TIMEOUT-*)', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.stubGlobal('window', {
      electronAPI: { getLogger: () => logger },
    })
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('首次成功立即返回', async () => {
    const { withTimeoutAndRetry } = await loadComposable()
    const promise = withTimeoutAndRetry(() => Promise.resolve({ code: 200, status: 'ok' }), {
      timeoutMs: 1000,
      retries: 0,
      retryDelayMs: 100,
      label: '首次成功',
    })
    await expect(promise).resolves.toMatchObject({ code: 200 })
  })

  it('失败后重试并最终成功', async () => {
    const { withTimeoutAndRetry } = await loadComposable()
    let calls = 0
    const promise = withTimeoutAndRetry(
      () => {
        calls++
        if (calls === 1) return Promise.reject(new Error('transient'))
        return Promise.resolve({ code: 200, status: 'ok' })
      },
      { timeoutMs: 1000, retryDelayMs: 100, retries: 2, label: '重试成功' }
    )

    await vi.advanceTimersByTimeAsync(200)
    await expect(promise).resolves.toMatchObject({ code: 200 })
    expect(calls).toBe(2)
  })

  it('超时后取消并重试，最终抛出超时错误', async () => {
    const { withTimeoutAndRetry } = await loadComposable()
    let calls = 0
    const promise = withTimeoutAndRetry(
      () => {
        calls++
        return new Promise(() => {})
      },
      { timeoutMs: 100, retryDelayMs: 50, retries: 1, label: '超时重试' }
    )

    // 在 advance timer 前先挂上 rejection handler，避免 fake timer 期间产生 unhandled rejection。
    const assertion = expect(promise).rejects.toThrow('超时')
    // 第一次超时 100ms + retryDelay 50ms + 第二次超时 100ms
    await vi.advanceTimersByTimeAsync(300)
    await assertion
    expect(calls).toBe(2)
  })

  it('取消后 promise 立即 reject 且不再重试', async () => {
    const { withTimeoutAndRetry } = await loadComposable()
    let calls = 0
    const promise = withTimeoutAndRetry(
      () => {
        calls++
        return new Promise(() => {})
      },
      { timeoutMs: 1000, retryDelayMs: 100, retries: 2, label: '取消' }
    )

    promise.cancel('用户取消')
    await expect(promise).rejects.toThrow('取消')
    expect(calls).toBe(1)
  })

  it('取消后底层请求的 late rejection 不产生 unhandled rejection', async () => {
    const { withTimeoutAndRetry } = await loadComposable()
    let rejectFn: (reason?: unknown) => void = () => {}
    const promise = withTimeoutAndRetry(
      () =>
        new Promise((_resolve, reject) => {
          rejectFn = reject
        }),
      { timeoutMs: 1000, retryDelayMs: 100, retries: 2, label: 'late rejection' }
    )

    promise.cancel('用户取消')
    await expect(promise).rejects.toThrow('取消')
    // 模拟底层请求晚到的 rejection，不应抛错
    expect(() => rejectFn(new Error('late'))).not.toThrow()
  })
})

describe('useEmulatorApi 轮询与竞态 (FE-POLL-*)', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.stubGlobal('window', {
      electronAPI: { getLogger: () => logger },
    })
    vi.stubGlobal('localStorage', {
      getItem: vi.fn(() => ''),
      setItem: vi.fn(),
      removeItem: vi.fn(),
    })
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('空 index 时不发起状态请求', async () => {
    const { instance } = await createManagement({ intervalMs: 100 })
    mockApi.getEmulatorApiEmulatorGetPost.mockResolvedValue({
      code: 200,
      index: [],
      data: {},
    })

    instance!.startPolling()
    await vi.advanceTimersByTimeAsync(200)
    expect(mockApi.getStatusApiEmulatorStatusPost).not.toHaveBeenCalled()
    instance!.stopPolling()
  })

  it('轮询成功后更新 devicesData 并清空该 emulator 的 pollingErrors', async () => {
    const { instance } = await createManagement({
      intervalMs: 100,
      timeoutMs: 1000,
      retries: 0,
    })

    instance!.emulatorIndex.value = [{ uid: 'emu-1', type: 'general' }]
    mockApi.getStatusApiEmulatorStatusPost.mockResolvedValue({
      code: 200,
      data: {
        'emu-1': {
          '0': { status: 0, adb_address: '127.0.0.1:7555', title: 'dev-0' },
        },
      },
    })

    instance!.startPolling()
    await vi.advanceTimersByTimeAsync(50)
    instance!.stopPolling()
    await nextTick()

    expect(instance!.devicesData.value['emu-1']?.['0']?.status).toBe(0)
    expect(instance!.pollingErrors.value['emu-1']).toBeUndefined()
  })

  it('partial 失败只记录失败 emulator，不影响其他 emulator 状态', async () => {
    const { instance } = await createManagement({
      intervalMs: 100,
      timeoutMs: 1000,
      retries: 0,
    })

    instance!.emulatorIndex.value = [
      { uid: 'emu-ok', type: 'general' },
      { uid: 'emu-fail', type: 'mumu' },
    ]
    mockApi.getStatusApiEmulatorStatusPost.mockImplementation(async req => {
      if (req.emulatorId === 'emu-ok') {
        return {
          code: 200,
          data: { 'emu-ok': { '0': { status: 0, adb_address: '127.0.0.1:7555', title: 'ok' } } },
        }
      }
      return { code: 500, status: 'error', message: 'status failed' }
    })

    instance!.startPolling()
    await vi.advanceTimersByTimeAsync(50)
    instance!.stopPolling()
    await nextTick()

    expect(instance!.devicesData.value['emu-ok']?.['0']?.status).toBe(0)
    expect(instance!.devicesData.value['emu-fail']).toBeUndefined()
    expect(instance!.pollingErrors.value['emu-fail']).toContain('status failed')
  })

  it('generation 守卫使旧响应不覆盖新数据', async () => {
    const { instance } = await createManagement({
      intervalMs: 100,
      timeoutMs: 1000,
      retries: 0,
    })

    instance!.emulatorIndex.value = [{ uid: 'emu-1', type: 'general' }]
    let resolveFirst: (value: unknown) => void = () => {}
    mockApi.getStatusApiEmulatorStatusPost.mockImplementation(
      () =>
        new Promise(resolve => {
          resolveFirst = resolve
        })
    )

    instance!.startPolling()
    await vi.advanceTimersByTimeAsync(10)
    // 旧请求仍在途中，停止并重启轮询以推进 generation
    instance!.stopPolling()
    instance!.startPolling()
    // 现在让旧请求 resolve（应被忽略）
    resolveFirst({
      code: 200,
      data: { 'emu-1': { '0': { status: 0, adb_address: '127.0.0.1:7555', title: 'old' } } },
    })
    await vi.advanceTimersByTimeAsync(10)
    await nextTick()

    // 旧 generation 的响应不应被采纳
    expect(instance!.devicesData.value['emu-1']).toBeUndefined()
  })

  it('stopPolling 取消在途请求并停止后续调度', async () => {
    const { instance } = await createManagement({
      intervalMs: 100,
      timeoutMs: 1000,
      retries: 0,
    })

    instance!.emulatorIndex.value = [{ uid: 'emu-1', type: 'general' }]
    mockApi.getStatusApiEmulatorStatusPost.mockImplementation(() => new Promise(() => {}))

    instance!.startPolling()
    await vi.advanceTimersByTimeAsync(10)
    instance!.stopPolling()
    await vi.advanceTimersByTimeAsync(500)

    // 停止后不再发起新的状态请求（已发起一次）
    expect(mockApi.getStatusApiEmulatorStatusPost).toHaveBeenCalledTimes(1)
  })
})

describe('useEmulatorApi 操作失败传播 (FE-OPERATE-*)', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.stubGlobal('window', {
      electronAPI: { getLogger: () => logger },
    })
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('operate 业务失败后 inFlight 标志被清除', async () => {
    const { instance } = await createManagement({ timeoutMs: 1000, retries: 0 })
    mockApi.operationEmulatorApiEmulatorOperatePost.mockResolvedValue({
      code: 500,
      status: 'error',
      message: 'operate failed',
    })

    await instance!.startEmulator('emu-1', '0')
    expect(instance!.startingDevices.value.has('emu-1-0')).toBe(false)
    expect(messageMock.error).toHaveBeenCalledWith('operate failed')
  })

  it('operate 抛异常后 inFlight 标志被清除并向上传播', async () => {
    // startEmulator 内部固定 retries: 1，需要推进 fake timer 让重试完成
    const { instance } = await createManagement({
      timeoutMs: 1000,
      retries: 0,
      retryDelayMs: 100,
    })
    mockApi.operationEmulatorApiEmulatorOperatePost.mockRejectedValue(new Error('ADB lost'))

    const promise = instance!.startEmulator('emu-1', '0')
    const assertion = expect(promise).rejects.toThrow('ADB lost')
    await vi.advanceTimersByTimeAsync(200)
    await assertion
    expect(instance!.startingDevices.value.has('emu-1-0')).toBe(false)
  })
  it('accepted 响应不冒充成功，收到匹配的 emulator.notice 后才提示真实成功', async () => {
    const { instance } = await createManagement({ timeoutMs: 1000, retries: 0 })
    mockApi.operationEmulatorApiEmulatorOperatePost.mockResolvedValue({
      code: 200,
      status: 'accepted',
      accepted: true,
      operationId: 'op-success',
      message: '启动操作已接受',
    })
    mockApi.getStatusApiEmulatorStatusPost.mockResolvedValue({ code: 200, data: {} })

    await instance!.startEmulator('emu-1', '0')
    expect(messageMock.success).not.toHaveBeenCalled()

    websocketMocks.handler?.({
      id: 'EmulatorManager',
      type: 'emulator.notice',
      data: { level: 'info', message: '模拟器启动完成', operationId: 'op-success' },
    })
    await Promise.resolve()

    expect(messageMock.success).toHaveBeenCalledWith('模拟器启动完成')
    expect(mockApi.getStatusApiEmulatorStatusPost).toHaveBeenCalledWith({ emulatorId: 'emu-1' })
  })

  it('收到匹配的 emulator.notice 失败时展示后端具体原因，并在卸载时退订', async () => {
    const { instance } = await createManagement({ timeoutMs: 1000, retries: 0 })
    mockApi.operationEmulatorApiEmulatorOperatePost.mockResolvedValue({
      code: 200,
      status: 'accepted',
      accepted: true,
      operationId: 'op-error',
    })
    mockApi.getStatusApiEmulatorStatusPost.mockResolvedValue({ code: 200, data: {} })

    await instance!.stopEmulator('emu-1', '0')
    websocketMocks.handler?.({
      id: 'EmulatorManager',
      type: 'emulator.notice',
      data: { level: 'error', message: '模拟器操作失败: 进程超时', operationId: 'op-error' },
    })
    await Promise.resolve()

    expect(messageMock.error).toHaveBeenCalledWith('模拟器操作失败: 进程超时')
    for (const callback of unmountCallbacks) callback()
    expect(websocketMocks.unsubscribe).toHaveBeenCalledWith('emulator_notice_subscription')
  })
})

describe('useEmulatorApi 保存/加载失败传播 (FE-SAVE-*)', () => {
  beforeEach(() => {
    vi.stubGlobal('window', {
      electronAPI: { getLogger: () => logger },
    })
    vi.stubGlobal('localStorage', {
      getItem: vi.fn(() => ''),
      setItem: vi.fn(),
      removeItem: vi.fn(),
    })
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('加载配置失败时显示错误消息且不崩溃', async () => {
    const { instance } = await createManagement({ timeoutMs: 1000, retries: 0 })
    mockApi.getEmulatorApiEmulatorGetPost.mockRejectedValue(new Error('network down'))

    await instance!.loadEmulators()
    expect(instance!.loading.value).toBe(false)
    expect(messageMock.error).toHaveBeenCalledWith('加载模拟器配置失败')
  })

  it('保存配置业务失败后显示后端消息', async () => {
    const { instance } = await createManagement({ timeoutMs: 1000, retries: 0 })
    mockApi.updateEmulatorApiEmulatorUpdatePost.mockResolvedValue({
      code: 400,
      status: 'error',
      message: 'invalid path',
    })

    await instance!.handleSaveChange('emu-1', 'name', 'new-name')
    expect(messageMock.error).toHaveBeenCalledWith('invalid path')
  })
})
