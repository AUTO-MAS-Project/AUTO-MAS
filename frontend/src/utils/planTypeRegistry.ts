import { defineAsyncComponent, type Component } from 'vue'

// ==================== 类型定义 ====================

export type PlanConfigType = 'MaaPlanConfig' | 'MaaEndPlanConfig'
export type PlanCreateType = 'MaaPlan' | 'MaaEndPlan'

export interface PlanTypeDescriptor {
  configType: PlanConfigType
  createType: PlanCreateType
  displayName: string
  defaultName: string
  selectorTag: string
  tableComponent: Component
}

// ==================== 注册表 ====================

export const PLAN_TYPE_REGISTRY: Record<PlanConfigType, PlanTypeDescriptor> = {
  MaaPlanConfig: {
    configType: 'MaaPlanConfig',
    createType: 'MaaPlan',
    displayName: 'MAA 计划表',
    defaultName: '新 MAA 计划表',
    selectorTag: 'MAA',
    tableComponent: defineAsyncComponent(() => import('@/views/plan/tables/MaaPlanTable.vue')),
  },
  MaaEndPlanConfig: {
    configType: 'MaaEndPlanConfig',
    createType: 'MaaEndPlan',
    displayName: 'MaaEnd 计划表',
    defaultName: '新 MaaEnd 计划表',
    selectorTag: 'MaaEnd',
    tableComponent: defineAsyncComponent(() => import('@/views/plan/tables/MaaEndPlanTable.vue')),
  },
}

export const DEFAULT_PLAN_CONFIG_TYPE: PlanConfigType = 'MaaPlanConfig'
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
