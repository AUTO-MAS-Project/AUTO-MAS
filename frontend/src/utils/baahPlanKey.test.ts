import { describe, expect, it } from 'vitest'
import {
  BAAH_KEY_FIELD_BY_NAME,
  allowsHighestStage,
  applyMixedPart,
  applySingleNumber,
  buildSingleDayKey,
  fillDayFields,
  partIndexOf,
  readDayFields,
  readSingleCell,
  resolveDayKind,
  type BAAHKeyFieldName,
} from './baahPlanKey'

const ALL_EMPTY = {
  Event: [],
  Wanted: [],
  Special: [],
  Exchange: [],
  Hard: [],
  Normal: [],
} as Record<BAAHKeyFieldName, number[]>

describe('readDayFields', () => {
  it('缺席的类别不补默认值', () => {
    expect(readDayFields({ Key: { Wanted: [1, -1, 1] } })).toEqual({ Wanted: [1, -1, 1] })
  })

  it('空数组保持空数组', () => {
    expect(readDayFields({ Key: { Wanted: [], Normal: [1, 2, -1] } })).toEqual({
      Wanted: [],
      Normal: [1, 2, -1],
    })
  })

  it('后端序列化出的 null 与字段缺席同义', () => {
    expect(readDayFields({ Key: { Event: null } })).toEqual({})
  })

  it('没有 Key 外壳的裸 key 也能读', () => {
    expect(readDayFields({ Hard: [2, 3, 5] })).toEqual({ Hard: [2, 3, 5] })
  })

  it('位数不足时补到界面暴露的位', () => {
    expect(readDayFields({ Key: { Event: [3] } })).toEqual({ Event: [3, 1] })
  })

  it('后端允许的额外位原样保留', () => {
    expect(readDayFields({ Key: { Hard: [2, 3, 5, 1] } })).toEqual({ Hard: [2, 3, 5, 1] })
  })

  it('读不出东西时给空对象', () => {
    expect(readDayFields(null)).toEqual({})
    expect(readDayFields(undefined)).toEqual({})
  })
})

describe('fillDayFields', () => {
  it('缺席与空数组都补成该类的默认值', () => {
    const filled = fillDayFields({ Wanted: [] })
    expect(filled.Wanted).toEqual([1, -1, 1])
    expect(filled.Event).toEqual([1, 1])
    expect(filled.Normal).toEqual([1, 1, -1])
  })
})

describe('resolveDayKind', () => {
  it('恰好一类有值时判为该类', () => {
    expect(resolveDayKind({ Wanted: [1, -1, 1], Event: [] })).toBe('Wanted')
  })

  it('恰好一类缺席、其余五类空数组时也认出来', () => {
    // 缺席是「不干预」，空数组是「不打」，两者都表达这一天只交给这一类
    expect(resolveDayKind({ Event: [], Special: [], Exchange: [], Hard: [], Normal: [] })).toBe(
      'Wanted'
    )
  })

  it('六类全空数组是「不打」', () => {
    expect(resolveDayKind(ALL_EMPTY)).toBe('')
  })

  it('多类有值是混打的排法，不当作每天一类', () => {
    expect(resolveDayKind(fillDayFields({}))).toBe('')
  })

  it('没有数据时是「不打」', () => {
    expect(resolveDayKind(undefined)).toBe('')
  })
})

describe('partIndexOf', () => {
  it('活动关卡只有关卡与次数两位', () => {
    const spec = BAAH_KEY_FIELD_BY_NAME.Event
    expect(partIndexOf(spec, 'stage')).toBe(0)
    expect(partIndexOf(spec, 'times')).toBe(1)
  })

  it('其余五类以关卡与次数收尾', () => {
    const names: BAAHKeyFieldName[] = ['Wanted', 'Special', 'Exchange', 'Hard', 'Normal']
    for (const name of names) {
      const spec = BAAH_KEY_FIELD_BY_NAME[name]
      expect(partIndexOf(spec, 'stage')).toBe(1)
      expect(partIndexOf(spec, 'times')).toBe(2)
    }
  })
})

