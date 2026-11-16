import { afterEach, beforeEach, describe, expect, it, vi } from 'vite-plus/test'
import { ref } from 'vue'
import { TaskMode, TaskTriggerReason, type TaskItemDocument } from '@/api'

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

const EMPTY_SNAPSHOT = { tasks: [] }
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

  it.each(['snapshot', 'websocket'])('新任务树通过 %s 保留重复运行身份', async source => {
    const script = (status: string) => ({
      info: { script_id: 's1', name: 'same script', status },
      users: {
        order: [{ uid: 'user-run', type: 'TaskUserItem' }],
        data: { 'user-run': { info: { user_id: 'user-config', status } } },
      },
    })
    const tree: TaskItemDocument = {
      info: {
        name: '受理时的队列名称',
        mode: TaskMode.AUTO_PROXY,
        status: 'running',
        trigger: TaskTriggerReason.CYCLE,
      },
      current: { log: 'current log' },
      scripts: {
        order: [
          { uid: 'run-1', type: 'TaskScriptItem' },
          { uid: 'run-2', type: 'TaskScriptItem' },
        ],
        data: {
          'run-2': script('运行'),
          'run-1': script('完成'),
        },
      },
    }
    const mod = await loadRuntimeState()
    let taskId: string
    if (source === 'snapshot') {
      taskId = 'restored'
      getRuntimeTasks.mockResolvedValue({
        tasks: [
          {
            taskId,
            mode: 'AutoProxy',
            trigger: TaskTriggerReason.CYCLE,
            logSeq: 7,
            logFirstLine: 9,
            scripts: [{ scriptId: 's1', scriptType: 'MAA' }],
            task: tree,
          },
        ],
      })
      await mod.refreshTaskRuntimeSnapshot()
    } else {
      pushTaskCreated()
      taskId = `task_${createdTaskCounter}`
      subscriptionHandlers.get(`${taskId}:task.info.updated`)!({
        id: taskId,
        type: 'task.info.updated',
        data: tree,
      })
    }
    const states = mod.getTaskRuntimeStates()
    const state = states.find(item => item.taskId === taskId)!
    expect(state.taskName).toBe('受理时的队列名称')
    expect(state.trigger).toBe(TaskTriggerReason.CYCLE)
    expect(state.log).toBe(source === 'snapshot' ? 'current log' : '')
    expect(state.logSeq).toBe(source === 'snapshot' ? 7 : undefined)
    expect(state.logFirstLine).toBe(source === 'snapshot' ? 9 : undefined)
    expect(state.taskInfo.map(item => item.script_id)).toEqual(['run-1', 'run-2'])
    expect(state.taskInfo.map(item => item.config_id)).toEqual(['s1', 's1'])
    subscriptionHandlers.get(`${taskId}:task.completed`)!({
      id: taskId,
      type: 'task.completed',
      data: { task: tree, result: 'failed', outcome: 'error' },
    })
    const completed = mod.getTaskRuntimeState(taskId)!
    expect(completed.phase).toBe('completed')
    expect(completed.log).toBe(state.log)
    expect(completed.logSeq).toBe(state.logSeq)
    expect(completed.taskInfo.map(item => item.script_id)).toEqual(['run-1', 'run-2'])
    mod.disposeTaskRuntimeState()
  })
})

