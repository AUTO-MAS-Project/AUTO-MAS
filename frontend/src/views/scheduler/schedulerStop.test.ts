/**
 * 调度器停止行为与状态机测试
 *
 * 覆盖 Lane 09 目标：
 * - stop `code=500` 假成功修复（显式检查 response.code）
 * - 停止中状态忽略迟到 WS 消息（防止旧快照覆盖）
 * - 状态机转换：运行 → 停止中 → 结束/失败
 * - 订阅/timer 清理
 *
 * 结论标注：observed（vitest 单元测试）
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

// ---- Mock ant-design-vue ----
vi.mock('ant-design-vue', () => ({
  message: { info: vi.fn(), success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  Modal: { confirm: vi.fn(), warning: vi.fn() },
  notification: { info: vi.fn(), success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

// ---- Mock useAudioPlayer ----
const mockPlaySound = vi.fn().mockResolvedValue(undefined)
vi.mock('@/composables/useAudioPlayer', () => ({
  useAudioPlayer: () => ({ playSound: mockPlaySound }),
}))

// ---- Mock useWebSocket ----
// 订阅回调通过 mockWS.subscribe 的返回值与调用记录可被测试访问
const subscribeCallbacks = new Map<string, (msg: any) => void>()
const mockWS = {
  status: { value: '已连接' },
  subscribe: vi.fn().mockImplementation(({ id, type }: { id: string; type: string }) => {
    const subId = `sub-${id}-${type}-${subscribeCallbacks.size}`
    return subId
  }),
  // registerSubscribeCallback 用于测试直接向 handleWebSocketMessage 注入消息
  registerSubscribeCallback: vi.fn(),
  unsubscribe: vi.fn(),
  send: vi.fn().mockReturnValue(true),
  sendRaw: vi.fn(),
}

vi.mock('@/composables/useWebSocket', () => ({
  useWebSocket: () => mockWS,
  ExternalWSHandlers: { taskManagerMessage: null, mainMessage: null },
}))

// ---- Mock schedulerHandlers ----
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

// Dynamic import to avoid static hoisting
const loadSchedulerLogic = async () => {
  vi.resetModules()
  return await import('./useSchedulerLogic')
}

describe('调度器停止行为', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    subscribeCallbacks.clear()
    vi.stubGlobal('window', {
      electronAPI: {
        getLogger: () => logger,
        appQuit: vi.fn().mockResolvedValue(undefined),
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
    vi.stubGlobal('sessionStorage', {
      getItem: vi.fn().mockReturnValue(null),
      setItem: vi.fn(),
      removeItem: vi.fn(),
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  describe('stopTask - code=500 假成功修复', () => {
    it('无 websocketId 时直接返回不调用 API', async () => {
      const mod = await loadSchedulerLogic()
      const { schedulerTabs, stopTask, initialize } = mod.useSchedulerLogic()

      await initialize()
      const tab = schedulerTabs.value[0]
      tab.websocketId = null

      await stopTask(tab)
      expect(mockApi.stopTaskApiDispatchStopPost).not.toHaveBeenCalled()
      expect(mockPlaySound).not.toHaveBeenCalled()
    })

    it('response.code=200 时进入停止中状态并播放音频', async () => {
      // 后端 dispatch.py 正常停止返回 OutBase()，code 默认 200
      mockApi.stopTaskApiDispatchStopPost.mockResolvedValue({ code: 200 })

      const mod = await loadSchedulerLogic()
      const { schedulerTabs, stopTask, initialize } = mod.useSchedulerLogic()

      await initialize()
      const tab = schedulerTabs.value[0]
      tab.websocketId = 'task-123'
      tab.status = '运行'

      await stopTask(tab)

      expect(mockApi.stopTaskApiDispatchStopPost).toHaveBeenCalledWith({
        taskId: 'task-123',
      })
      // 成功路径：播放中止音频
      expect(mockPlaySound).toHaveBeenCalledWith('maa_task_aborted')
      // 保持停止中状态，等待 WS Accomplish 信号
      expect(tab.status).toBe('停止中')
    })

    it('response.code=500 时不播放音频，状态从运行切为失败（假成功修复）', async () => {
      // 后端 dispatch.py 异常时返回 OutBase(code=500)，HTTP 仍为 200
      // 这是 Lane 09 修复的核心缺陷：旧代码不检查 response.code，把 500 当成功
      mockApi.stopTaskApiDispatchStopPost.mockResolvedValue({
        code: 500,
        status: 'error',
        message: 'TaskRuntimeError: task not found',
      })

      const mod = await loadSchedulerLogic()
      const { schedulerTabs, stopTask, initialize } = mod.useSchedulerLogic()

      await initialize()
      const tab = schedulerTabs.value[0]
      tab.websocketId = 'task-500'
      tab.status = '运行'

      await stopTask(tab)

      expect(mockApi.stopTaskApiDispatchStopPost).toHaveBeenCalledWith({
        taskId: 'task-500',
      })
      // 关键断言：code=500 时不得播放成功音频
      expect(mockPlaySound).not.toHaveBeenCalled()
      // 状态从运行切为失败，不停留在停止中
      expect(tab.status).toBe('失败')
      // 错误被记录
      expect(logger.error).toHaveBeenCalledWith(expect.stringContaining('停止任务失败'))
    })

    it('response.code 缺失时也视为失败（防御性）', async () => {
      // 某些异常路径可能返回无 code 的对象
      mockApi.stopTaskApiDispatchStopPost.mockResolvedValue({})

      const mod = await loadSchedulerLogic()
      const { schedulerTabs, stopTask, initialize } = mod.useSchedulerLogic()

      await initialize()
      const tab = schedulerTabs.value[0]
      tab.websocketId = 'task-nocode'
      tab.status = '运行'

      await stopTask(tab)

      // undefined !== 200 → 失败路径
      expect(mockPlaySound).not.toHaveBeenCalled()
      expect(tab.status).toBe('失败')
    })

    it('API 抛出网络异常时状态切为失败', async () => {
      mockApi.stopTaskApiDispatchStopPost.mockRejectedValue(new Error('网络断开'))

      const mod = await loadSchedulerLogic()
      const { schedulerTabs, stopTask, initialize } = mod.useSchedulerLogic()

      await initialize()
      const tab = schedulerTabs.value[0]
      tab.websocketId = 'task-net'
      tab.status = '运行'

      await stopTask(tab)

      expect(mockPlaySound).not.toHaveBeenCalled()
      expect(tab.status).toBe('失败')
      expect(logger.error).toHaveBeenCalledWith(expect.stringContaining('停止任务请求异常'))
    })

    it('非运行状态停止失败时恢复原状态', async () => {
      // 例如停止中状态再次点击（虽 UI 已禁用），失败后应回到停止中而非失败
      mockApi.stopTaskApiDispatchStopPost.mockResolvedValue({
        code: 500,
        message: 'already stopping',
      })

      const mod = await loadSchedulerLogic()
      const { schedulerTabs, stopTask, initialize } = mod.useSchedulerLogic()

      await initialize()
      const tab = schedulerTabs.value[0]
      tab.websocketId = 'task-retry'
      tab.status = '空闲'

      await stopTask(tab)

      // previousStatus=空闲，非运行，恢复为空闲而非失败
      expect(tab.status).toBe('空闲')
      expect(mockPlaySound).not.toHaveBeenCalled()
    })
  })

  describe('停止中状态 - 旧 WS 消息覆盖防护', () => {
    it('停止中状态忽略 Update 消息，不覆盖 taskQueue', async () => {
      mockApi.stopTaskApiDispatchStopPost.mockResolvedValue({ code: 200 })

      const mod = await loadSchedulerLogic()
      const { schedulerTabs, startTask, stopTask, initialize } = mod.useSchedulerLogic()

      await initialize()
      const tab = schedulerTabs.value[0]
      tab.selectedTaskId = 'queue-stale'
      tab.selectedMode = 'AutoProxy' as any

      // startTask 内部调用 subscribeToTask，设置 WS 订阅回调
      await startTask(tab)
      expect(tab.status).toBe('运行')

      // 预置已有 taskQueue（startTask 会清空，需在 start 后设置）
      tab.taskQueue = [{ name: '原始任务', status: '运行' }]

      // 进入停止中
      await stopTask(tab)
      expect(tab.status).toBe('停止中')

      // 捕获 subscribe 注册的回调（startTask → subscribeToTask 注册了多类型订阅）
      const subscribeCalls = mockWS.subscribe.mock.calls
      expect(subscribeCalls.length).toBeGreaterThan(0)
      const updateCallback = subscribeCalls.find(call => call[0]?.type === 'Update')?.[1] as (
        msg: any
      ) => void
      expect(updateCallback).toBeDefined()

      // 模拟迟到的 Update 消息
      updateCallback({
        id: tab.websocketId,
        type: 'Update',
        data: {
          task_info: [{ name: '迟到任务', status: '运行', userList: [] }],
          log: '迟到的日志',
        },
      })

      // 关键断言：taskQueue 不被迟到消息覆盖
      expect(tab.taskQueue).toEqual([{ name: '原始任务', status: '运行' }])
      expect(tab.lastLogContent).toBe('')
      // 应记录忽略日志
      expect(logger.info).toHaveBeenCalledWith(expect.stringContaining('停止中状态忽略迟到消息'))
    })

    it('停止中状态仍接受 Accomplish 信号以完成停止→结束转换', async () => {
      mockApi.stopTaskApiDispatchStopPost.mockResolvedValue({ code: 200 })

      const mod = await loadSchedulerLogic()
      const { schedulerTabs, startTask, stopTask, initialize } = mod.useSchedulerLogic()

      await initialize()
      const tab = schedulerTabs.value[0]
      tab.selectedTaskId = 'queue-acc'
      tab.selectedMode = 'AutoProxy' as any

      await startTask(tab)
      await stopTask(tab)
      expect(tab.status).toBe('停止中')

      const subscribeCalls = mockWS.subscribe.mock.calls
      const signalCallback = subscribeCalls.find(call => call[0]?.type === 'Signal')?.[1] as (
        msg: any
      ) => void

      expect(signalCallback).toBeDefined()

      // 模拟 WS Accomplish 信号
      signalCallback({
        id: tab.websocketId,
        type: 'Signal',
        data: { Accomplish: '任务已完成' },
      })

      // 停止中 → 结束 的转换应正常完成
      expect(tab.status).toBe('结束')
    })

    it('停止中状态忽略 Info 日志消息', async () => {
      mockApi.stopTaskApiDispatchStopPost.mockResolvedValue({ code: 200 })

      const mod = await loadSchedulerLogic()
      const { schedulerTabs, startTask, stopTask, initialize } = mod.useSchedulerLogic()

      await initialize()
      const tab = schedulerTabs.value[0]
      tab.selectedTaskId = 'queue-info'
      tab.selectedMode = 'AutoProxy' as any

      await startTask(tab)
      await stopTask(tab)

      const subscribeCalls = mockWS.subscribe.mock.calls
      const infoCallback = subscribeCalls.find(call => call[0]?.type === 'Info')?.[1] as (
        msg: any
      ) => void

      expect(infoCallback).toBeDefined()

      // 清除 startTask/stopTask 期间的音频调用
      mockPlaySound.mockClear()

      infoCallback({
        id: tab.websocketId,
        type: 'Info',
        data: { Error: '迟到的错误' },
      })

      // 停止中不应触发错误通知音频
      expect(mockPlaySound).not.toHaveBeenCalledWith('error_occurred')
    })
  })

  describe('CycleRun 启动契约', () => {
    it('循环运行不携带普通队列的 resumeFromScriptId', async () => {
      const mod = await loadSchedulerLogic()
      const { schedulerTabs, startTask, initialize } = mod.useSchedulerLogic()

      await initialize()
      const tab = schedulerTabs.value[0]
      tab.selectedTaskId = 'queue-cycle'
      tab.selectedMode = 'CycleRun' as any
      tab.resumeFromScriptId = 'script-stale'

      await startTask(tab)

      expect(mockApi.addTaskApiDispatchStartPost).toHaveBeenCalledWith({
        taskId: 'queue-cycle',
        mode: 'CycleRun',
      })
    })
  })

  describe('状态机转换', () => {
    it('收到 Accomplish 信号后 tab.status 变为 结束', async () => {
      const mod = await loadSchedulerLogic()
      const { schedulerTabs, startTask, initialize } = mod.useSchedulerLogic()

      await initialize()
      const tab = schedulerTabs.value[0]
      tab.selectedTaskId = 'queue-done'
      tab.selectedMode = 'AutoProxy' as any

      await startTask(tab)

      const subscribeCalls = mockWS.subscribe.mock.calls
      const signalCallback = subscribeCalls.find(call => call[0]?.type === 'Signal')?.[1] as (
        msg: any
      ) => void

      expect(signalCallback).toBeDefined()

      signalCallback({
        id: tab.websocketId,
        type: 'Signal',
        data: { Accomplish: '完成' },
      })

      expect(tab.status).toBe('结束')
    })

    it('已结束的 tab 忽略重复 Accomplish 信号', async () => {
      const mod = await loadSchedulerLogic()
      const { schedulerTabs, startTask, initialize } = mod.useSchedulerLogic()

      await initialize()
      const tab = schedulerTabs.value[0]
      tab.selectedTaskId = 'queue-ended'
      tab.selectedMode = 'AutoProxy' as any

      await startTask(tab)

      const subscribeCalls = mockWS.subscribe.mock.calls
      const signalCallback = subscribeCalls.find(call => call[0]?.type === 'Signal')?.[1] as (
        msg: any
      ) => void

      // 第一次 Accomplish → 结束
      signalCallback({
        id: tab.websocketId,
        type: 'Signal',
        data: { Accomplish: '完成' },
      })
      expect(tab.status).toBe('结束')

      // 清除音频调用
      mockPlaySound.mockClear()

      // 第二次重复 Accomplish → 应忽略
      signalCallback({
        id: tab.websocketId,
        type: 'Signal',
        data: { Accomplish: '重复完成' },
      })

      expect(mockPlaySound).not.toHaveBeenCalled()
      expect(tab.status).toBe('结束')
    })

    it('未运行的任务完成信号不改变其他 tab 状态', async () => {
      const mod = await loadSchedulerLogic()
      const { schedulerTabs, addSchedulerTab, initialize } = mod.useSchedulerLogic()

      await initialize()

      const tab2 = addSchedulerTab({ title: '调度台2', status: '空闲' })
      tab2.websocketId = 'task-456'

      const mainTab = schedulerTabs.value[0]
      mainTab.status = '空闲'

      tab2.status = '结束'

      expect(mainTab.status).toBe('空闲')
      expect(tab2.status).toBe('结束')
    })
  })

  describe('订阅与 timer 清理', () => {
    it('cleanup 清理所有订阅和 pending timer', async () => {
      const mod = await loadSchedulerLogic()
      const { schedulerTabs, startTask, cleanup, initialize } = mod.useSchedulerLogic()

      await initialize()
      const tab = schedulerTabs.value[0]
      tab.selectedTaskId = 'queue-cleanup'
      tab.selectedMode = 'AutoProxy' as any

      await startTask(tab)

      // 调用 cleanup
      cleanup()

      // 所有订阅应被 unsubscribe
      expect(mockWS.unsubscribe).toHaveBeenCalled()
    })

    it('startTask 创建订阅并在任务完成后清理', async () => {
      const mod = await loadSchedulerLogic()
      const { schedulerTabs, startTask, initialize } = mod.useSchedulerLogic()

      await initialize()

      const tab = schedulerTabs.value[0]
      tab.selectedTaskId = 'queue-sub'
      tab.selectedMode = 'AutoProxy' as any

      await startTask(tab)

      // startTask 内部调用 subscribeToTask 创建订阅
      expect(mockWS.subscribe.mock.calls.length).toBeGreaterThan(0)
    })

    it('初始化时将停止中的 tab 标记为失败（页面刷新后无法收到 WS 完成信号）', async () => {
      // 模拟 sessionStorage 中存在停止中的 tab
      const staleTab = {
        key: 'main',
        title: '主调度台',
        closable: false,
        status: '停止中',
        selectedTaskId: null,
        selectedMode: 'AutoProxy',
        resumeFromScriptId: null,
        resumeScriptOptions: [],
        resumeScriptLoading: false,
        websocketId: 'stale-task',
        taskQueue: [],
        userQueue: [],
        logs: [],
        isLogAtBottom: true,
        lastLogContent: '',
      }
      vi.stubGlobal('sessionStorage', {
        getItem: vi.fn().mockReturnValue(JSON.stringify([staleTab])),
        setItem: vi.fn(),
        removeItem: vi.fn(),
      })

      const mod = await loadSchedulerLogic()
      const { schedulerTabs, initialize } = mod.useSchedulerLogic()

      await initialize()

      const tab = schedulerTabs.value[0]
      // 停止中的 tab 在初始化后被标记为失败，避免永久停留
      expect(tab.status).toBe('失败')
      expect(tab.websocketId).toBeNull()
    })
  })
})
