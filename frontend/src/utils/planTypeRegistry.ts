import { defineAsyncComponent, type Component } from 'vue'
import { PlanCreateIn } from '@/api/models/PlanCreateIn'
import { PlanIndexItem } from '@/api/models/PlanIndexItem'
import type { PlanGetOut } from '@/api'

// ==================== 类型定义 ====================

export type PlanConfigType = PlanIndexItem.type
export type PlanCreateType = PlanCreateIn.type
export type PlanConfigData = PlanGetOut['data'][string]

export const PLAN_CONFIG_TYPES = {
  MAA: PlanIndexItem.type.MAA_PLAN_CONFIG,
  MAA_END: PlanIndexItem.type.MAA_END_PLAN_CONFIG,
} as const

export interface PlanChangeOptions {
  refresh?: boolean
  forceCustomStages?: boolean
}

/* eslint-disable no-unused-vars */
export type PlanChangeHandler = (
  _path: string,
  _value: any,
  _reloadOrOptions?: boolean | PlanChangeOptions
) => Promise<boolean>
/* eslint-enable no-unused-vars */

export interface PlanTypeDescriptor {
  configType: PlanConfigType
  createType: PlanCreateType
  displayName: string
  defaultName: string
  selectorTag: string
  reloadAfterSave: boolean
  tableComponent: Component
}

// ==================== 注册表 ====================

export const PLAN_TYPE_REGISTRY: Record<PlanConfigType, PlanTypeDescriptor> = {
  [PLAN_CONFIG_TYPES.MAA]: {
    configType: PLAN_CONFIG_TYPES.MAA,
    createType: PlanCreateIn.type.MAA_PLAN,
    displayName: 'MAA 计划表',
    defaultName: '新 MAA 计划表',
    selectorTag: 'MAA',
    reloadAfterSave: true,
    tableComponent: defineAsyncComponent(() => import('@/views/plan/tables/MaaPlanTable.vue')),
  },
  [PLAN_CONFIG_TYPES.MAA_END]: {
    configType: PLAN_CONFIG_TYPES.MAA_END,
    createType: PlanCreateIn.type.MAA_END_PLAN,
    displayName: 'MaaEnd 计划表',
    defaultName: '新 MaaEnd 计划表',
    selectorTag: 'MaaEnd',
    reloadAfterSave: false,
    tableComponent: defineAsyncComponent(() => import('@/views/plan/tables/MaaEndPlanTable.vue')),
  },
}

export const DEFAULT_PLAN_CONFIG_TYPE: PlanConfigType = PLAN_CONFIG_TYPES.MAA
export const PLAN_TYPE_DESCRIPTORS = Object.values(PLAN_TYPE_REGISTRY)

// ==================== 查询方法 ====================

export const isKnownPlanType = (planType: string): planType is PlanConfigType =>
  Object.prototype.hasOwnProperty.call(PLAN_TYPE_REGISTRY, planType)

export const getPlanTypeDescriptor = (planType?: string | null): PlanTypeDescriptor | null => {
  if (!planType || !isKnownPlanType(planType)) {
    return null
  }

  return PLAN_TYPE_REGISTRY[planType]
}

export const getPlanCreateType = (planType: string): PlanCreateType | null =>
  getPlanTypeDescriptor(planType)?.createType ?? null