describe('运行日志的唯一归属', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.clearAllMocks()
    connectionStateRef.value = 'idle'
    vi.stubGlobal('window', {
      electronAPI: { getLogger: () => logger },
      setTimeout,
      clearTimeout,
      setInterval,
      clearInterval,
    })
  })
  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  const snapshot = (taskId: string, log: string, logSeq: number) => ({
    taskId,
    mode: TaskMode.AUTO_PROXY,
    trigger: TaskTriggerReason.MANUAL,
    task: { info: { mode: TaskMode.AUTO_PROXY, name: 'snapshot name' } },
    log,
    logSeq,
  })
  const pushLog = (taskId: string, log: string, seq: number, append = false) =>
    subscriptionHandlers.get(`${taskId}:task.log.updated`)!({
      id: taskId,
      type: 'task.log.updated',
      data: { log, seq, append, firstLine: 1 },
    })

  it('快照请求途中的新日志不会被旧基线覆盖，也不会触发元数据重试', async () => {
    const mod = await loadRuntimeState()
    pushTaskCreated()
    const id = `task_${createdTaskCounter}`
    const prefetch = { target: 'MaaEnd', method: 'FluxDown', progress: '50%' }
    pushLog(id, 'one\n', 1)
    let resolve = (_value: unknown) => {}
    getRuntimeTasks.mockReturnValue(
      new Promise(accept => {
        resolve = accept
      })
    )
    const refreshing = mod.refreshTaskRuntimeSnapshot()
    pushLog(id, 'two\n', 2, true)
    resolve({
      tasks: [
        {
          ...snapshot(id, 'one\n', 1),
          task: {
            info: { mode: TaskMode.AUTO_PROXY, name: 'snapshot name' },
            current: { prefetch },
          },
        },
      ],
    })
    await refreshing
    expect(mod.getTaskRuntimeState(id)?.taskName).toBe('snapshot name')
    expect(mod.getTaskRuntimeState(id)?.log).toBe('one\ntwo\n')
    expect(getRuntimeTasks).toHaveBeenCalledTimes(1)
    expect(mod.getTaskRuntimeState(id)?.prefetch).toEqual(prefetch)
    const updateInfo = subscriptionHandlers.get(`${id}:task.info.updated`)!
    updateInfo({
      id,
      type: 'task.info.updated',
      data: { current: { prefetch: { ...prefetch, progress: '75%' } } },
    })
    expect(mod.getTaskRuntimeState(id)).toMatchObject({
      prefetch: { progress: '75%' },
      log: 'one\ntwo\n',
      logSeq: 2,
    })
    updateInfo({ id, type: 'task.info.updated', data: { current: { prefetch: null } } })
    expect(mod.getTaskRuntimeState(id)).toMatchObject({
      prefetch: null,
      log: 'one\ntwo\n',
      logSeq: 2,
    })
    updateInfo({ id, type: 'task.info.updated', data: { current: { prefetch } } })
    getRuntimeTasks.mockResolvedValueOnce(EMPTY_SNAPSHOT)
    await mod.refreshTaskRuntimeSnapshot()
    expect(mod.getTaskRuntimeState(id)).toMatchObject({
      phase: 'completed',
      prefetch: null,
      log: 'one\ntwo\n',
      logSeq: 2,
    })
    mod.disposeTaskRuntimeState()

    const recovery = await loadRuntimeState()
    pushTaskCreated()
    const recoveredId = `task_${createdTaskCounter}`
    const requestsBeforeGap = getRuntimeTasks.mock.calls.length
    pushLog(recoveredId, 'one\n', 1)
    let resolveSnapshot: (value: unknown) => void = () => undefined
    getRuntimeTasks.mockReturnValue(
      new Promise(accept => {
        resolveSnapshot = accept
      })
    )
    pushLog(recoveredId, 'lost\n', 3, true)
    pushLog(recoveredId, 'lost too\n', 4, true)
    expect(getRuntimeTasks).toHaveBeenCalledTimes(requestsBeforeGap + 1)
    resolveSnapshot({ tasks: [snapshot(recoveredId, 'recovered\n', 4)] })
    await vi.advanceTimersByTimeAsync(0)
    pushLog(recoveredId, 'tail\n', 5, true)
    expect(recovery.getTaskRuntimeState(recoveredId)?.log).toBe('recovered\ntail\n')
    expect(recovery.getTaskRuntimeState(recoveredId)?.logSeq).toBe(5)

    const requestsBeforeMutations = getRuntimeTasks.mock.calls.length
    getRuntimeTasks.mockImplementation(async () => {
      pushTaskCreated()
      return EMPTY_SNAPSHOT
    })
    await recovery.refreshTaskRuntimeSnapshot()
    expect(getRuntimeTasks).toHaveBeenCalledTimes(requestsBeforeMutations + 1)
    await vi.advanceTimersByTimeAsync(499)
    expect(getRuntimeTasks).toHaveBeenCalledTimes(requestsBeforeMutations + 1)
    await vi.advanceTimersByTimeAsync(1)
    expect(getRuntimeTasks).toHaveBeenCalledTimes(requestsBeforeMutations + 2)
    await vi.advanceTimersByTimeAsync(60_000)
    expect(getRuntimeTasks).toHaveBeenCalledTimes(requestsBeforeMutations + 6)
    expect(recovery.getTaskRuntimeState(recoveredId)?.log).toBe('recovered\ntail\n')
    recovery.disposeTaskRuntimeState()
  })
})
