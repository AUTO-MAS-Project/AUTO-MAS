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
