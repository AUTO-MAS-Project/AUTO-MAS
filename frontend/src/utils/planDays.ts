// 计划表「按天」的公共约定：周计划是周一~周日，多天轮换是第 1~N 天。两者在接口里都是
// 配置分组名：星期名保持原样，轮换天为 Day1~Day31，与后端 config/plan.py 一致。

export type PlanMode = 'ALL' | 'Weekly' | 'Rotate'

export const PLAN_WEEKDAY_KEYS = [
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
  'Saturday',
  'Sunday',
] as const

export const PLAN_ROTATE_DAYS_DEFAULT = 7
export const PLAN_ROTATE_DAYS_MIN = 1
export const PLAN_ROTATE_DAYS_MAX = 31

const isWeekdayKey = (day: string): boolean =>
  (PLAN_WEEKDAY_KEYS as readonly string[]).includes(day)

/** 轮换天数夹到合法区间，读不出数字就用默认值 */
export const clampRotateDays = (raw: unknown): number => {
  const parsed = typeof raw === 'string' ? Number(raw) : raw
  if (typeof parsed !== 'number' || !Number.isInteger(parsed)) return PLAN_ROTATE_DAYS_DEFAULT
  return Math.min(Math.max(parsed, PLAN_ROTATE_DAYS_MIN), PLAN_ROTATE_DAYS_MAX)
}

/** 该用哪些天键：周计划七天，多天轮换是 "1"~"N" */
export const planDayKeys = (mode: string | undefined, rotateDays: unknown): string[] => {
  if (mode !== 'Rotate') return [...PLAN_WEEKDAY_KEYS]
  return Array.from({ length: clampRotateDays(rotateDays) }, (_, index) => String(index + 1))
}

/** 天键的词表 key 与插值参数：星期名走 plan.week.*，轮换天走 plan.rotateDay（带 {n}） */
export const planDayLabel = (day: string): { key: string; params: Record<string, unknown> } =>
  isWeekdayKey(day)
    ? { key: `core.plan.week.${day}`, params: {} }
    : { key: 'core.plan.rotateDay', params: { n: day } }

/**
 * 列的键：全局模式与周计划是 ALL 加当天的天键；多天轮换是一次接一次的循环，
 * 没有「每天」那一格的用武之地，只给天键。
 */
export const planColumnKeys = (mode: string | undefined, rotateDays: unknown): string[] => {
  const days = planDayKeys(mode, rotateDays)
  return mode === 'Rotate' ? days : ['ALL', ...days]
}

/** 计划列对应的配置分组。 */
export const planColumnGroup = (key: string): string =>
  key === 'ALL' || isWeekdayKey(key) ? key : `Day${key}`

/** 直接读取派生契约中的配置分组。 */
export const readPlanColumn = (tableData: Record<string, any> | null, key: string): unknown =>
  tableData?.[planColumnGroup(key)]

/** 写某一列的配置字段路径。 */
export const planColumnPath = (key: string, field: string): string =>
  `${planColumnGroup(key)}.${field}`

/** 全部已声明的计划列，包括当前未显示的轮换天。 */
export const planAllDayKeys = (planData: Record<string, any> | null | undefined): string[] => [
  'ALL',
  ...Object.keys(planData ?? {}).flatMap(group =>
    isWeekdayKey(group) ? [group] : /^Day\d+$/.test(group) ? [group.slice(3)] : []
  ),
]

/**
 * 合并两份计划数据：以 override 为准，其余槽位用 base 补齐。
 *
 * 协调器只持有当前显示的那几天，改名之类要覆盖所有引用的操作得拿后端返回的完整配置打底，
 * 否则切回另一种模式时那些槽位还留着旧值。
 */
export const mergePlanData = (
  base: Record<string, any> | null | undefined,
  override: Record<string, any>
): Record<string, any> => ({
  ...(base ?? {}),
  ...override,
  ALL: override.ALL ?? base?.ALL,
})
