import type { ComboBoxItem } from '@/api/models/ComboBoxItem'

export type SchedulerTaskOption = ComboBoxItem & {
  title: string
}

/**
 * 将后端任务下拉项转换为仅用于调度中心展示的选项。
 *
 * label 是后端根据真实脚本类型和配置/任务名称生成的权威文本，
 * value 则是创建任务时使用的 ID；这里不重写任一字段，只补充完整文本提示。
 */
export const buildSchedulerTaskOptions = (
  options: readonly ComboBoxItem[]
): SchedulerTaskOption[] =>
  options.map(option => ({
    ...option,
    title: option.label,
  }))
