import { describe, expect, it } from 'vitest'
import {
  PLAN_ROTATE_DAYS_DEFAULT,
  clampRotateDays,
  planColumnKeys,
  planColumnPath,
  planDayKeys,
  planDayLabel,
  readPlanColumn,
} from './planDays'

describe('clampRotateDays', () => {
  it('读不出整数时给默认值', () => {
    expect(clampRotateDays(undefined)).toBe(PLAN_ROTATE_DAYS_DEFAULT)
    expect(clampRotateDays('abc')).toBe(PLAN_ROTATE_DAYS_DEFAULT)
    expect(clampRotateDays(3.5)).toBe(PLAN_ROTATE_DAYS_DEFAULT)
  })

  it('越界夹到 1~31', () => {
    expect(clampRotateDays(0)).toBe(1)
    expect(clampRotateDays(99)).toBe(31)
    expect(clampRotateDays('8')).toBe(8)
  })
})

describe('planDayKeys', () => {
  it('周计划给七天', () => {
    expect(planDayKeys('Weekly', 3)).toEqual([
      'Monday',
      'Tuesday',
      'Wednesday',
      'Thursday',
      'Friday',
      'Saturday',
      'Sunday',
    ])
  })

  it('全局模式也给七天：七列照旧摆着，只是不可编辑', () => {
    expect(planDayKeys('ALL', 3)).toHaveLength(7)
  })

  it('多天轮换按天数给 "1"~"N"', () => {
    expect(planDayKeys('Rotate', 3)).toEqual(['1', '2', '3'])
  })

  it('轮换天数越界时夹回来', () => {
    expect(planDayKeys('Rotate', 0)).toEqual(['1'])
    expect(planDayKeys('Rotate', undefined)).toHaveLength(PLAN_ROTATE_DAYS_DEFAULT)
  })
})

describe('planColumnKeys', () => {
  it('ALL 永远在最前', () => {
    expect(planColumnKeys('Rotate', 2)).toEqual(['ALL', '1', '2'])
    expect(planColumnKeys('Weekly', 7)[0]).toBe('ALL')
  })
})

describe('planDayLabel', () => {
  it('星期名走 plan.week', () => {
    expect(planDayLabel('Monday')).toEqual({ key: 'plan.week.Monday', params: {} })
  })

  it('轮换天走 plan.rotateDay', () => {
    expect(planDayLabel('3')).toEqual({ key: 'plan.rotateDay', params: { n: '3' } })
  })
})

describe('readPlanColumn 与 planColumnPath', () => {
  const tableData = {
    ALL: { Key: { Wanted: [1, -1, 1] } },
    Days: { Monday: { Key: { Wanted: [2, -1, 3] } } },
  }

  it('ALL 在接口顶层，每天在 Days 里', () => {
    expect(readPlanColumn(tableData, 'ALL')).toEqual({ Key: { Wanted: [1, -1, 1] } })
    expect(readPlanColumn(tableData, 'Monday')).toEqual({ Key: { Wanted: [2, -1, 3] } })
    expect(readPlanColumn(tableData, 'Tuesday')).toBeUndefined()
    expect(readPlanColumn(null, 'ALL')).toBeUndefined()
  })

  it('写路径同样是两级', () => {
    expect(planColumnPath('ALL', 'Key')).toBe('ALL.Key')
    expect(planColumnPath('Monday', 'Stage')).toBe('Days.Monday.Stage')
  })
})
