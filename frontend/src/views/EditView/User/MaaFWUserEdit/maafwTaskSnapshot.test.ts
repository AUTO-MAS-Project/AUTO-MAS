import { describe, expect, it } from 'vitest'
import type { MaaFWInterfacePreviewData, MaaFWTaskInfo } from '@/types/script'
import {
  MAAFW_TASK_LABEL_MAX_LENGTH,
  duplicateMaaFWQueuedTask,
  normalizeTaskSnapshot,
  parseTaskSnapshot,
  pickMaaFWTaskLabels,
  withMaaFWTaskLabel,
} from './maafwTaskSnapshot'
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

  it('实例显示名只留队列里的实例、去首尾空白后非空的；一个都没有时不写 taskLabels 键', () => {
    const snapshot = normalizeTaskSnapshot(
      {
        taskOrder: ['A', 'A__MAS_DUP__x1', 'B'],
        taskChecked: { B: false },
        taskOptions: {},
        taskLabels: { A: ' 早班 ', A__MAS_DUP__x1: '   ', B: '晚班', Gone: '旧', C: 3 },
      },
      preview(['A', 'B'])
    )
    expect(snapshot.taskLabels).toEqual({ A: '早班' })
    const plain = normalizeTaskSnapshot(
      { taskOrder: ['A'], taskChecked: {}, taskOptions: {}, taskLabels: { A: '' } },
      preview(['A'])
    )
    expect('taskLabels' in plain).toBe(false)
  })
})

describe('MFW 队列实例显示名与复制', () => {
  it('改名：去首尾空白、截到上限；清空或改回原显示名即删掉这一条；不改入参', () => {
    const labels = { A: '旧名' }
    expect(withMaaFWTaskLabel(labels, 'A', '  新名 ', '收菜')).toEqual({ A: '新名' })
    expect(withMaaFWTaskLabel(labels, 'A', '   ', '收菜')).toEqual({})
    expect(withMaaFWTaskLabel(labels, 'A', '收菜', '收菜')).toEqual({})
    expect(withMaaFWTaskLabel(undefined, 'B', 'x'.repeat(60), '收菜')).toEqual({
      B: 'x'.repeat(MAAFW_TASK_LABEL_MAX_LENGTH),
    })
    expect(labels).toEqual({ A: '旧名' })
  })

  it('原名超过上限时不改直接确定：按原名比较，不存截断后的名字', () => {
    const longName = '长'.repeat(45)
    expect(withMaaFWTaskLabel({}, 'A', longName, longName)).toEqual({})
    expect(withMaaFWTaskLabel({ A: '旧名' }, 'A', ` ${longName} `, longName)).toEqual({})
  })

  it('pickMaaFWTaskLabels：非对象给空表，只收给定实例', () => {
    expect(pickMaaFWTaskLabels(null, ['A'])).toEqual({})
    expect(pickMaaFWTaskLabels(['A'], ['A'])).toEqual({})
    expect(pickMaaFWTaskLabels({ A: 'a', B: 'b' }, ['B'])).toEqual({ B: 'b' })
  })

  it('复制：插在原任务正下方，勾选、选项（深拷贝）与显示名一起复制，原快照不动', () => {
    const snapshot = {
      taskOrder: ['A', 'B'],
      taskChecked: { A: true, B: true },
      taskOptions: { A: { o: ['x'] } },
      taskLabels: { A: '账号A' },
    }
    const result = duplicateMaaFWQueuedTask(snapshot, 'A', 'A')
    expect(result).not.toBeNull()
    const { snapshot: next, taskId } = result!
    expect(taskId.startsWith('A__MAS_DUP__')).toBe(true)
    expect(next.taskOrder).toEqual(['A', taskId, 'B'])
    expect(next.taskChecked[taskId]).toBe(true)
    expect(next.taskOptions[taskId]).toEqual({ o: ['x'] })
    expect(next.taskOptions[taskId]).not.toBe(snapshot.taskOptions.A)
    expect((next.taskOptions[taskId].o as string[]) === snapshot.taskOptions.A.o).toBe(false)
    expect(next.taskLabels).toEqual({ A: '账号A', [taskId]: '账号A' })
    expect(snapshot.taskOrder).toEqual(['A', 'B'])
    expect(snapshot.taskLabels).toEqual({ A: '账号A' })
  })

  it('复制没改过名的实例：副本也没有显示名，不凭空写 taskLabels 键', () => {
    const snapshot = { taskOrder: ['A'], taskChecked: { A: true }, taskOptions: {} }
    const { snapshot: next, taskId } = duplicateMaaFWQueuedTask(snapshot, 'A', 'A')!
    expect(next.taskOrder).toEqual(['A', taskId])
    expect('taskLabels' in next).toBe(false)
    expect(next.taskOptions).toEqual({})
    expect(duplicateMaaFWQueuedTask(snapshot, 'Gone', 'Gone')).toBeNull()
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
