import { computed, ref, type Ref } from 'vue'
import type { MaaFWInterfacePreviewData, MaaFWScriptConfig } from '@/types/script'
import {
  PERIOD_KEYS,
  buildPeriodTaskOptions,
  parseTaskNameList,
  stringifyTaskNameList,
  type PeriodKey,
} from './periodTasks'
import {
  countTaskLimitOverrides,
  parseTaskLimitOverrides,
  pruneTaskLimitOverrides,
  stringifyTaskLimitOverrides,
} from './taskTimeLimits'
import type { MaaFWScriptChangeHandler } from './useMaaFWScriptDraft'

/** 「每日 / 每周 / 每月只跑一次」的任务选择：本地列表、下拉选项、改动落盘与按 interface 修剪。 */
export function useMaaFWPeriodTasks(
  maafwConfig: MaaFWScriptConfig,
  previewData: Ref<MaaFWInterfacePreviewData | null>,
  handleChange: MaaFWScriptChangeHandler
) {
  const dailyOnceTasks = ref<string[]>([])
  const weeklyOnceTasks = ref<string[]>([])
  const monthlyOnceTasks = ref<string[]>([])

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

  const prunePeriodTaskSelections = async () => {
    const available = new Set((previewData.value?.tasks || []).map(task => task.name))
    for (const key of PERIOD_KEYS) {
      const current = periodTaskRef(key).value
      const next = current.filter(name => available.has(name))
      if (next.length !== current.length) {
        await handlePeriodTaskChange(key, next)
      }
    }
    // 按任务设置的单任务时限同样跟着 interface 走：任务名不在当前项目里就丢掉（变了才落盘）
    const overrides = parseTaskLimitOverrides(maafwConfig.Run.TaskTimeLimitOverrides)
    const nextOverrides = pruneTaskLimitOverrides(overrides, available)
    if (countTaskLimitOverrides(nextOverrides) !== countTaskLimitOverrides(overrides)) {
      maafwConfig.Run.TaskTimeLimitOverrides = stringifyTaskLimitOverrides(nextOverrides)
      await handleChange('Run', 'TaskTimeLimitOverrides', maafwConfig.Run.TaskTimeLimitOverrides)
    }
  }

  /** 草稿刚铺上后端配置时调用：把三个 JSON 字符串字段读成本地列表 */
  const syncPeriodTasksFromConfig = () => {
    dailyOnceTasks.value = parseTaskNameList(maafwConfig.Run.DailyOnceTasks)
    weeklyOnceTasks.value = parseTaskNameList(maafwConfig.Run.WeeklyOnceTasks)
    monthlyOnceTasks.value = parseTaskNameList(maafwConfig.Run.MonthlyOnceTasks)
  }

  return {
    dailyOnceTasks,
    weeklyOnceTasks,
    monthlyOnceTasks,
    periodTaskOptions,
    handlePeriodTaskChange,
    prunePeriodTaskSelections,
    syncPeriodTasksFromConfig,
  }
}
