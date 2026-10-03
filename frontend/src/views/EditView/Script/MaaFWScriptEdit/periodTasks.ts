import type { MaaFWTaskInfo } from '@/types/script'

// MaaFW pretask 伪任务：预览接口会把它们混进 tasks[]（entry 固定为 MXU_PRETASK、
// name 带 __MXU_PRETASK__ 前缀），周期跳过下拉不能让用户选到。按 entry 过滤、name 前缀兜底。
const PRETASK_TASK_ENTRY = 'MXU_PRETASK'
const PRETASK_TASK_PREFIX = '__MXU_PRETASK__'
export const isPretaskTask = (task: MaaFWTaskInfo): boolean =>
  task.entry === PRETASK_TASK_ENTRY || task.name.startsWith(PRETASK_TASK_PREFIX)

export const PERIOD_KEYS = ['DailyOnceTasks', 'WeeklyOnceTasks', 'MonthlyOnceTasks'] as const
export type PeriodKey = (typeof PERIOD_KEYS)[number]

/** 周期跳过下拉的选项：去掉 pretask 伪任务，有 label 时带上任务名 */
export const buildPeriodTaskOptions = (tasks: MaaFWTaskInfo[]) =>
  tasks
    .filter(task => !isPretaskTask(task))
    .map(task => ({
      label: task.label ? `${task.label}（${task.name}）` : task.name,
      value: task.name,
    }))

// ConfigBase 把周期任务列表以 JSON 字符串保存、读回也是字符串；
// 兼容后端某天直接返回数组的情况，统一收敛成字符串数组。
export const parseTaskNameList = (value: unknown): string[] => {
  if (Array.isArray(value)) return value.filter((item): item is string => typeof item === 'string')
  if (typeof value === 'string' && value.trim()) {
    try {
      const parsed = JSON.parse(value)
      return Array.isArray(parsed)
        ? parsed.filter((item): item is string => typeof item === 'string')
        : []
    } catch {
      return []
    }
  }
  return []
}

export const stringifyTaskNameList = (value: string[]): string => JSON.stringify(value)

/** 按任务名覆盖的单任务时限：分钟数，0 表示该任务不限。 */
export interface TaskLimitOverrideRow {
  name: string
  minutes: number
}

export const normalizeTaskLimitMinutes = (value: unknown): number => {
  const minutes = Math.trunc(Number(value))
  return Number.isFinite(minutes) && minutes > 0 ? minutes : 0
}

// 覆盖表同样以 JSON 字符串保存（任务名 → 分钟），值 0 表示该任务不限；
// 兼容后端某天直接返回对象、以及分钟被存成字符串的情况。
export const parseTaskLimitOverrides = (value: unknown): TaskLimitOverrideRow[] => {
  let source: unknown = value
  if (typeof source === 'string') {
    if (!source.trim()) return []
    try {
      source = JSON.parse(source)
    } catch {
      return []
    }
  }
  if (!source || typeof source !== 'object' || Array.isArray(source)) return []
  return Object.entries(source as Record<string, unknown>)
    .filter(([name]) => Boolean(name))
    .map(([name, minutes]) => ({ name, minutes: normalizeTaskLimitMinutes(minutes) }))
}

export const stringifyTaskLimitOverrides = (rows: TaskLimitOverrideRow[]): string =>
  JSON.stringify(
    Object.fromEntries(
      rows
        .filter(row => Boolean(row.name))
        .map(row => [row.name, normalizeTaskLimitMinutes(row.minutes)] as const)
    )
  )
