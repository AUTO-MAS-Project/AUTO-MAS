import { describe, expect, it } from 'vitest'
import type { MaaFWInterfacePreviewData, MaaFWTaskInfo } from '@/types/script'
import { normalizeTaskSnapshot, parseTaskSnapshot } from './maafwTaskSnapshot'
import { getDefaultMaaFWUserData } from './maafwUserDefaults'

const task = (name: string): MaaFWTaskInfo => ({
  name,
  entry: name,
  group: [],
  controller: [],
  resource: [],
  option: [],
  defaultCheck: false,
})

const preview = (names: string[]) =>
  ({ tasks: names.map(task) }) as unknown as MaaFWInterfacePreviewData

describe('MFW 用户页任务快照', () => {
  it('解析：空值给空对象，字符串按 JSON 读，坏 JSON 给空对象，对象原样返回', () => {
    expect(parseTaskSnapshot(null)).toEqual({})
    expect(parseTaskSnapshot('')).toEqual({})
    expect(parseTaskSnapshot('{ }')).toEqual({})
    expect(parseTaskSnapshot('not json')).toEqual({})
    expect(parseTaskSnapshot('{"taskOrder":["A"]}')).toEqual({ taskOrder: ['A'] })
    const raw = { taskOrder: ['A'], taskChecked: {}, taskOptions: {} }
    expect(parseTaskSnapshot(raw)).toBe(raw)
  })

  it('默认只留 interface 认得的任务（副本实例按任务名认），未勾选的不进队列', () => {
    const snapshot = normalizeTaskSnapshot(
      JSON.stringify({
        taskOrder: ['A', 'Gone', 'A__MAS_DUP__x1', 'B', 3],
        taskChecked: { B: false },
        taskOptions: { A: { o: 'v' }, B: { o: 'w' }, Gone: { o: 'z' } },
      }),
      preview(['A', 'B'])
    )
    expect(snapshot).toEqual({
      taskOrder: ['A', 'A__MAS_DUP__x1'],
      taskChecked: { A: true, A__MAS_DUP__x1: true },
      taskOptions: { A: { o: 'v' } },
    })
  })

  it('keepMissing 保留 interface 已经没有的任务（虚影），选项跟着留下', () => {
    const snapshot = normalizeTaskSnapshot(
      { taskOrder: ['A', 'Gone'], taskChecked: {}, taskOptions: { Gone: { o: 'z' } } },
      preview(['A']),
      { keepMissing: true }
    )
    expect(snapshot).toEqual({
      taskOrder: ['A', 'Gone'],
      taskChecked: { A: true, Gone: true },
      taskOptions: { Gone: { o: 'z' } },
    })
  })

  it('没有 interface 时默认什么都不认，keepMissing 时全保留', () => {
    const raw = { taskOrder: ['A'], taskChecked: {}, taskOptions: {} }
    expect(normalizeTaskSnapshot(raw, null).taskOrder).toEqual([])
    expect(normalizeTaskSnapshot(raw, null, { keepMissing: true }).taskOrder).toEqual(['A'])
    expect(normalizeTaskSnapshot('{ }', null)).toEqual({
      taskOrder: [],
      taskChecked: {},
      taskOptions: {},
    })
  })
})

describe('MFW 用户页默认值', () => {
  it('每次给一份新对象，改了不影响下一份', () => {
    const first = getDefaultMaaFWUserData()
    first.Info.Name = '改过'
    first.Task.TaskSnapshot = 'x'
    const second = getDefaultMaaFWUserData()
    expect(second.Info.Name).toBe('')
    expect(second.Task.TaskSnapshot).toBe('{ }')
  })

  it('四个分区齐全，关键默认值不变', () => {
    const defaults = getDefaultMaaFWUserData()
    expect(Object.keys(defaults)).toEqual(['Info', 'Task', 'Notify', 'Data'])
    expect(defaults.Info).toMatchObject({
      Status: true,
      Mode: '用户',
      IfQuickConfig: true,
      RemainedDay: -1,
      PlanMode: 'Fixed',
    })
    expect(defaults.Task).toEqual({ SelectedPreset: '', TaskSnapshot: '{ }' })
    expect(defaults.Data).toMatchObject({ LastProxyStatus: '未知', PeriodTaskRecords: '{ }' })
  })
})
