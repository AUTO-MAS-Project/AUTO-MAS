import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

// ==================== 全局桩 ====================

const logger = { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() }

const getRuntimeTasks = vi.hoisted(() => vi.fn())
vi.mock('@/services/realtimeSnapshotApi', () => ({
  realtimeSnapshotApi: { getRuntimeTasks },
}))

const connectionStateRef = ref<'idle' | 'open' | 'reconnecting'>('idle')
vi.mock('@/services/websocket/connection', () => ({
  connectionState: () => connectionStateRef,
  onConnected: () => () => undefined,
}))

// 常驻订阅按消息类型记下处理函数，测试里据此模拟请求期间到达的增量事件
type Handler = (message: { id: string; type: string; data: unknown }) => void
const subscriptionHandlers = vi.hoisted(() => new Map<string, Handler>())
vi.mock('@/services/websocket/subscriptions', () => ({
  subscribe: (filter: { id: string; type: string }, handler: Handler) => {
    subscriptionHandlers.set(`${filter.id}:${filter.type}`, handler)
    return `sub_${filter.id}_${filter.type}`
  },
  unsubscribe: vi.fn(),
}))

const EMPTY_SNAPSHOT = { tasks: [], scheduledScripts: [] }
let createdTaskCounter = 0

const pushTaskCreated = (): void => {
  const handler = subscriptionHandlers.get('TaskManager:task.created')
  if (!handler) throw new Error('未注册 task.created 常驻订阅')
  createdTaskCounter++
  handler({
    id: 'TaskManager',
    type: 'task.created',
    data: {
      taskId: `task_${createdTaskCounter}`,
      mode: 'AutoProxy',
      scripts: [{ scriptId: 's1', scriptType: 'MAA' }],
    },
  })
}

const loadRuntimeState = async () => {
  vi.resetModules()
  subscriptionHandlers.clear()
  const mod = await import('./useTaskRuntimeState')
  mod.bootstrapTaskRuntimeState()
  return mod
}

describe('useTaskRuntimeState 快照对账', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.clearAllMocks()
    connectionStateRef.value = 'idle'
    vi.stubGlobal('window', {
      electronAPI: { getLogger: () => logger },
      setTimeout: (fn: () => void, ms?: number) => setTimeout(fn, ms),
      clearTimeout: (id: number) => clearTimeout(id),
      setInterval: (fn: () => void, ms?: number) => setInterval(fn, ms),
      clearInterval: (id: number) => clearInterval(id),
    })
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('请求期间有增量事件时隔一拍再重取，不背靠背热请求，且重取次数有上限', async () => {
    // 每次快照请求期间都有新任务创建：模拟高频增量
    getRuntimeTasks.mockImplementation(async () => {
      pushTaskCreated()
      return EMPTY_SNAPSHOT
    })
    const mod = await loadRuntimeState()

    await mod.refreshTaskRuntimeSnapshot()
    expect(getRuntimeTasks).toHaveBeenCalledTimes(1)

    // 不再立刻递归重取
    await vi.advanceTimersByTimeAsync(499)
    expect(getRuntimeTasks).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(1)
    expect(getRuntimeTasks).toHaveBeenCalledTimes(2)

    // 首次 + 最多 5 次重取，之后放弃本轮对账
    await vi.advanceTimersByTimeAsync(60000)
    expect(getRuntimeTasks).toHaveBeenCalledTimes(6)
    expect(logger.warn).toHaveBeenCalledWith('运行任务快照请求期间持续有增量事件，放弃本轮对账')
  })

  it('增量事件平息后重取成功即完成对账，不再继续请求', async () => {
    getRuntimeTasks
      .mockImplementationOnce(async () => {
        pushTaskCreated()
        return EMPTY_SNAPSHOT
      })
      .mockResolvedValue(EMPTY_SNAPSHOT)
    const mod = await loadRuntimeState()

    await mod.refreshTaskRuntimeSnapshot()
    await vi.advanceTimersByTimeAsync(60000)

    expect(getRuntimeTasks).toHaveBeenCalledTimes(2)
    // 快照里没有该任务：请求期间创建、又被快照判定不再活跃的任务按快照移除
    expect(mod.getTaskRuntimeStates()).toEqual([])
  })

  it('重连后快照拉取失败时延时重试一次，再失败不无限重试', async () => {
    connectionStateRef.value = 'open'
    getRuntimeTasks.mockRejectedValue(new Error('HTTP 503'))
    const mod = await loadRuntimeState()
    // bootstrap 时连接已 open 会立即拉一次
    await vi.advanceTimersByTimeAsync(0)
    expect(getRuntimeTasks).toHaveBeenCalledTimes(1)

    await vi.advanceTimersByTimeAsync(2999)
    expect(getRuntimeTasks).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(1)
    expect(getRuntimeTasks).toHaveBeenCalledTimes(2)

    await vi.advanceTimersByTimeAsync(60000)
    expect(getRuntimeTasks).toHaveBeenCalledTimes(2)
    mod.disposeTaskRuntimeState()
  })

  it('失败重试到点时连接已断开则跳过，交给下次重连', async () => {
    getRuntimeTasks.mockRejectedValue(new Error('HTTP 503'))
    const mod = await loadRuntimeState()

    connectionStateRef.value = 'open'
    await mod.refreshTaskRuntimeSnapshot()
    connectionStateRef.value = 'reconnecting'
    await vi.advanceTimersByTimeAsync(60000)

    expect(getRuntimeTasks).toHaveBeenCalledTimes(1)
  })

  it('释放后不再执行挂起的重试', async () => {
    connectionStateRef.value = 'open'
    getRuntimeTasks.mockRejectedValue(new Error('HTTP 503'))
    const mod = await loadRuntimeState()
    await vi.advanceTimersByTimeAsync(0)
    expect(getRuntimeTasks).toHaveBeenCalledTimes(1)

    mod.disposeTaskRuntimeState()
    await vi.advanceTimersByTimeAsync(60000)
    expect(getRuntimeTasks).toHaveBeenCalledTimes(1)
  })
})