describe('readSingleCell', () => {
  it('读出一类的关卡与次数', () => {
    expect(readSingleCell({ Hard: [2, 3, 5] })).toEqual({ kind: 'Hard', stage: 3, times: 5 })
  })

  it('旧数据里恰好一类缺席时按默认值给出可编的值', () => {
    const legacy = { Event: [], Special: [], Exchange: [], Hard: [], Normal: [] }
    expect(readSingleCell(legacy)).toEqual({ kind: 'Wanted', stage: -1, times: 1 })
  })

  it('没选类时三行都没有值', () => {
    expect(readSingleCell(ALL_EMPTY)).toEqual({ kind: '', stage: 1, times: 1 })
  })
})

describe('buildSingleDayKey', () => {
  it('选中那一类有值，其余五类空数组', () => {
    expect(buildSingleDayKey('Hard', [1, 2, 3])).toEqual({ ...ALL_EMPTY, Hard: [1, 2, 3] })
  })

  it('不打时六类全空', () => {
    expect(buildSingleDayKey('', [])).toEqual(ALL_EMPTY)
  })
})

describe('applySingleNumber', () => {
  it('改次数不动关卡', () => {
    const write = applySingleNumber({ Hard: [2, 3, 5] }, 'times', 9)
    expect(write?.fields).toEqual(buildSingleDayKey('Hard', [2, 3, 9]))
    expect(write?.corrected).toBe(false)
  })

  it('困难图的关卡填 0 当场改成 1', () => {
    const write = applySingleNumber({ Hard: [2, 3, 5] }, 'stage', 0)
    expect(write?.fields).toEqual(buildSingleDayKey('Hard', [2, 1, 5]))
    expect(write?.corrected).toBe(true)
  })

  it('悬赏通缉的关卡位可以填 -1（最高关）', () => {
    const write = applySingleNumber({ Wanted: [1, 2, 3] }, 'stage', -1)
    expect(write?.fields).toEqual(buildSingleDayKey('Wanted', [1, -1, 3]))
    expect(write?.corrected).toBe(false)
  })

  it('次数位填 0 不纠正', () => {
    const write = applySingleNumber({ Wanted: [1, 2, 3] }, 'times', 0)
    expect(write?.fields).toEqual(buildSingleDayKey('Wanted', [1, 2, 0]))
    expect(write?.corrected).toBe(false)
  })

  it('输入框给回空值时退回原来的取值', () => {
    const write = applySingleNumber({ Hard: [2, 3, 5] }, 'stage', null)
    expect(write?.fields).toEqual(buildSingleDayKey('Hard', [2, 3, 5]))
  })

  it('没选类时改不动', () => {
    expect(applySingleNumber(ALL_EMPTY, 'times', 3)).toBeNull()
  })
})

describe('applyMixedPart', () => {
  it('缺席的类别按默认值补齐后一起提交', () => {
    const write = applyMixedPart({}, 'Event', 0, 4)
    expect(write.fields).toEqual({
      Event: [4, 1],
      Wanted: [1, -1, 1],
      Special: [1, -1, 1],
      Exchange: [1, -1, 1],
      Hard: [1, 1, -1],
      Normal: [1, 1, -1],
    })
    expect(write.corrected).toBe(false)
  })

  it('保留没在界面上暴露的后端位', () => {
    const write = applyMixedPart({ Hard: [2, 3, 5, 1] }, 'Hard', 1, 4)
    expect(write.fields.Hard).toEqual([2, 4, 5, 1])
  })

  it('普通图的关卡填 0 改成 1', () => {
    const write = applyMixedPart({ Normal: [1, 2, 3] }, 'Normal', 1, 0)
    expect(write.fields.Normal).toEqual([1, 1, 3])
    expect(write.corrected).toBe(true)
  })
})

describe('allowsHighestStage', () => {
  it('悬赏通缉、特殊任务、学园交流会可以选「最高关」', () => {
    expect(allowsHighestStage('Wanted')).toBe(true)
    expect(allowsHighestStage('Special')).toBe(true)
    expect(allowsHighestStage('Exchange')).toBe(true)
  })

  it('困难与普通关卡的关卡位不能填 -1', () => {
    expect(allowsHighestStage('Hard')).toBe(false)
    expect(allowsHighestStage('Normal')).toBe(false)
  })

  it('活动关卡没有「最高关」这一说', () => {
    expect(allowsHighestStage('Event')).toBe(false)
  })

  it('还没选类时不出现「最高关」', () => {
    expect(allowsHighestStage('')).toBe(false)
  })
})
