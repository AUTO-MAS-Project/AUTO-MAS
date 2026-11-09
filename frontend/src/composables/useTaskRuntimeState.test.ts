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

  it('重连恢复预下载状态，后续进度和清除事件不改写脚本日志基线', async () => {
    const prefetch = { target: 'MaaEnd', method: 'FluxDown', progress: '50%' }
    getRuntimeTasks.mockResolvedValue({
      tasks: [
        {
          taskId: 'prefetch-task',
          mode: 'AutoProxy',
          queueId: null,
          scriptId: 's1',
          userId: null,
          stopping: false,
          isCycle: false,
          scripts: [],
          task: { info: { mode: TaskMode.AUTO_PROXY }, current: { prefetch } },
          cycleNextList: [],
          log: 'MAA running\n',
          logSeq: 7,
          logFirstLine: 1,
        },
      ],
      scheduledScripts: [],
    })
    const mod = await loadRuntimeState()
    await mod.refreshTaskRuntimeSnapshot()
    expect(mod.getTaskRuntimeState('prefetch-task')?.prefetch).toEqual(prefetch)
    const handler = subscriptionHandlers.get('prefetch-task:task.info.updated')!
    handler({
      id: 'prefetch-task',
      type: 'task.info.updated',
      data: {
        current: { prefetch: { ...prefetch, progress: '75%' } },
      },
    })
    expect(mod.getTaskRuntimeState('prefetch-task')).toMatchObject({
      prefetch: { progress: '75%' },
      log: 'MAA running\n',
      logSeq: 7,
    })
    handler({
      id: 'prefetch-task',
      type: 'task.info.updated',
      data: { current: { prefetch: null } },
    })
    expect(mod.getTaskRuntimeState('prefetch-task')?.prefetch).toBeNull()
    expect(mod.getTaskRuntimeState('prefetch-task')?.logSeq).toBe(7)
    handler({ id: 'prefetch-task', type: 'task.info.updated', data: { current: { prefetch } } })
    getRuntimeTasks.mockResolvedValue({ tasks: [] })
    await mod.refreshTaskRuntimeSnapshot()
    expect(mod.getTaskRuntimeState('prefetch-task')).toMatchObject({
      phase: 'completed',
      prefetch: null,
      log: 'MAA running\n',
      logSeq: 7,
    })
    mod.disposeTaskRuntimeState()
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

  it('显式无日志基线的过程态快照通过已有重试取得提交后的基线', async () => {
    const task = {
      taskId: 'transient',
      mode: 'AutoProxy',
      scripts: [],
      task: { info: { mode: TaskMode.AUTO_PROXY } },
      log: 'before',
      logSeq: null,
    }
    getRuntimeTasks.mockResolvedValueOnce({ tasks: [task] })
    getRuntimeTasks.mockResolvedValue({
      tasks: [{ ...task, log: 'committed', logSeq: 4 }],
    })
    const mod = await loadRuntimeState()
    await mod.refreshTaskRuntimeSnapshot()
    expect(mod.getTaskRuntimeState('transient')?.logSeq).toBeUndefined()
    await vi.advanceTimersByTimeAsync(500)
    expect(mod.getTaskRuntimeState('transient')?.logSeq).toBe(4)
    expect(mod.getTaskRuntimeState('transient')?.log).toBe('committed')
    await vi.advanceTimersByTimeAsync(5000)
    expect(getRuntimeTasks).toHaveBeenCalledTimes(2)
    mod.disposeTaskRuntimeState()
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

  it('HTTP 受理保留早到的日志和终态，日志不广播生命周期事件', async () => {
    const mod = await loadRuntimeState()
    const events: string[] = []
    mod.onTaskRuntimeEvent(event => {
      events.push(event.type)
    })
    pushTaskCreated()
    const id = `task_${createdTaskCounter}`
    const state = mod.getTaskRuntimeState(id)!
    pushLog(id, '', 1)
    pushLog(id, 'waiting for lock\n', 2, true)
    mod.registerAcceptedTask(id, TaskMode.AUTO_PROXY)
    expect(mod.getTaskRuntimeState(id)).toBe(state)
    expect(state.log).toBe('waiting for lock\n')
    expect(state.logSeq).toBe(2)
    expect(events).toEqual(['created'])
    subscriptionHandlers.get(`${id}:task.completed`)!({
      id,
      type: 'task.completed',
      data: { outcome: 'success', result: 'done', task: { info: { mode: TaskMode.AUTO_PROXY } } },
    })
    mod.registerAcceptedTask(id, TaskMode.AUTO_PROXY)
    expect(mod.getTaskRuntimeState(id)?.phase).toBe('completed')
    expect(mod.getTaskRuntimeState(id)?.log).toBe('waiting for lock\n')
    expect(mod.getTaskRuntimeState(id)?.result).toBe('done')
    mod.disposeTaskRuntimeState()
  })

  it('日志漏包只发起一次补快照，恢复后继续追加', async () => {
    const mod = await loadRuntimeState()
    pushTaskCreated()
    const id = `task_${createdTaskCounter}`
    pushLog(id, 'one\n', 1)
    let resolve = (_value: unknown) => {}
    getRuntimeTasks.mockReturnValue(
      new Promise(accept => {
        resolve = accept
      })
    )
    pushLog(id, 'lost\n', 3, true)
    pushLog(id, 'lost too\n', 4, true)
    expect(getRuntimeTasks).toHaveBeenCalledTimes(1)
    resolve({ tasks: [snapshot(id, 'recovered\n', 4)] })
    await vi.advanceTimersByTimeAsync(0)
    pushLog(id, 'tail\n', 5, true)
    expect(mod.getTaskRuntimeState(id)?.log).toBe('recovered\ntail\n')
    expect(mod.getTaskRuntimeState(id)?.logSeq).toBe(5)
    mod.disposeTaskRuntimeState()
  })

  it('快照请求途中的新日志不会被旧基线覆盖，也不会触发元数据重试', async () => {
    const mod = await loadRuntimeState()
    pushTaskCreated()
    const id = `task_${createdTaskCounter}`
    pushLog(id, 'one\n', 1)
    let resolve = (_value: unknown) => {}
    getRuntimeTasks.mockReturnValue(
      new Promise(accept => {
        resolve = accept
      })
    )
    const refreshing = mod.refreshTaskRuntimeSnapshot()
    pushLog(id, 'two\n', 2, true)
    resolve({ tasks: [snapshot(id, 'one\n', 1)] })
    await refreshing
    expect(mod.getTaskRuntimeState(id)?.taskName).toBe('snapshot name')
    expect(mod.getTaskRuntimeState(id)?.log).toBe('one\ntwo\n')
    expect(getRuntimeTasks).toHaveBeenCalledTimes(1)
    mod.disposeTaskRuntimeState()
  })

  it('标签绑定的完成任务保留结果，释放绑定后按原保留期清理', async () => {
    const mod = await loadRuntimeState()
    pushTaskCreated()
    const id = `task_${createdTaskCounter}`
    mod.retainTaskRuntime(id)
    subscriptionHandlers.get(`${id}:task.completed`)!({
      id,
      type: 'task.completed',
      data: { outcome: 'success', result: 'done', task: { info: { mode: TaskMode.AUTO_PROXY } } },
    })
    await vi.advanceTimersByTimeAsync(6 * 60 * 1000)
    expect(mod.getTaskRuntimeState(id)?.result).toBe('done')
    mod.releaseTaskRuntime(id)
    await vi.advanceTimersByTimeAsync(30 * 1000)
    expect(mod.getTaskRuntimeState(id)).toBeUndefined()
    mod.disposeTaskRuntimeState()
  })
})
