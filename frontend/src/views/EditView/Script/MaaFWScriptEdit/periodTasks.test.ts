import { describe, expect, it } from 'vitest'
import type { MaaFWTaskInfo } from '@/types/script'
import {
  PERIOD_KEYS,
  buildPeriodTaskOptions,
  isPretaskTask,
  parseTaskNameList,
  stringifyTaskNameList,
} from './periodTasks'

const task = (name: string, extra: Partial<MaaFWTaskInfo> = {}): MaaFWTaskInfo => ({
  name,
  entry: name,
  group: [],
  controller: [],
  resource: [],
  option: [],
  defaultCheck: false,
  ...extra,
})

describe('MFW 脚本页周期任务', () => {
  it('pretask 伪任务按 entry 认，name 前缀兜底', () => {
    expect(isPretaskTask(task('Anything', { entry: 'MXU_PRETASK' }))).toBe(true)
    expect(isPretaskTask(task('__MXU_PRETASK__Start'))).toBe(true)
    expect(isPretaskTask(task('Daily'))).toBe(false)
  })

  it('三个周期键与配置字段同名', () => {
    expect(PERIOD_KEYS).toEqual(['DailyOnceTasks', 'WeeklyOnceTasks', 'MonthlyOnceTasks'])
  })

  it('下拉选项去掉 pretask，有 label 时带上任务名，保持原顺序', () => {
    expect(
      buildPeriodTaskOptions([
        task('Start', { entry: 'MXU_PRETASK' }),
        task('Daily', { label: '日常' }),
        task('Weekly'),
        task('__MXU_PRETASK__Close'),
      ])
    ).toEqual([
      { label: '日常（Daily）', value: 'Daily' },
      { label: 'Weekly', value: 'Weekly' },
    ])
  })

  it('任务名列表兼容 JSON 字符串与数组，坏数据收敛成空数组', () => {
    expect(parseTaskNameList('["Daily","Weekly"]')).toEqual(['Daily', 'Weekly'])
    expect(parseTaskNameList(['Daily', 1, null, 'Weekly'])).toEqual(['Daily', 'Weekly'])
    expect(parseTaskNameList('["Daily", 2]')).toEqual(['Daily'])
    expect(parseTaskNameList('{"a":1}')).toEqual([])
    expect(parseTaskNameList('not json')).toEqual([])
    expect(parseTaskNameList('   ')).toEqual([])
    expect(parseTaskNameList(undefined)).toEqual([])
    expect(parseTaskNameList(42)).toEqual([])
  })

  it('写回是 JSON 字符串，能被原样读回', () => {
    const saved = stringifyTaskNameList(['Daily', 'Weekly'])
    expect(saved).toBe('["Daily","Weekly"]')
    expect(parseTaskNameList(saved)).toEqual(['Daily', 'Weekly'])
  })
})
