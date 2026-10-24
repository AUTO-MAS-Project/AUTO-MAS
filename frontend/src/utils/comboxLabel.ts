import { translate as t } from '@/i18n'
import type { ComboBoxItem } from '@/api'

/**
 * combox 选项的本地化展示。
 *
 * 后端 combox 接口（任务/脚本/模拟器/计划下拉）原先直接返回中文 label
 * （「未选择」「队列 - x」「脚本 - x」），英文/日文界面打开下拉全是中文。
 * 现在后端在选项上给出 labelKey / kind / name / scriptType（见
 * app/models/schema.py ComboBoxItem 与 app/core/config.py 的五个 get_*_combox），
 * 前端统一在这里拼装本地化文案：
 * - labelKey   占位（未选择）与固定项，直接整条翻译；
 * - kind+name 队列/脚本项，本地化前缀 + 用户起的实体名（实体名不翻译）；
 * - kind      同时是稳定类别，isQueueTaskOption 让调度台不再靠 label 中文前缀判断。
 * 兜底：旧后端（或没带新字段的接口）逐字回退 label，行为与改造前一致。
 */

type ItemLike = Pick<ComboBoxItem, 'label' | 'value'> & Partial<ComboBoxItem>

/** 单个选项的展示文案。 */
export const comboxLabel = (item: ItemLike): string => {
  if (item.labelKey) return t(item.labelKey)
  if (item.kind === 'queue') {
    return t('combox.queue', { name: item.name ?? item.label })
  }
  if (item.kind === 'script') {
    const name = item.name ?? item.label
    const typeKey = item.scriptType ? `combox.scriptType.${item.scriptType}` : ''
    return typeKey ? `${t(typeKey)} - ${name}` : name
  }
  return item.label
}

/** 把一组 combox 选项映射为本地化展示的 options（a-select :options 形状）。 */
export const comboxOptions = <T extends ItemLike>(items: T[]): (T & { label: string })[] =>
  items.map(item => ({ ...item, label: comboxLabel(item) }))

/** 队列任务？用 kind 判断，不再看 label 的中文前缀。 */
export const isQueueTaskOption = (item: ItemLike | undefined): boolean => item?.kind === 'queue'

/** 脚本任务？（kind 存在且不是占位/队列即脚本，与后端 get_task_combox 结构一致） */
export const isScriptTaskOption = (item: ItemLike | undefined): boolean =>
  Boolean(item && item.kind !== 'placeholder' && item.kind !== 'queue')

/** MaaEnd 脚本任务？（通知兜底用；队列任务恒 false） */
export const isMaaEndTaskOption = (item: ItemLike | undefined): boolean =>
  item?.scriptType === 'MaaEnd'
