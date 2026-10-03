import { describe, expect, it } from 'vitest'
import type { MaaFWTaskInfo, MaaFWTaskOptionValue } from '@/types/script'
import { buildPresetAppliedSnapshot, selectPresetQueueEntries } from './maafwPresetQueue'

const task = (name: string): MaaFWTaskInfo => ({
  name,
  entry: name,
  group: [],
  controller: [],
  resource: [],
  option: [],
  defaultCheck: false,
})

// MRA v3.2.0「周常配置」的形状：开始前任务 + 9 次「自动出征」（各自选章节）+ 结束前任务。
// 后端把第二次起的重复展开成 `<任务名>__MAS_DUP__presetN`。
const SORTIE = '自动出征'
const sortieIds = [
  SORTIE,
  ...Array.from({ length: 8 }, (_, index) => `${SORTIE}__MAS_DUP__preset${index + 2}`),
]
const presetOrder = ['开始前任务', ...sortieIds, '结束前任务']
const presetOptions: Record<string, Record<string, MaaFWTaskOptionValue>> = Object.fromEntries(
  sortieIds.map((taskId, index) => [taskId, { 选择章节: `第${index + 1}章` }])
)
const tasks = [task('开始前任务'), task(SORTIE), task('结束前任务'), task('自动远征')]
const taskByName = new Map(tasks.map(item => [item.name, item] as const))
const validTaskNames = new Set(taskByName.keys())

describe('应用预设时保留重复任务实例', () => {
  it('实例 id 解析回任务名后判断可用，顺序与预设一致', () => {
    const entries = selectPresetQueueEntries(presetOrder, taskByName, validTaskNames)
    expect(entries.map(entry => entry.id)).toEqual(presetOrder)
    expect(entries.filter(entry => entry.task.name === SORTIE)).toHaveLength(9)
  })

  it('快照 11 项、各实例的选项各自保留，与手动复制的实例不冲突', () => {
    const entries = selectPresetQueueEntries(presetOrder, taskByName, validTaskNames)
    const currentOrder = [SORTIE, `${SORTIE}__MAS_DUP__k3j9x0qa`]
    const snapshot = buildPresetAppliedSnapshot(entries, presetOptions, currentOrder, () => false)

    expect(snapshot.taskOrder).toEqual(presetOrder)
    expect(snapshot.taskOrder).toHaveLength(11)
    expect(Object.values(snapshot.taskChecked).every(Boolean)).toBe(true)
    expect(snapshot.taskOptions[`${SORTIE}__MAS_DUP__preset9`]).toEqual({ 选择章节: '第9章' })
    expect(snapshot.taskOptions[SORTIE]).toEqual({ 选择章节: '第1章' })
    expect(snapshot.taskOptions[`${SORTIE}__MAS_DUP__k3j9x0qa`]).toBeUndefined()
    // 选项表是拷贝：之后在队列里改选项不会改到预设本身。
    expect(snapshot.taskOptions[SORTIE]).not.toBe(presetOptions[SORTIE])
  })

  it('原队列里的前置任务保留在最前；当前上下文不可用的任务被滤掉', () => {
    const pretaskId = '__MXU_PRETASK__init'
    const onlyStart = new Map([['开始前任务', taskByName.get('开始前任务')!]])
    const entries = selectPresetQueueEntries(presetOrder, onlyStart, validTaskNames)
    const snapshot = buildPresetAppliedSnapshot(
      entries,
      presetOptions,
      [pretaskId, SORTIE],
      taskId => taskId === pretaskId
    )
    expect(snapshot.taskOrder).toEqual([pretaskId, '开始前任务'])
  })
})
