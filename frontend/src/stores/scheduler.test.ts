import { afterEach, beforeEach, describe, expect, it, vi } from 'vite-plus/test'
import { createPinia, setActivePinia } from 'pinia'
import { TaskMode, TaskTriggerReason } from '@/api'
import type { TaskRuntimeEvent, TaskRuntimeState } from '@/composables/useTaskRuntimeState'

const runtime = vi.hoisted(() => ({
  states: new Map<string, TaskRuntimeState>(),
  listener: undefined as ((event: TaskRuntimeEvent) => void) | undefined,
  retain: vi.fn(),
  release: vi.fn(),
}))
vi.mock('@/i18n', () => ({ translate: (key: string) => key }))
vi.mock('@/composables/useTaskRuntimeState', () => ({
  getTaskRuntimeState: (id: string) => runtime.states.get(id),
  getTaskRuntimeStates: () => [...runtime.states.values()],
  registerAcceptedTask: vi.fn(),
  retainTaskRuntime: runtime.retain,
  releaseTaskRuntime: runtime.release,
  onTaskRuntimeEvent: (listener: (event: TaskRuntimeEvent) => void) => {
    runtime.listener = listener
    return () => {
      runtime.listener = undefined
    }
  },
}))

const state = (taskId: string): TaskRuntimeState => ({
  taskId,
  mode: TaskMode.AUTO_PROXY,
  trigger: TaskTriggerReason.MANUAL,
  scriptId: 'same-config',
  userId: null,
  stopping: false,
  scripts: [],
  taskInfo: [],
  prefetch: null,
  log: `waiting-${taskId}`,
  logSeq: 2,
  phase: 'active',
  taskName: 'same name',
  taskType: null,
  result: null,
  outcome: null,
  error: null,
  completedAt: null,
})
let store: ReturnType<(typeof import('./scheduler'))['useSchedulerStore']>
let saved: Map<string, string>

beforeEach(async () => {
  vi.useFakeTimers()
  vi.clearAllMocks()
  runtime.states.clear()
  saved = new Map()
  vi.stubGlobal('window', {
    electronAPI: { getLogger: () => ({ warn: vi.fn() }) },
    setTimeout,
    clearTimeout,
  })
  vi.stubGlobal('sessionStorage', {
    getItem: (key: string) => saved.get(key) ?? null,
    setItem: (key: string, value: string) => saved.set(key, value),
  })
  setActivePinia(createPinia())
  store = (await import('./scheduler')).useSchedulerStore()
})
afterEach(() => {
  store.$dispose()
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('调度台只绑定运行身份', () => {
  it('自动清理保留切到后台的启动页，响应返回后只绑定一个可见标签', () => {
    store.bootstrap()
    for (let index = 0; index < 20; index++) {
      const task = state(`completed-${index}`)
      runtime.states.set(task.taskId, task)
      runtime.listener!({ type: 'created', state: task })
      task.phase = 'completed'
      runtime.listener!({ type: 'completed', state: task })
    }
    const other = state('other-running')
    runtime.states.set(other.taskId, other)
    runtime.listener!({ type: 'created', state: other })

    const startingTab = store.tabs.find(tab => tab.taskId === 'completed-0')!
    store.activeTab = startingTab.key
    startingTab.starting = true
    store.activeTab = 'main'
    other.phase = 'completed'
    runtime.listener!({ type: 'completed', state: other })
    expect(store.tabs.some(tab => tab.key === startingTab.key)).toBe(true)
    expect(runtime.release).not.toHaveBeenCalledWith('completed-0')

    // 模拟创建消息早于 HTTP 响应，再将新运行绑定回原来的启动页。
    const accepted = state('accepted-run')
    runtime.states.set(accepted.taskId, accepted)
    runtime.listener!({ type: 'created', state: accepted })
    store.bindRun(startingTab, accepted.taskId)
    startingTab.starting = false

    expect(store.tabs.filter(tab => tab.taskId === accepted.taskId)).toHaveLength(1)
    expect(store.tabs.find(tab => tab.key === store.activeTab)).toBe(startingTab)
    expect(store.panels.find(panel => panel.tab.key === startingTab.key)?.runtime).toBe(accepted)
  })

  it('限制自动完成标签，并释放缓存引用，保留手动页与仍在运行的任务', () => {
    store.bootstrap()
    const manual = state('manual')
    manual.phase = 'completed'
    runtime.states.set(manual.taskId, manual)
    store.bindRun(store.addTab(), manual.taskId)
    const active = state('still-running')
    runtime.states.set(active.taskId, active)
    runtime.listener!({ type: 'created', state: active })
    for (let index = 0; index < 23; index++) {
      const task = state(`auto-${index}`)
      task.trigger = TaskTriggerReason.CYCLE
      runtime.states.set(task.taskId, task)
      runtime.listener!({ type: 'created', state: task })
      task.phase = 'completed'
      runtime.listener!({ type: 'completed', state: task })
    }
    expect(store.tabs.filter(tab => tab.automatic)).toHaveLength(21)
    expect(store.tabs.some(tab => tab.taskId === 'still-running')).toBe(true)
    expect(store.tabs.some(tab => tab.taskId === 'manual')).toBe(true)
    expect(store.tabs.find(tab => tab.key === store.activeTab)?.taskId).toBe('auto-22')
    for (const id of ['auto-0', 'auto-1', 'auto-2']) {
      expect(store.tabs.some(tab => tab.taskId === id)).toBe(false)
      expect(runtime.release).toHaveBeenCalledWith(id)
    }
  })

  it('立即保存手动绑定与活动页，合并自动页不修改早到的日志', () => {
    const task = state('run-1')
    runtime.states.set(task.taskId, task)
    store.bootstrap()
    expect(store.tabs).toHaveLength(2)
    store.bindRun(store.tabs[0], task.taskId)
    expect(store.tabs).toHaveLength(1)
    expect(runtime.states.get(task.taskId)?.log).toBe('waiting-run-1')
    expect(runtime.states.get(task.taskId)?.logSeq).toBe(2)
    const workspace = JSON.parse(saved.get('scheduler-tabs-session')!)
    expect(workspace.tabs[0].taskId).toBe(task.taskId)
    expect(workspace.activeTab).toBe('main')
    expect(JSON.stringify(workspace)).not.toContain('waiting-run-1')
  })

  it('同配置的并行运行各自保留，绑定只合并同一运行 UUID', () => {
    store.bootstrap()
    for (const id of ['run-a', 'run-b']) {
      const task = state(id)
      runtime.states.set(id, task)
      runtime.listener!({ type: 'created', state: task })
    }
    store.bindRun(store.tabs[0], 'run-a')
    expect(store.tabs.map(tab => tab.taskId)).toEqual(['run-a', 'run-b'])
    expect(store.panels.map(panel => panel.runtime?.log)).toEqual([
      'waiting-run-a',
      'waiting-run-b',
    ])
    expect(runtime.retain).toHaveBeenCalledWith('run-a')
    expect(runtime.retain).toHaveBeenCalledWith('run-b')
  })
})
