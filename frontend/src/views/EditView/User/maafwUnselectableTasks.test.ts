import { describe, expect, it } from 'vitest'
import { isUnselectableMaaFWTask, unselectableMaaFWQueueNotices } from './maafwUnselectableTasks'

// 形状照后端预览：可选任务 unselectableReason 为 null，特调声明的给原因
const REASON = '需手动进入对应页面（M9A 没有自动导航）'
const DAILY = { name: '收取荒原', label: '收取荒原', unselectableReason: null }
const ARCADE = { name: '8-bit 街机秀', label: '8-bit 街机秀', unselectableReason: REASON }
const CRITTER = { name: '翻斗棋速刷', label: null, unselectableReason: REASON }
const OTHER = { name: '别的', label: '别的', unselectableReason: '另一个原因' }
const name = (task: { name: string; label?: string | null }) => task.label || task.name

describe('isUnselectableMaaFWTask', () => {
  it('只认后端给了原因的任务', () => {
    expect(isUnselectableMaaFWTask(ARCADE)).toBe(true)
    expect(isUnselectableMaaFWTask(DAILY)).toBe(false)
    expect(isUnselectableMaaFWTask({})).toBe(false)
    expect(isUnselectableMaaFWTask({ unselectableReason: '' })).toBe(false)
    expect(isUnselectableMaaFWTask(undefined)).toBe(false)
  })
})

describe('unselectableMaaFWQueueNotices', () => {
  it('同一原因并成一条、任务名去重（同一任务加了两份只列一次）', () => {
    const queued = [DAILY, ARCADE, CRITTER, ARCADE].map(task => ({ task }))
    expect(unselectableMaaFWQueueNotices(queued, name)).toEqual([
      { tasks: '8-bit 街机秀、翻斗棋速刷', reason: REASON },
    ])
  })

  it('不同原因各一条，按首次出现的顺序', () => {
    const queued = [OTHER, ARCADE].map(task => ({ task }))
    expect(unselectableMaaFWQueueNotices(queued, name)).toEqual([
      { tasks: '别的', reason: '另一个原因' },
      { tasks: '8-bit 街机秀', reason: REASON },
    ])
  })

  it('队列里没有不可选任务时没有提示', () => {
    expect(unselectableMaaFWQueueNotices([{ task: DAILY }], name)).toEqual([])
    expect(unselectableMaaFWQueueNotices<typeof DAILY>([], name)).toEqual([])
  })
})
