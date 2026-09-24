import { describe, expect, it } from 'vitest'
import type { TaskRuntimeState } from '@/composables/useTaskRuntimeState'
import { isScriptConfigLocked } from './scriptConfigLock'

const createTask = (overrides: Partial<TaskRuntimeState> = {}): TaskRuntimeState => ({
  taskId: 'task-1',
  mode: 'AutoProxy',
  queueId: null,
  scriptId: 'script-1',
  userId: null,
  stopping: false,
  isCycle: false,
  scripts: [{ scriptId: 'script-1', scriptType: 'MAA' }],
  taskInfo: [],
  cycleNextList: [],
  log: '',
  phase: 'active',
  taskName: null,
  taskType: null,
  result: null,
  outcome: null,
  error: null,
  completedAt: null,
  ...overrides,
})

describe('isScriptConfigLocked', () => {
  it.each(['AutoProxy', 'ScriptConfig', 'Update'] as const)(
    'locks the exact target script while a %s task is active',
    mode => {
      expect(isScriptConfigLocked([createTask({ mode })], 'script-1')).toBe(true)
      expect(isScriptConfigLocked([createTask({ mode })], 'script-2')).toBe(false)
    }
  )

  it('locks a sequential queue only while its target script is running', () => {
    const queueTask = createTask({
      scriptId: null,
      queueId: 'queue-1',
      scripts: [
        { scriptId: 'script-1', scriptType: 'MAA' },
        { scriptId: 'script-2', scriptType: 'SRC' },
      ],
      taskInfo: [
        { script_id: 'script-1', name: 'MAA', status: '完成', userList: [] },
        { script_id: 'script-2', name: 'SRC', status: '等待', userList: [] },
      ],
    })

    expect(isScriptConfigLocked([queueTask], 'script-1')).toBe(false)
    expect(isScriptConfigLocked([queueTask], 'script-2')).toBe(false)

    queueTask.taskInfo[1].status = '运行'
    expect(isScriptConfigLocked([queueTask], 'script-2')).toBe(true)
  })

  it('locks only the running entry of a cycle task', () => {
    const cycleTask = createTask({
      mode: 'CycleRun',
      isCycle: true,
      scriptId: null,
      queueId: 'queue-1',
      scripts: [
        { scriptId: 'script-1', scriptType: 'MAA' },
        { scriptId: 'script-2', scriptType: 'SRC' },
      ],
      cycleNextList: [
        {
          queueItemId: 'item-1',
          scriptId: 'script-1',
          scriptName: 'MAA',
          nextRunAt: '',
          isDue: true,
          isRunning: true,
        },
        {
          queueItemId: 'item-2',
          scriptId: 'script-2',
          scriptName: 'SRC',
          nextRunAt: '',
          isDue: false,
          isRunning: false,
        },
      ],
    })

    expect(isScriptConfigLocked([cycleTask], 'script-1')).toBe(true)
    expect(isScriptConfigLocked([cycleTask], 'script-2')).toBe(false)
  })

  it('unlocks scripts after the task completes', () => {
    expect(isScriptConfigLocked([createTask({ phase: 'completed' })], 'script-1')).toBe(false)
  })
})
