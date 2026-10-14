import { defineAsyncComponent, type Component } from 'vue'

// ==================== 类型定义 ====================

export type PlanConfigType = string
type PlanCreateType = string
/** API plan rows are plugin-defined, so their concrete shape is resolved at runtime. */
export interface PlanConfigData extends Record<string, unknown> {
  Info?: { Name?: string; Mode?: 'ALL' | 'Weekly'; [key: string]: unknown }
}

export const PLAN_CONFIG_TYPES = {
  MAA: 'MaaPlan',
  MAA_END: 'MaaEndPlan',
  BAAH: 'BAAHPlan',
  MSS: 'MSSPlan',
} as const

export interface PlanChangeOptions {
  refresh?: boolean
  forceCustomStages?: boolean
}

export type PlanChangeHandler = (
  _path: string,
  _value: unknown,
  _reloadOrOptions?: boolean | PlanChangeOptions
) => Promise<boolean>

interface PlanTypeDescriptor {
  configType: PlanConfigType
  createType: PlanCreateType
  /** 词表 key；defaultName 刻意不走词表，见下方注释 */
  displayNameKey: string
  defaultName: string
  selectorTag: string
  reloadAfterSave: boolean
  /** 是否提供「简化视图」；没提供的类型隐藏视图切换，避免留下点了没反应的控件 */
  supportsSimpleView: boolean
  /** 是否提供「关卡安排」（多类混打 / 每天一类）；只有 BAAH 的 key 分这两种排法 */
  supportsLayoutMode: boolean
  tableComponent: Component
}

// ==================== 注册表 ====================

export const PLAN_TYPE_REGISTRY: Record<PlanConfigType, PlanTypeDescriptor> = {
  [PLAN_CONFIG_TYPES.MAA]: {
    configType: PLAN_CONFIG_TYPES.MAA,
    createType: 'MaaScript',
    displayNameKey: 'plan.type.maa',
    // defaultName 会被写进计划名，并被 plan/index.vue 拿来判断“还是默认名”，保持中文
    defaultName: '新 MAA 计划表',
    selectorTag: 'MAA',
    reloadAfterSave: true,
    supportsSimpleView: true,
    supportsLayoutMode: false,
    tableComponent: defineAsyncComponent(() => import('@/views/plan/tables/MaaPlanTable.vue')),
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
