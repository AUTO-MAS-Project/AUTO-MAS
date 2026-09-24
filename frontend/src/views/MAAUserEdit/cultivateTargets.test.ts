import { describe, expect, it } from 'vitest'

import {
  appendOperator,
  levelOptionsWithSaved,
  listGoals,
  parseCultivateTargets,
  removeGoal,
  removeOperator,
  serializeCultivateTargets,
  setEliteLevel,
  tierValues,
  upsertGoal,
} from './cultivateTargets'

describe('parseCultivateTargets', () => {
  it('解析合法条目，elite 档位由 listGoals 取得', () => {
    const json = JSON.stringify([
      {
        operator_id: 'char_1',
        goals: [
          { kind: 'elite', target_id: '', to_level: 1, state: 'in_progress' },
          {
            kind: 'mastery',
            target_id: 'skill_1',
            to_level: 3,
            state: 'not_started',
          },
        ],
      },
      { operator_id: 'char_2', goals: [] },
    ])
    const rows = parseCultivateTargets(json)
    expect(rows).toHaveLength(2)
    expect(rows[0].operatorId).toBe('char_1')
    expect(listGoals(rows[0].rawGoals, 'elite')).toEqual([
      { kind: 'elite', targetId: '', toLevel: 1, state: 'in_progress' },
    ])
    expect(listGoals(rows[0].rawGoals, 'mastery')).toEqual([
      { kind: 'mastery', targetId: 'skill_1', toLevel: 3, state: 'not_started' },
    ])
    expect(rows[1].rawGoals).toEqual([])
  })

  it('跳过非法条目与非法 JSON', () => {
    const json = JSON.stringify([
      { operator_id: '', goals: [] },
      { operator_id: 'char_1' },
      'bad',
      { operator_id: 'char_2', goals: 'not-array' },
    ])
    expect(parseCultivateTargets(json)).toEqual([])
    expect(parseCultivateTargets('not-json')).toEqual([])
    expect(parseCultivateTargets(undefined)).toEqual([])
  })

  it('同一 (kind, targetId) 的重复 goal 只留首条（手改配置防隐形条目）', () => {
    const json = JSON.stringify([
      {
        operator_id: 'char_1',
        goals: [
          { kind: 'elite', target_id: '', to_level: 1, state: 'in_progress' },
          { kind: 'elite', target_id: '', to_level: 2 },
          { kind: 'mastery', target_id: 's1', to_level: 1 },
          { kind: 'mastery', target_id: 's1', to_level: 2 },
        ],
      },
    ])
    const rows = parseCultivateTargets(json)
    expect(rows[0].rawGoals).toEqual([
      { kind: 'elite', target_id: '', to_level: 1, state: 'in_progress' },
      { kind: 'mastery', target_id: 's1', to_level: 1 },
    ])
  })
})

describe('serializeCultivateTargets', () => {
  it('与 parse 往返对称，保留三类 goal 与 state', () => {
    const goals = [
      { kind: 'elite', target_id: '', to_level: 2, state: 'in_progress' },
      { kind: 'mastery', target_id: 'skill_1', to_level: 3, state: 'not_started' },
      {
        kind: 'module',
        target_id: 'uniequip_1',
        to_level: 1,
        state: 'pending_confirm',
      },
    ]
    const rows = parseCultivateTargets(JSON.stringify([{ operator_id: 'char_1', goals }]))
    expect(JSON.parse(serializeCultivateTargets(rows))).toEqual([{ operator_id: 'char_1', goals }])
  })
})

describe('upsertGoal / removeGoal / setEliteLevel', () => {
  it('新增目标带 not_started，更新只改档位并保留 state', () => {
    const base = [{ kind: 'mastery', target_id: 'skill_1', to_level: 1, state: 'in_progress' }]
    const added = upsertGoal(base, {
      kind: 'mastery',
      targetId: 'skill_2',
      toLevel: 2,
    })
    expect(added[1]).toEqual({
      kind: 'mastery',
      target_id: 'skill_2',
      to_level: 2,
      state: 'not_started',
    })
    const raised = upsertGoal(added, {
      kind: 'mastery',
      targetId: 'skill_1',
      toLevel: 3,
    })
    expect(listGoals(raised, 'mastery')[0]).toMatchObject({
      state: 'in_progress',
      toLevel: 3,
    })
  })

  it('removeGoal 按 kind+targetId 定位，elite 不需要 targetId', () => {
    const goals = [
      { kind: 'elite', target_id: '', to_level: 2, state: 'not_started' },
      { kind: 'mastery', target_id: 'skill_1', to_level: 1, state: 'not_started' },
      { kind: 'mastery', target_id: 'skill_2', to_level: 1, state: 'not_started' },
    ]
    expect(listGoals(removeGoal(goals, 'elite', ''), 'elite')).toEqual([])
    const left = removeGoal(goals, 'mastery', 'skill_1')
    expect(listGoals(left, 'mastery').map(g => g.targetId)).toEqual(['skill_2'])
  })

  it('setEliteLevel：null 移除精英化目标，数字 upsert', () => {
    expect(setEliteLevel([], null)).toEqual([])
    const withElite = setEliteLevel([], 2)
    expect(listGoals(withElite, 'elite')[0].toLevel).toBe(2)
    const changed = setEliteLevel(withElite, 1)
    expect(listGoals(changed, 'elite')[0].toLevel).toBe(1)
  })
})

describe('appendOperator / removeOperator', () => {
  it('追加干员默认带精2目标，重复追加忽略', () => {
    const rows = appendOperator([], 'char_1')
    expect(listGoals(rows[0].rawGoals, 'elite')[0].toLevel).toBe(2)
    const again = appendOperator(rows, 'char_1')
    expect(again).toHaveLength(1)
  })

  it('移除干员', () => {
    let rows = appendOperator([], 'char_1')
    rows = appendOperator(rows, 'char_2')
    expect(removeOperator(rows, 'char_1').map(r => r.operatorId)).toEqual(['char_2'])
  })

  it('默认档位受可达上限约束：上限 1 用 1，上限 0 不预置精英化目标', () => {
    const one = appendOperator([], 'char_1', [], 1)
    expect(listGoals(one[0].rawGoals, 'elite')[0].toLevel).toBe(1)
    const none = appendOperator([], 'char_2', [], 0)
    expect(listGoals(none[0].rawGoals, 'elite')).toEqual([])
    expect(none[0].rawGoals).toEqual([])
  })
})

describe('tierValues', () => {
  it('给出 1..上限 的档位；无消耗数据（0/负/非法）为空', () => {
    expect(tierValues(3)).toEqual([1, 2, 3])
    expect(tierValues(1)).toEqual([1])
    expect(tierValues(0)).toEqual([])
    expect(tierValues(-1)).toEqual([])
    expect(tierValues(Number.NaN)).toEqual([])
  })
})

describe('levelOptionsWithSaved', () => {
  it('默认可达档位 ∪ 已存档位（超限保底，不删用户配置）', () => {
    expect(levelOptionsWithSaved(2, 0)).toEqual([1, 2])
    expect(levelOptionsWithSaved(2, 2)).toEqual([1, 2])
    // 已存精 3 而当前可达上限只有 2：仍出现在选项里回显
    expect(levelOptionsWithSaved(2, 3)).toEqual([1, 2, 3])
    // 可达上限为 0（低星/缺数据）但存了目标：只回显已存值
    expect(levelOptionsWithSaved(0, 2)).toEqual([2])
    expect(levelOptionsWithSaved(0, 0)).toEqual([])
  })
})
