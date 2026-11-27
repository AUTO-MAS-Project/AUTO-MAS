import { describe, expect, it } from 'vite-plus/test'
import { getAvailablePlanTypes, PLAN_CONFIG_TYPES } from './planTypeRegistry'

describe('新建计划表菜单', () => {
  it('只显示已启用专项的计划表，保留内置类型', () => {
    const types = (enabled: string[]) => getAvailablePlanTypes(enabled).map(plan => plan.configType)
    expect(types(['MAA'])).toContain(PLAN_CONFIG_TYPES.MAA)
    expect(types(['MAA'])).not.toContain(PLAN_CONFIG_TYPES.MSS)
    expect(types(['MSS'])).toContain(PLAN_CONFIG_TYPES.MSS)
    expect(types(['MSS'])).not.toContain(PLAN_CONFIG_TYPES.MAA)
    expect(types([])).toContain(PLAN_CONFIG_TYPES.UNIVERSAL)
  })
})
