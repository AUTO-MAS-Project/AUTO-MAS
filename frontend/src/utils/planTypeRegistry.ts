import { defineAsyncComponent, type Component } from 'vue'
import { SCRIPT_PLUGIN_BINDINGS } from '@/plugins/scriptAdapters'
import { PlanCreateIn } from '@/api/models/PlanCreateIn'
import { PlanIndexItem } from '@/api/models/PlanIndexItem'
import type { PlanGetOut } from '@/api'
import { translate as t } from '@/i18n'
import type { PluginScriptTypes } from './pluginScriptTypes'

// ==================== 类型定义 ====================

export type PlanConfigType = PlanIndexItem.type
type PlanCreateType = PlanCreateIn.type
export type PlanConfigData = PlanGetOut['data'][string]

export const PLAN_CONFIG_TYPES = {
  OKWW: PlanIndexItem.type.OKWW_PLAN_CONFIG,
  OKNTE: PlanIndexItem.type.OK_NTE_PLAN_CONFIG,
  UNIVERSAL: PlanIndexItem.type.UNIVERSAL_PLAN_CONFIG,
  MAA: PlanIndexItem.type.MAA_PLAN_CONFIG,
  MAA_END: PlanIndexItem.type.MAA_END_PLAN_CONFIG,
  MSS: PlanIndexItem.type.MSSPLAN_CONFIG,
} as const

export interface PlanChangeOptions {
  /** 批量编辑由外层汇总一次，内部逐日写入不重复计数。 */
  analyticsBatch?: boolean
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
  /** 词表 key；defaultName 刻意不走词表，见下方注释 */
  displayNameKey: string
  defaultName: string
  selectorTag: string
  reloadAfterSave: boolean
  /** 是否提供「简化视图」；没提供的类型隐藏视图切换，避免留下点了没反应的控件 */
  supportsSimpleView: boolean
  tableComponent: Component
}

// ==================== 注册表 ====================

export const PLAN_TYPE_REGISTRY: Record<string, PlanTypeDescriptor> = {
  [PLAN_CONFIG_TYPES.OKWW]: {
    configType: PLAN_CONFIG_TYPES.OKWW,
    createType: PlanCreateIn.type.OKWW_PLAN,
    displayNameKey: 'core.plan.type.okww',
    defaultName: '新 Okww 计划表',
    selectorTag: 'Okww',
    reloadAfterSave: false,
    supportsSimpleView: false,
    tableComponent: defineAsyncComponent(() => import('@/views/plan/tables/OkwwPlanTable.vue')),
  },
  [PLAN_CONFIG_TYPES.OKNTE]: {
    configType: PLAN_CONFIG_TYPES.OKNTE,
    createType: PlanCreateIn.type.OK_NTE_PLAN,
    displayNameKey: 'core.plan.type.oknte',
    defaultName: '新 OkNte 计划表',
    selectorTag: 'OkNte',
    reloadAfterSave: false,
    supportsSimpleView: false,
    tableComponent: defineAsyncComponent(() => import('@/views/plan/tables/OkNtePlanTable.vue')),
  },
  [PLAN_CONFIG_TYPES.UNIVERSAL]: {
    configType: PLAN_CONFIG_TYPES.UNIVERSAL,
    createType: PlanCreateIn.type.UNIVERSAL_PLAN,
    displayNameKey: 'core.plan.type.universal',
    defaultName: '新通用脚本计划表',
    selectorTag: '通用',
    reloadAfterSave: false,
    supportsSimpleView: false,
    tableComponent: defineAsyncComponent(
      () => import('@/views/plan/tables/UniversalPlanTable.vue')
    ),
  },
}

// ==================== 查询方法 ====================

export const isKnownPlanType = (planType: string): planType is PlanConfigType =>
  Object.prototype.hasOwnProperty.call(PLAN_TYPE_REGISTRY, planType)

export const getPlanTypeDescriptor = (planType?: string | null): PlanTypeDescriptor | null => {
  if (!planType || !isKnownPlanType(planType)) {
    return null
  }

  return PLAN_TYPE_REGISTRY[planType]
}

export function getPlanTypeOption(configType: string, plugins: PluginScriptTypes) {
  const stored = getPlanTypeDescriptor(configType)
  if (stored) {
    return {
      configType,
      createType: stored.createType,
      displayName: t(stored.displayNameKey),
      selectorTag: stored.selectorTag,
      defaultName: stored.defaultName,
    }
  }
  const plugin = plugins.byPlanConfigType.get(configType)
  if (plugin) {
    const name = plugin.displayName
    return {
      configType,
      createType: configType,
      displayName: name,
      selectorTag: name,
      defaultName: name,
    }
  }
}

export type PlanTypeOption = NonNullable<ReturnType<typeof getPlanTypeOption>>

export function getAvailablePlanTypes(scriptTypes: readonly string[], plugins: PluginScriptTypes) {
  const types = new Set([...Object.keys(PLAN_TYPE_REGISTRY), ...plugins.byPlanConfigType.keys()])
  const available: PlanTypeOption[] = []
  for (const type of types) {
    const owner =
      plugins.byPlanConfigType.get(type)?.scriptKey ??
      SCRIPT_PLUGIN_BINDINGS.find(binding => binding.planConfigType === type)?.scriptType
    if (!owner || scriptTypes.includes(owner)) available.push(getPlanTypeOption(type, plugins)!)
  }
  return available
}
