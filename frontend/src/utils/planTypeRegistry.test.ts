/**
 * Lane 8：计划类型注册中心测试。
 *
 * 覆盖：
 * - 当前后端真实已注册类型（MaaPlanConfig）的元数据完整性
 * - resolvePlanTableComponent 对已注册和未注册类型的解析
 * - 显式未知类型必须拒绝套用 MaaPlanTable
 * - validateRegistryIntegrity 自检
 * - checkPlanTypeCompatibility 对后端返回的兼容性检查
 * - isModeSupported 模式支持判断
 *
 * Lane 8 验收重点：所有现有计划类型继续显示。
 */
import { describe, expect, it } from 'vitest'
import {
  DEFAULT_PLAN_TYPE,
  DEFAULT_TABLE_COMPONENT,
  checkPlanTypeCompatibility,
  getPlanTypeRegistration,
  getRegisteredDefaultName,
  getRegisteredPlanTypeLabel,
  isModeSupported,
  listRegisteredPlanTypes,
  resolvePlanTableComponent,
  validateRegistryIntegrity,
} from './planTypeRegistry'

describe('planTypeRegistry', () => {
  describe('registered plan types', () => {
    it('MaaPlanConfig is registered as default type', () => {
      const reg = getPlanTypeRegistration('MaaPlanConfig')
      expect(reg).not.toBeNull()
      expect(reg?.label).toBe('MAA计划表')
      expect(reg?.tableComponent).toBe('MaaPlanTable')
      expect(reg?.isDefault).toBe(true)
      expect(reg?.supportedModes).toEqual(['ALL', 'Weekly'])
    })

    it('does not register placeholder types without a backend path', () => {
      expect(getPlanTypeRegistration('GeneralPlan')).toBeNull()
      expect(getPlanTypeRegistration('CustomPlan')).toBeNull()
    })

    it('listRegisteredPlanTypes returns all registered types', () => {
      const all = listRegisteredPlanTypes()
      const types = all.map(r => r.type)
      expect(types).toEqual(['MaaPlanConfig'])
    })

    it('exactly one type is marked as default', () => {
      const all = listRegisteredPlanTypes()
      const defaults = all.filter(r => r.isDefault)
      expect(defaults).toHaveLength(1)
      expect(defaults[0].type).toBe(DEFAULT_PLAN_TYPE)
    })
  })

  describe('resolvePlanTableComponent', () => {
    it('returns MaaPlanTable for MaaPlanConfig', () => {
      expect(resolvePlanTableComponent('MaaPlanConfig')).toBe('MaaPlanTable')
    })

    it('returns an unsupported marker for an explicit unknown type', () => {
      expect(resolvePlanTableComponent('SomeUnknownType')).toBe('UnknownPlanTable')
    })

    it('falls back to default table for undefined type', () => {
      expect(resolvePlanTableComponent(undefined)).toBe(DEFAULT_TABLE_COMPONENT)
    })

    it('falls back to default table for null type', () => {
      expect(resolvePlanTableComponent(null)).toBe(DEFAULT_TABLE_COMPONENT)
    })

    it('falls back to default table for empty string', () => {
      expect(resolvePlanTableComponent('')).toBe(DEFAULT_TABLE_COMPONENT)
    })

    it('default table component is MaaPlanTable', () => {
      expect(DEFAULT_TABLE_COMPONENT).toBe('MaaPlanTable')
    })
  })

  describe('getRegisteredPlanTypeLabel', () => {
    it('returns label for registered type', () => {
      expect(getRegisteredPlanTypeLabel('MaaPlanConfig')).toBe('MAA计划表')
    })

    it('returns generic label for unregistered type', () => {
      expect(getRegisteredPlanTypeLabel('UnknownType')).toBe('计划表')
    })
  })

  describe('getRegisteredDefaultName', () => {
    it('returns default name for registered type', () => {
      expect(getRegisteredDefaultName('MaaPlanConfig')).toBe('新 MAA 计划表')
    })

    it('returns generic name for unregistered type', () => {
      expect(getRegisteredDefaultName('UnknownType')).toBe('新计划表')
    })
  })

  describe('isModeSupported', () => {
    it('MaaPlanConfig supports ALL and Weekly', () => {
      expect(isModeSupported('MaaPlanConfig', 'ALL')).toBe(true)
      expect(isModeSupported('MaaPlanConfig', 'Weekly')).toBe(true)
    })

    it('rejects modes for an unknown type', () => {
      expect(isModeSupported('UnknownType', 'ALL')).toBe(false)
      expect(isModeSupported('UnknownType', 'Weekly')).toBe(false)
    })
  })

  describe('validateRegistryIntegrity', () => {
    it('returns valid when default type is registered', () => {
      const result = validateRegistryIntegrity()
      expect(result.valid).toBe(true)
      expect(result.missing).toEqual([])
    })

    it('default plan type is MaaPlanConfig', () => {
      expect(DEFAULT_PLAN_TYPE).toBe('MaaPlanConfig')
    })
  })

  describe('checkPlanTypeCompatibility', () => {
    it('marks registered types as known', () => {
      const result = checkPlanTypeCompatibility([{ uid: 'plan-1', type: 'MaaPlanConfig' }])
      expect(result[0].known).toBe(true)
    })

    it('marks unregistered types as unknown but still returns them', () => {
      const result = checkPlanTypeCompatibility([{ uid: 'plan-1', type: 'SomeNewType' }])
      expect(result).toHaveLength(1)
      expect(result[0].known).toBe(false)
      // 未注册类型仍保留原始 type，不丢弃
      expect(result[0].type).toBe('SomeNewType')
    })

    it('assigns an unsupported marker to unknown types', () => {
      const result = checkPlanTypeCompatibility([{ uid: 'plan-1', type: 'UnknownType' }])
      expect(result[0].tableComponent).toBe('UnknownPlanTable')
    })

    it('assigns specific table component to known types', () => {
      const result = checkPlanTypeCompatibility([{ uid: 'plan-1', type: 'MaaPlanConfig' }])
      expect(result[0].tableComponent).toBe('MaaPlanTable')
    })

    it('handles empty plan index', () => {
      expect(checkPlanTypeCompatibility([])).toEqual([])
    })

    it('preserves uid for each plan', () => {
      const result = checkPlanTypeCompatibility([
        { uid: 'plan-1', type: 'MaaPlanConfig' },
        { uid: 'plan-2', type: 'UnknownType' },
      ])
      expect(result[0].uid).toBe('plan-1')
      expect(result[1].uid).toBe('plan-2')
    })

    it('mixed known and unknown types in one call', () => {
      const result = checkPlanTypeCompatibility([
        { uid: 'plan-1', type: 'MaaPlanConfig' },
        { uid: 'plan-2', type: 'FutureType' },
      ])
      expect(result[0].known).toBe(true)
      expect(result[1].known).toBe(false)
    })
  })
})
