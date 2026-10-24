import { defineAsyncComponent, type Component } from 'vue'
import { PlanCreateIn } from '@/api/models/PlanCreateIn'
import { PlanIndexItem } from '@/api/models/PlanIndexItem'
import type { PlanGetOut } from '@/api'

// ==================== 类型定义 ====================

export type PlanConfigType = PlanIndexItem.type
type PlanCreateType = PlanCreateIn.type
export type PlanConfigData = PlanGetOut['data'][string]

export const PLAN_CONFIG_TYPES = {
  MAA: PlanIndexItem.type.MAA_PLAN_CONFIG,
  MAA_END: PlanIndexItem.type.MAA_END_PLAN_CONFIG,
  BAAH: PlanIndexItem.type.BAAHPLAN_CONFIG,
  MSS: PlanIndexItem.type.MSSPLAN_CONFIG,
} as const

export interface PlanChangeOptions {
  refresh?: boolean
  forceCustomStages?: boolean
  /** 弹出编辑保留草稿时，展示服务端提供的保存失败原因。 */
  onError?: (_reason: string) => void
}

export type PlanChangeHandler = (
  _path: string,
  _value: unknown,
  _reloadOrOptions?: boolean | PlanChangeOptions
) => Promise<boolean>

interface PlanTypeDescriptor {
  configType: PlanConfigType
  createType: PlanCreateType
  displayNameKey: string
  /** 默认计划名的词表 key：默认名会被写进计划名，必须跟随界面语言 */
  defaultNameKey: string
  /** 历史版本写进数据的默认名（中文），加载时用它识别「还是默认名」 */
  legacyDefaultName: string
  selectorTag: string
  reloadAfterSave: boolean
  /** 是否提供「简化视图」；没提供的类型隐藏视图切换，避免留下点了没反应的控件 */
  supportsSimpleView: boolean
  tableComponent: Component
}

// ==================== 注册表 ====================

export const PLAN_TYPE_REGISTRY: Record<PlanConfigType, PlanTypeDescriptor> = {
  [PLAN_CONFIG_TYPES.MAA]: {
    configType: PLAN_CONFIG_TYPES.MAA,
    createType: PlanCreateIn.type.MAA_PLAN,
    displayNameKey: 'plan.type.maa',
    defaultNameKey: 'plan.defaultName.maa',
    legacyDefaultName: '新 MAA 计划表',
    selectorTag: 'MAA',
    reloadAfterSave: true,
    supportsSimpleView: true,
    tableComponent: defineAsyncComponent(() => import('@/views/plan/tables/MaaPlanTable.vue')),
  },
  [PLAN_CONFIG_TYPES.MAA_END]: {
    configType: PLAN_CONFIG_TYPES.MAA_END,
    createType: PlanCreateIn.type.MAA_END_PLAN,
    displayNameKey: 'plan.type.maaEnd',
    defaultNameKey: 'plan.defaultName.maaEnd',
    legacyDefaultName: '新 MaaEnd 计划表',
    selectorTag: 'MaaEnd',
    reloadAfterSave: false,
    supportsSimpleView: true,
    tableComponent: defineAsyncComponent(() => import('@/views/plan/tables/MaaEndPlanTable.vue')),
  },
  [PLAN_CONFIG_TYPES.BAAH]: {
    configType: PLAN_CONFIG_TYPES.BAAH,
    createType: PlanCreateIn.type.BAAHPLAN,
    displayNameKey: 'plan.type.baah',
    defaultNameKey: 'plan.defaultName.baah',
    legacyDefaultName: '新 BAAH 计划表',
    selectorTag: 'BAAH',
    reloadAfterSave: false,
    // BAAH 两种排法都是一格一个控件，但要按行说明每一位是什么，转置成简化视图只会更难读
    supportsSimpleView: false,
    tableComponent: defineAsyncComponent(() => import('@/views/plan/tables/BAAHPlanTable.vue')),
  },
  [PLAN_CONFIG_TYPES.MSS]: {
    configType: PLAN_CONFIG_TYPES.MSS,
    createType: PlanCreateIn.type.MSSPLAN,
    displayNameKey: 'plan.type.mss',
    defaultNameKey: 'plan.defaultName.mss',
    legacyDefaultName: '新 MSS 计划表',
    selectorTag: 'MSS',
    reloadAfterSave: false,
    supportsSimpleView: true,
    tableComponent: defineAsyncComponent(() => import('@/views/plan/tables/MSSPlanTable.vue')),
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
