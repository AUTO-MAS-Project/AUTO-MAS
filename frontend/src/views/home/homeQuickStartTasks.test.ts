import { describe, expect, it } from 'vitest'
import {
  launchHomeTasks,
  normalizeHomeQuickStartSelection,
  retainSelectedTaskIds,
  toHomeTaskOptions,
} from './homeQuickStartTasks'

describe('home quick-start task selection', () => {
  it('normalizes persisted selections without placeholders or duplicates', () => {
    expect(
      normalizeHomeQuickStartSelection([
        'task-2',
        '',
        'task-1',
        'task-2',
        'mock-daily-queue',
        null,
        42,
      ])
    ).toEqual(['task-2', 'task-1'])
  })

  it('filters unavailable options and preserves the user selection order', () => {
    const options = toHomeTaskOptions([
      { label: '未选择', value: null },
      { label: '队列', value: 'queue-1' },
      { label: '脚本', value: 'script-1' },
    ])

    expect(options).toEqual([
      { label: '队列', value: 'queue-1' },
      { label: '脚本', value: 'script-1' },
    ])
    expect(retainSelectedTaskIds(['script-1', 'deleted-task', 'queue-1'], options)).toEqual([
      'script-1',
      'queue-1',
    ])
  })
})

describe('home quick-start batch launch', () => {
  it('continues remaining tasks and reports successful and failed items', async () => {
    const requestedTaskIds: string[] = []
    const startedTasks: string[] = []
    const startTask = async (taskId: string) => {
      requestedTaskIds.push(taskId)
      if (taskId === 'task-1') throw new Error('scheduler unavailable')
      if (taskId === 'task-2') return { taskId: '', message: 'task is running' }
      return { code: 200, taskId: `run-${taskId}` }
    }

    const outcome = await launchHomeTasks({
      taskIds: ['task-1', 'task-2', 'task-3'],
      options: [
        { label: '任务一', value: 'task-1' },
        { label: '任务二', value: 'task-2' },
        { label: '任务三', value: 'task-3' },
      ],
      fallbackLabel: '首页快速任务',
      failureReason: '开始任务失败',
      startTask,
      onTaskStarted: result => startedTasks.push(result.taskId),
    })

    expect(requestedTaskIds).toEqual(['task-1', 'task-2', 'task-3'])
    expect(startedTasks).toEqual(['run-task-3'])
    expect(outcome.started.map(result => result.selectedTaskId)).toEqual(['task-3'])
    expect(outcome.failed).toEqual([
      { taskLabel: '任务一', reason: 'scheduler unavailable' },
      { taskLabel: '任务二', reason: 'task is running' },
    ])
  })

  it('does not classify callback failures as task-start failures', async () => {
    await expect(
      launchHomeTasks({
        taskIds: ['task-1'],
        options: [{ label: '任务一', value: 'task-1' }],
        fallbackLabel: '首页快速任务',
        failureReason: '开始任务失败',
        startTask: async () => ({ code: 200, taskId: 'run-task-1' }),
        onTaskStarted: () => {
          throw new Error('tracking unavailable')
        },
      })
    ).rejects.toThrow('tracking unavailable')
  })
})
