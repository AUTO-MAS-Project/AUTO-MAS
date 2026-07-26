/**
 * 冷启动快照时序断链修复测试
 *
 * 缺陷：appEntry 先建连（后端立即推 Main/snapshot.response），后才 initialize()
 * 建立 (taskId, task.info.updated) 订阅——快照到达时无订阅者被丢弃，且前端从不发
 * snapshot.request，运行中任务状态无法恢复。
 *
 * 修复：useSchedulerLogic.initialize() 在全部订阅建立完成后，通过 ws.send 发送
 * {id: 'Main', type: 'snapshot.request'} 按需补拉快照（连接层只在 id=Main 时
 * 展开快照，故必须用 id=Main 请求）。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// ---- Mock API Service ----
const mockApi = vi.hoisted(() => ({
  stopTaskApiDispatchStopPost: vi.fn(),
  getTaskComboxApiInfoComboxTaskPost: vi.fn().mockResolvedValue({ code: 200, data: [] }),
  getScriptComboxApiInfoComboxScriptPost: vi.fn().mockResolvedValue({ code: 200, data: [] }),
  getItemApiQueueItemGetPost: vi.fn().mockResolvedValue({ code: 200, index: [], data: {} }),
  addTaskApiDispatchStartPost: vi.fn().mockResolvedValue({ code: 200, taskId: 'task-started' }),
}))

vi.mock('@/api/services/Service', () => ({
  Service: mockApi,
}))

vi.mock('ant-design-vue', () => ({
  message: { info: vi.fn(), success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  Modal: { confirm: vi.fn(), warning: vi.fn() },
  notification: { info: vi.fn(), success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

vi.mock('@/composables/useAudioPlayer', () => ({
  useAudioPlayer: () => ({ playSound: vi.fn().mockResolvedValue(undefined) }),
}))

const mockWS = {
  status: { value: '已连接' },
  subscribe: vi.fn().mockImplementation(({ id, type }: { id: string; type: string }) => {
    return `sub-${id}-${type}`
  }),
  unsubscribe: vi.fn(),
  send: vi.fn().mockReturnValue(true),
  sendRaw: vi.fn(),
}

vi.mock('@/composables/useWebSocket', () => ({
  useWebSocket: () => mockWS,
  ExternalWSHandlers: { taskManagerMessage: null, mainMessage: null },
}))

vi.mock('./schedulerHandlers', () => ({
  default: {
    registerSchedulerUI: vi.fn(),
    consumePendingTabIds: vi.fn().mockReturnValue([]),
    consumePendingCountdown: vi.fn().mockReturnValue(null),
    handleMainMessage: vi.fn(),
    bootstrapSchedulerSubscriptions: vi.fn(),
  },
}))

const logger = { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() }

const loadSchedulerLogic = async () => {
  vi.resetModules()
  return await import('./useSchedulerLogic')
}

const stubSessionStorage = (payload: string | null) => {
  vi.stubGlobal('sessionStorage', {
    getItem: vi.fn().mockReturnValue(payload),
    setItem: vi.fn(),
    removeItem: vi.fn(),
  })
}

describe('冷启动快照补拉（snapshot.request）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockWS.send.mockReturnValue(true)
    vi.stubGlobal('window', {
      electronAPI: {
        getLogger: () => logger,
      },
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      setTimeout: globalThis.setTimeout,
      clearTimeout: globalThis.clearTimeout,
    })
    vi.stubGlobal('localStorage', {
      getItem: vi.fn().mockReturnValue(null),
      setItem: vi.fn(),
      removeItem: vi.fn(),
    })
    stubSessionStorage(null)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('initialize() 后以 id=Main 发送一次 snapshot.request', async () => {
    const mod = await loadSchedulerLogic()
    const { initialize } = mod.useSchedulerLogic()

    initialize()

    const snapshotCalls = mockWS.send.mock.calls.filter(call => call[1] === 'snapshot.request')
    expect(snapshotCalls).toHaveLength(1)
    // 连接层只在 id=Main 时展开快照，请求必须使用 id=Main
    expect(snapshotCalls[0][0]).toBe('Main')
  })

  it('快照请求发生在恢复运行中 tab 的订阅建立之后', async () => {
    // 模拟页面刷新：sessionStorage 中存在运行中的 tab，需要先恢复订阅再补拉快照
    const runningTab = {
      key: 'main',
      title: '主调度台',
      closable: false,
      status: '运行',
      selectedTaskId: null,
      selectedMode: 'AutoProxy',
      resumeFromScriptId: null,
      resumeScriptOptions: [],
      resumeScriptLoading: false,
      websocketId: 'task-running-1',
      taskQueue: [],
      userQueue: [],
      logs: [],
      isLogAtBottom: true,
      lastLogContent: '',
    }
    stubSessionStorage(JSON.stringify([runningTab]))

    const mod = await loadSchedulerLogic()
    const { initialize } = mod.useSchedulerLogic()

    initialize()

    // 任务订阅已建立（含 task.info.updated）
    const taskSubscribeCalls = mockWS.subscribe.mock.calls.filter(
      call => call[0]?.id === 'task-running-1'
    )
    expect(taskSubscribeCalls.length).toBeGreaterThan(0)
    expect(taskSubscribeCalls.some(call => call[0]?.type === 'task.info.updated')).toBe(true)

    // 快照请求晚于所有任务订阅建立（订阅就绪后快照重分发才有接收者）
    const snapshotSendOrder = mockWS.send.mock.invocationCallOrder[0]
    const subscribeOrders = mockWS.subscribe.mock.invocationCallOrder
    expect(snapshotSendOrder).toBeGreaterThan(Math.max(...subscribeOrders))
  })

  it('连接未就绪时 send 返回 false 不抛异常，等待后端在重连后自动推送', async () => {
    mockWS.send.mockReturnValue(false)

    const mod = await loadSchedulerLogic()
    const { initialize } = mod.useSchedulerLogic()

    expect(() => initialize()).not.toThrow()
    expect(logger.info).toHaveBeenCalledWith(expect.stringContaining('快照补拉请求未发送'))
  })

  it('重复 initialize() 每次都会补拉（幂等请求，多次无害）', async () => {
    const mod = await loadSchedulerLogic()
    const { initialize } = mod.useSchedulerLogic()

    initialize()
    initialize()

    const snapshotCalls = mockWS.send.mock.calls.filter(call => call[1] === 'snapshot.request')
    expect(snapshotCalls).toHaveLength(2)
  })
})
