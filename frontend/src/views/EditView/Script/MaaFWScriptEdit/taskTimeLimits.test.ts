import { describe, expect, it } from 'vitest'
import {
  countTaskLimitOverrides,
  normalizeTaskLimitMinutes,
  parseTaskLimitOverrides,
  pruneTaskLimitOverrides,
  stringifyTaskLimitOverrides,
  taskLimitDraftToOverrides,
} from './taskTimeLimits'

describe('MFW 按任务设置的单任务时限', () => {
  it('分钟数收成非负整数，写坏的当 0（不限）', () => {
    expect(normalizeTaskLimitMinutes(45)).toBe(45)
    expect(normalizeTaskLimitMinutes('60')).toBe(60)
    expect(normalizeTaskLimitMinutes(12.9)).toBe(12)
    expect(normalizeTaskLimitMinutes(-5)).toBe(0)
    expect(normalizeTaskLimitMinutes('abc')).toBe(0)
    expect(normalizeTaskLimitMinutes(null)).toBe(0)
  })

  it('兼容 JSON 字符串与对象，坏数据收敛成空表', () => {
    expect(parseTaskLimitOverrides('{"自动深眠": 60, "B": 0}')).toEqual({ 自动深眠: 60, B: 0 })
    expect(parseTaskLimitOverrides({ A: '30', B: 'x' })).toEqual({ A: 30, B: 0 })
    expect(parseTaskLimitOverrides('{ }')).toEqual({})
    expect(parseTaskLimitOverrides('[1]')).toEqual({})
    expect(parseTaskLimitOverrides('not json')).toEqual({})
    expect(parseTaskLimitOverrides('  ')).toEqual({})
    expect(parseTaskLimitOverrides(undefined)).toEqual({})
    expect(parseTaskLimitOverrides({ '': 5 })).toEqual({})
  })

  it('写回是 JSON 字符串，能被原样读回', () => {
    const saved = stringifyTaskLimitOverrides({ 智能均衡刷材料: 45, 自动深眠: 60 })
    expect(saved).toBe('{"智能均衡刷材料":45,"自动深眠":60}')
    expect(parseTaskLimitOverrides(saved)).toEqual({ 智能均衡刷材料: 45, 自动深眠: 60 })
    expect(stringifyTaskLimitOverrides({})).toBe('{}')
  })

  it('草稿留空不存键，填了数字（含 0、含等于默认值）就存', () => {
    expect(
      taskLimitDraftToOverrides({ A: null, B: undefined, C: 0, D: 45, E: 90, F: Number.NaN })
    ).toEqual({ C: 0, D: 45, E: 90 })
    expect(taskLimitDraftToOverrides({})).toEqual({})
  })

  it('读到 interface 后只留还在的任务名', () => {
    expect(pruneTaskLimitOverrides({ A: 10, Gone: 20, C: 0 }, new Set(['A', 'C', 'D']))).toEqual({
      A: 10,
      C: 0,
    })
  })

  it('摘要按单独设置的任务数计', () => {
    expect(countTaskLimitOverrides({})).toBe(0)
    expect(countTaskLimitOverrides({ A: 0, B: 45 })).toBe(2)
  })
})
