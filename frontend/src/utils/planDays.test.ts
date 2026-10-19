import { describe, expect, it } from 'vite-plus/test'
import {
  PLAN_ROTATE_DAYS_DEFAULT,
  clampRotateDays,
  mergePlanData,
  planAllDayKeys,
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
  it('全局模式与周计划把 ALL 放在最前', () => {
    expect(planColumnKeys('Weekly', 7)[0]).toBe('ALL')
    expect(planColumnKeys('ALL', 7)[0]).toBe('ALL')
  })

  it('多天轮换没有「每天」这一格，只给天键', () => {
    expect(planColumnKeys('Rotate', 2)).toEqual(['1', '2'])
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
    Monday: { Key: { Wanted: [2, -1, 3] } },
  }

  it('直接读取对应配置分组', () => {
    expect(readPlanColumn(tableData, 'ALL')).toEqual({ Key: { Wanted: [1, -1, 1] } })
    expect(readPlanColumn(tableData, 'Monday')).toEqual({ Key: { Wanted: [2, -1, 3] } })
    expect(readPlanColumn(tableData, 'Tuesday')).toBeUndefined()
    expect(readPlanColumn(null, 'ALL')).toBeUndefined()
  })

  it('写路径指向配置分组字段', () => {
    expect(planColumnPath('ALL', 'Key')).toBe('ALL.Key')
    expect(planColumnPath('Monday', 'Stage')).toBe('Monday.Stage')
  })
})

describe('planAllDayKeys 与 mergePlanData', () => {
  const full = {
    ALL: { Stage: '1-7' },
    Monday: { Stage: '1-7' },
    Day1: { Stage: 'CE-5' },
  }

  it('全部天键来自星期及轮换配置分组', () => {
    // 分组顺序保持后端配置声明的顺序。
    expect(planAllDayKeys(full)).toEqual(['ALL', 'Monday', '1'])
    expect(planAllDayKeys(null)).toEqual(['ALL'])
  })

  it('合并以 override 为准，其余槽位用 base 补齐', () => {
    const merged = mergePlanData(full, { Day2: { Stage: 'CE-6' } })
    expect(merged.ALL).toEqual({ Stage: '1-7' })
    expect(merged.Monday).toEqual({ Stage: '1-7' })
    expect(merged.Day1).toEqual({ Stage: 'CE-5' })
    expect(merged.Day2).toEqual({ Stage: 'CE-6' })
  })

  it('override 没给 ALL 时沿用 base 的', () => {
    expect(mergePlanData(full, {}).ALL).toEqual({ Stage: '1-7' })
    expect(mergePlanData(full, { ALL: { Stage: 'X' } }).ALL).toEqual({ Stage: 'X' })
  })
})
