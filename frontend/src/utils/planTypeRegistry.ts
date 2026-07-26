/**
 * Lane 8：计划类型注册中心。
 *
 * 目的：
 * - 将 plan/index.vue 中内联的 planType -> table 映射提取为可独立测试的纯函数。
 * - 显式登记所有受支持的计划类型，避免新增类型时静默丢失。
 * - 未注册类型必须明确报告为不受支持，不能套用另一种计划表编辑。
 *
 * 设计：
 * - registry 不依赖 Vue 组件实例，只保存 component key（字符串）。
 * - plan/index.vue 通过 resolvePlanTableComponent() 获取 key 后再映射到实际组件。
 * - 这使得注册逻辑可在 vitest 中无 Vue 环境运行。
 */

export type PlanTypeKey = string

export type PlanTableComponentKey = 'MaaPlanTable' | 'UnknownPlanTable'

export type PlanMode = 'ALL' | 'Weekly'

export interface PlanTypeRegistration {
  /** 计划类型标识，对应后端 PlanCreateIn.type */
  type: PlanTypeKey
  /** 显示名称（中文） */
  label: string
  /** 默认基础名称（用于 generateUniquePlanName） */
  defaultName: string
  /** 对应的表格组件 key */
  tableComponent: PlanTableComponentKey
  /** 支持的模式 */
  supportedModes: PlanMode[]
  /** 是否为默认类型 */
  isDefault?: boolean
}

/**
 * Lane 8：已知计划类型注册表。
 *
 * 当前 AUTO-MAS 后端只暴露 MaaPlanConfig（createPlan 内部会转为 MaaPlan）。
 *
 * 新增类型时：
 * 1. 在此添加 registration。
 * 2. 在 plan/tables/ 下新增对应表格组件。
 * 3. 在 plan/index.vue 中加入对应的真实组件映射。
 */
const REGISTRY: Record<PlanTypeKey, PlanTypeRegistration> = {
  MaaPlanConfig: {
    type: 'MaaPlanConfig',
    label: 'MAA计划表',
    defaultName: '新 MAA 计划表',
    tableComponent: 'MaaPlanTable',
    supportedModes: ['ALL', 'Weekly'],
    isDefault: true,
  },
}

/** 默认计划类型 */
export const DEFAULT_PLAN_TYPE: PlanTypeKey = 'MaaPlanConfig'

/** 默认表格组件 key，仅用于缺少类型信息时的当前后端兼容。 */
export const DEFAULT_TABLE_COMPONENT: PlanTableComponentKey = 'MaaPlanTable'

/**
 * 获取计划类型的注册信息。
 *
 * 未注册的类型返回 null。
 */
export function getPlanTypeRegistration(type: PlanTypeKey): PlanTypeRegistration | null {
  return REGISTRY[type] ?? null
}

/**
 * 解析计划类型对应的表格组件 key。
 *
 * - 已注册类型返回其 tableComponent。
 * - 缺少类型信息时兼容当前单一后端类型。
 * - 显式未知类型返回 UnknownPlanTable，调用方必须阻止编辑。
 *
 * Lane 8 验收：所有现有计划类型继续显示。
 */
export function resolvePlanTableComponent(
  type: PlanTypeKey | undefined | null
): PlanTableComponentKey {
  if (!type) return DEFAULT_TABLE_COMPONENT
  const reg = REGISTRY[type]
  return reg?.tableComponent ?? 'UnknownPlanTable'
}

/**
 * 获取计划类型的显示标签。
 */
export function getRegisteredPlanTypeLabel(type: PlanTypeKey): string {
  return REGISTRY[type]?.label ?? '计划表'
}

/**
 * 获取计划类型的默认名称（用于新建计划时）。
 */
export function getRegisteredDefaultName(type: PlanTypeKey): string {
  return REGISTRY[type]?.defaultName ?? '新计划表'
}

/**
 * 判断计划类型是否支持指定模式。
 */
export function isModeSupported(type: PlanTypeKey, mode: PlanMode): boolean {
  const reg = REGISTRY[type]
  if (!reg) return false
  return reg.supportedModes.includes(mode)
}

/**
 * 列出所有已注册的计划类型。
 */
export function listRegisteredPlanTypes(): PlanTypeRegistration[] {
  return Object.values(REGISTRY)
}

/**
 * 校验：确保默认类型确实存在于注册表中。
 *
 * Lane 8 要求：所有现有计划类型继续显示。
 * 此函数用于启动时自检，若默认类型未注册则说明注册表配置错误。
 */
export function validateRegistryIntegrity(): { valid: boolean; missing: PlanTypeKey[] } {
  const missing: PlanTypeKey[] = []
  if (!REGISTRY[DEFAULT_PLAN_TYPE]) {
    missing.push(DEFAULT_PLAN_TYPE)
  }
  return { valid: missing.length === 0, missing }
}

/**
 * Lane 8：对后端返回的 plan index 列表做兼容性检查。
 *
 * - 已注册类型标记为 known。
 * - 未注册类型标记为 unknown，但仍返回（降级显示），不丢弃。
 *
 * 返回每个 planId 的类型兼容性信息，供 plan/index.vue 在 UI 上提示用户。
 */
export function checkPlanTypeCompatibility(
  planIndex: Array<{ uid: string; type: string }>
): Array<{ uid: string; type: string; known: boolean; tableComponent: PlanTableComponentKey }> {
  return planIndex.map(item => {
    const reg = getPlanTypeRegistration(item.type)
    return {
      uid: item.uid,
      type: item.type,
      known: reg !== null,
      tableComponent: resolvePlanTableComponent(item.type),
    }
  })
}
