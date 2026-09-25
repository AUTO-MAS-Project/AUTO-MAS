import { describe, expect, it } from 'vitest'
import {
  isManagedMaaFWTask,
  managedMaaFWQueueSummary,
  withoutManagedMaaFWTasks,
} from './maafwManagedTasks'
import { resolveMaaFWFlavor } from '@/composables/useMaaFWFlavor'

// 任务表照 M9A v4.10.0 的 interface：启动 / 切号 / 关闭三个受管任务 + 两个普通任务
const TASKS = [
  { name: '启动游戏', label: '启动游戏', entry: 'StartUp' },
  { name: '收取荒原', label: '收取荒原', entry: 'Wilderness' },
  { name: '切换账号', label: '切换账号', entry: 'SwitchAccount' },
  { name: '常规作战', label: '常规作战', entry: 'Combat' },
  { name: '关闭游戏', label: '关闭游戏', entry: 'Close1999' },
]

const m9aEntries = new Set(resolveMaaFWFlavor('M9A').managedTaskEntries)
const maafwEntries = new Set(resolveMaaFWFlavor('MaaFW').managedTaskEntries)

describe('MaaFW 特调的受管任务', () => {
  it('M9A 的「添加任务」与预设模板候选里没有启动游戏、切换账号、关闭游戏', () => {
    expect(withoutManagedMaaFWTasks(TASKS, m9aEntries).map(task => task.name)).toEqual([
      '收取荒原',
      '常规作战',
    ])
  })

  it('通用 MaaFW 与没声明受管任务的特调一个都不滤', () => {
    expect(withoutManagedMaaFWTasks(TASKS, maafwEntries)).toHaveLength(TASKS.length)
    expect(resolveMaaFWFlavor('MSS').managedTaskEntries).toEqual([])
  })

  it('按 entry 判，不按任务名', () => {
    expect(isManagedMaaFWTask({ entry: 'SwitchAccount' }, m9aEntries)).toBe(true)
    expect(isManagedMaaFWTask({ entry: '' }, m9aEntries)).toBe(false)
    expect(isManagedMaaFWTask(null, m9aEntries)).toBe(false)
  })

  it('队列里残留多个切换账号时给出个数与去重后的任务名，没有就不提示', () => {
    const queued = [TASKS[1], TASKS[2], TASKS[2], TASKS[3]]
    expect(managedMaaFWQueueSummary(queued, m9aEntries, task => task.label)).toEqual({
      count: 2,
      tasks: '切换账号',
    })
    expect(managedMaaFWQueueSummary([TASKS[1]], m9aEntries, task => task.label)).toBeNull()
    expect(managedMaaFWQueueSummary(queued, maafwEntries, task => task.label)).toBeNull()
  })
})
