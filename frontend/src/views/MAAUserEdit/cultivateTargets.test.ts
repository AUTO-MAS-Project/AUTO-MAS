import { describe, expect, it } from 'vitest'

import {
  appendOperator,
  parseCultivateTargets,
  removeOperator,
  serializeCultivateTargets,
  updateLevel,
} from './cultivateTargets'

describe('parseCultivateTargets', () => {
  it('解析合法条目并取 elite 档位', () => {
    const json = JSON.stringify([
      {
        operator_id: 'char_1',
        goals: [
          { kind: 'elite', target_id: '', to_level: 1, state: 'in_progress' },
          { kind: 'mastery', target_id: 'skill_1', to_level: 3, state: 'not_started' },
        ],
      },
      { operator_id: 'char_2', goals: [] },
    ])
    const rows = parseCultivateTargets(json)
    expect(rows).toEqual([
      { operatorId: 'char_1', toLevel: 1, rawGoals: expect.any(Array) },
      { operatorId: 'char_2', toLevel: 2, rawGoals: [] },
    ])
  })

  it('跳过非法条目与非法 JSON', () => {
    const json = JSON.stringify([
      { operator_id: '', goals: [] },
      { goals: [] },
      'garbage',
    ])
    expect(parseCultivateTargets(json)).toEqual([])
    expect(parseCultivateTargets('not-json')).toEqual([])
    expect(parseCultivateTargets(undefined)).toEqual([])
  })
})

describe('serializeCultivateTargets', () => {
  it('替换 elite 档位且原样保留非 elite 目标', () => {
    const rows = parseCultivateTargets(
      JSON.stringify([
        {
          operator_id: 'char_1',
          goals: [
            { kind: 'elite', target_id: '', to_level: 1, state: 'in_progress' },
            { kind: 'module', target_id: 'mod_1', to_level: 2, state: 'not_started' },
          ],
        },
      ])
    ).map(row => ({ ...row, toLevel: 2 }))

    const parsed = JSON.parse(serializeCultivateTargets(rows))
    expect(parsed).toEqual([
      {
        operator_id: 'char_1',
        goals: [
          { kind: 'elite', target_id: '', to_level: 2, state: 'in_progress' },
          { kind: 'module', target_id: 'mod_1', to_level: 2, state: 'not_started' },
        ],
      },
    ])
  })

  it('无 elite 目标的条目追加一条', () => {
    const rows = parseCultivateTargets(
      JSON.stringify([{ operator_id: 'char_2', goals: [] }])
    )
    const parsed = JSON.parse(serializeCultivateTargets(rows))
    expect(parsed[0].goals).toEqual([
      { kind: 'elite', target_id: '', to_level: 2, state: 'not_started' },
    ])
  })
})

describe('rows 操作', () => {
  const base = [{ operatorId: 'char_1', toLevel: 2, rawGoals: [] }]

  it('追加去重且不重置已有档位', () => {
    const withNew = appendOperator(base, 'char_1')
    expect(withNew).toBe(base)

    const added = appendOperator(base, 'char_2')
    expect(added).toHaveLength(2)
    expect(added[1]).toEqual({ operatorId: 'char_2', toLevel: 2, rawGoals: [] })
  })

  it('移除与改档位', () => {
    const two = appendOperator(base, 'char_2')
    expect(removeOperator(two, 'char_1')).toEqual([
      { operatorId: 'char_2', toLevel: 2, rawGoals: [] },
    ])
    expect(updateLevel(two, 'char_2', 1)[1].toLevel).toBe(1)
    // 未命中的干员不改变任何行
    expect(updateLevel(two, 'char_x', 1)).toEqual(two)
  })
})
