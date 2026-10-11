import { describe, expect, it } from 'vitest'
import { applyMixedPart, isFieldEnabled, partOptionMax, readDayFields } from './baahPlanKey'

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

describe('applyMixedPart', () => {
  it('只写目标类别，别的类别不补默认值', () => {
    const write = applyMixedPart({}, 'Event', 0, 4)
    expect(write.fields).toEqual({ Event: [4, 1] })
    expect(write.corrected).toBe(false)
  })

  it('别的类别原样带过去', () => {
    const write = applyMixedPart({ Wanted: [2, 3, 4] }, 'Event', 0, 4)
    expect(write.fields).toEqual({ Wanted: [2, 3, 4], Event: [4, 1] })
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

  it('悬赏通缉的关卡位可以填 -1（倒数第一个），不纠正', () => {
    const write = applyMixedPart({ Wanted: [1, 2, 3] }, 'Wanted', 1, -1)
    expect(write.fields.Wanted).toEqual([1, -1, 3])
    expect(write.corrected).toBe(false)
  })

  it('活动关卡只有关卡与次数两位', () => {
    const write = applyMixedPart(undefined, 'Event', 1, 5)
    expect(write.fields.Event).toEqual([1, 5])
  })
})

describe('partOptionMax', () => {
  it('次数位给到 10', () => {
    expect(partOptionMax('plan.baah.partTimes')).toBe(10)
  })

  it('地区与学院给到 10', () => {
    expect(partOptionMax('plan.baah.partRegion')).toBe(10)
    expect(partOptionMax('plan.baah.partAcademy')).toBe(10)
  })

  it('章节位给到 30', () => {
    expect(partOptionMax('plan.baah.partChapter')).toBe(30)
  })

  it('关卡位与关卡序号给到 15', () => {
    expect(partOptionMax('plan.baah.partLevel')).toBe(15)
    expect(partOptionMax('plan.baah.partLevelHighest')).toBe(15)
    expect(partOptionMax('plan.baah.partStageIndex')).toBe(15)
  })
})

describe('isFieldEnabled', () => {
  it('有值的类算启用', () => {
    expect(isFieldEnabled({ Hard: [1, 2, 3] }, 'Hard')).toBe(true)
  })

  it('空数组是「今天不打」', () => {
    expect(isFieldEnabled({ Hard: [] }, 'Hard')).toBe(false)
  })

  it('缺席也当作没启用', () => {
    expect(isFieldEnabled({ Hard: [1, 2, 3] }, 'Normal')).toBe(false)
    expect(isFieldEnabled(undefined, 'Hard')).toBe(false)
  })
})
