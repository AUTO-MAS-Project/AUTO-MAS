import { computed, ref, type Ref } from 'vue'
import type { MaaFWInterfacePreviewData, MaaFWScriptConfig } from '@/types/script'
import {
  PERIOD_KEYS,
  buildPeriodTaskOptions,
  normalizeTaskLimitMinutes,
  parseTaskLimitOverrides,
  parseTaskNameList,
  stringifyTaskLimitOverrides,
  stringifyTaskNameList,
  type PeriodKey,
  type TaskLimitOverrideRow,
} from './periodTasks'
import type { MaaFWScriptChangeHandler } from './useMaaFWScriptDraft'

/** Run 分组里需要本地状态的项：每日 / 每周 / 每月只跑一次的任务选择、按任务覆盖的单任务时限。 */
export function useMaaFWPeriodTasks(
  maafwConfig: MaaFWScriptConfig,
  previewData: Ref<MaaFWInterfacePreviewData | null>,
  handleChange: MaaFWScriptChangeHandler
) {
  const dailyOnceTasks = ref<string[]>([])
  const weeklyOnceTasks = ref<string[]>([])
  const monthlyOnceTasks = ref<string[]>([])
  /** 按任务名覆盖的单任务时限；空数组 = 没有覆盖。 */
  const taskLimitOverrideRows = ref<TaskLimitOverrideRow[]>([])

  const periodTaskOptions = computed(() => buildPeriodTaskOptions(previewData.value?.tasks || []))

  const periodTaskRef = (key: PeriodKey): typeof dailyOnceTasks =>
    key === 'DailyOnceTasks'
      ? dailyOnceTasks
      : key === 'WeeklyOnceTasks'
        ? weeklyOnceTasks
        : monthlyOnceTasks

  const handlePeriodTaskChange = async (key: PeriodKey, values: string[]) => {
    const normalized = Array.from(new Set(values.filter(Boolean)))
    periodTaskRef(key).value = normalized
    maafwConfig.Run[key] = stringifyTaskNameList(normalized)
    await handleChange('Run', key, maafwConfig.Run[key])
  }

  const persistTaskLimitOverrides = async (rows: TaskLimitOverrideRow[]) => {
    taskLimitOverrideRows.value = rows
    maafwConfig.Run.TaskTimeLimitOverrides = stringifyTaskLimitOverrides(rows)
    await handleChange('Run', 'TaskTimeLimitOverrides', maafwConfig.Run.TaskTimeLimitOverrides)
  }

  const handleTaskLimitOverrideChange = async (rows: TaskLimitOverrideRow[]) => {
    await persistTaskLimitOverrides(
      rows
        .filter(row => Boolean(row.name))
        .map(row => ({ name: row.name, minutes: normalizeTaskLimitMinutes(row.minutes) }))
    )
  }

  const prunePeriodTaskSelections = async () => {
    const available = new Set((previewData.value?.tasks || []).map(task => task.name))
    for (const key of PERIOD_KEYS) {
      const current = periodTaskRef(key).value
      const next = current.filter(name => available.has(name))
      if (next.length !== current.length) {
        await handlePeriodTaskChange(key, next)
      }
    }
    // 覆盖表跟着 interface 走：任务名不在当前项目里就丢掉（变了才落盘）
    const nextRows = taskLimitOverrideRows.value.filter(row => available.has(row.name))
    if (nextRows.length !== taskLimitOverrideRows.value.length) {
      await persistTaskLimitOverrides(nextRows)
    }
  }

  /** 草稿刚铺上后端配置时调用：把 Run 分组里那几个 JSON 字符串字段读成本地状态 */
  const syncPeriodTasksFromConfig = () => {
    dailyOnceTasks.value = parseTaskNameList(maafwConfig.Run.DailyOnceTasks)
    weeklyOnceTasks.value = parseTaskNameList(maafwConfig.Run.WeeklyOnceTasks)
    monthlyOnceTasks.value = parseTaskNameList(maafwConfig.Run.MonthlyOnceTasks)
    taskLimitOverrideRows.value = parseTaskLimitOverrides(maafwConfig.Run.TaskTimeLimitOverrides)
  }

  return {
    dailyOnceTasks,
    weeklyOnceTasks,
    monthlyOnceTasks,
    taskLimitOverrideRows,
    periodTaskOptions,
    handlePeriodTaskChange,
    handleTaskLimitOverrideChange,
    prunePeriodTaskSelections,
    syncPeriodTasksFromConfig,
  }
}
