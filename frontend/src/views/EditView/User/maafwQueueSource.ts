// 把一份别处的任务快照（同脚本其他用户的队列）套到当前用户：哪些项能导入、哪些已失效、
// 有几项密码要重填，以及套用后的新快照。纯函数，不碰页面状态，判据都由调用方传进来。

import { resolveMaaFWTaskName } from '@/utils/maafwTaskInstance'
import type {
  MaaFWOptionInfo,
  MaaFWTaskInfo,
  MaaFWTaskOptionValue,
  MaaFWTaskSnapshot,
} from '@/types/script'
import { buildPresetAppliedSnapshot, type MaaFWPresetQueueEntry } from './maafwPresetQueue'
import { maafwMissingTaskName } from './maafwTaskChanges'

type TaskOptionMap = Record<string, Record<string, MaaFWTaskOptionValue>>

/** `{option 名: 其中 password 为 true 的输入字段名}`，只收 input 类型且至少有一个的（与后端同一口径） */
export type MaaFWPasswordFields = ReadonlyMap<string, ReadonlySet<string>>

export const maafwPasswordFields = (options: readonly MaaFWOptionInfo[]): MaaFWPasswordFields => {
  const fields = new Map<string, ReadonlySet<string>>()
  for (const option of options) {
    if (option.type !== 'input') continue
    const names = new Set(option.inputs.filter(input => input.password).map(input => input.name))
    if (names.size > 0) fields.set(option.name, names)
  }
  return fields
}

/** 来源里的一项（受管任务不在内）：`invalid` 是 interface 已没有、或当前控制器 / 资源下不可用 */
export type MaaFWQueueSourceChip = {
  id: string
  label: string
  invalid: boolean
}

export type MaaFWQueueSource = {
  /** 显示用，按来源顺序 */
  chips: MaaFWQueueSourceChip[]
  /** 能导入的项，按来源顺序 */
  entries: MaaFWPresetQueueEntry[]
  invalidCount: number
  /** 能导入的项里已填的密码字段个数：导入时这些值不带过去 */
  passwordCount: number
  /** 来源的选项表（只含能导入的项，未去密码） */
  taskOptions: TaskOptionMap
}

export type MaaFWQueueSourceContext = {
  /** interface 里的全部任务 */
  taskByName: ReadonlyMap<string, MaaFWTaskInfo>
  /** 当前控制器 / 资源下可用、且不是受管任务的任务 */
  availableTaskByName: ReadonlyMap<string, MaaFWTaskInfo>
  isManagedTask: (task: MaaFWTaskInfo) => boolean
  passwordFields: MaaFWPasswordFields
  displayName: (task: MaaFWTaskInfo) => string
}

const isFilledSecret = (value: unknown) => typeof value === 'string' && value !== ''

/** 选项表里已填的密码字段个数 */
export const countMaaFWPasswordValues = (
  taskOptions: TaskOptionMap,
  passwordFields: MaaFWPasswordFields
): number => {
  let count = 0
  for (const options of Object.values(taskOptions)) {
    for (const [optionName, value] of Object.entries(options || {})) {
      const fields = passwordFields.get(optionName)
      if (!fields || !value || typeof value !== 'object' || Array.isArray(value)) continue
      for (const [field, item] of Object.entries(value)) {
        if (fields.has(field) && isFilledSecret(item)) count += 1
      }
    }
  }
  return count
}

/**
 * 去掉密码字段的值（返回新对象，不改入参）：密文绑着原用户的 Windows 账户，别人的值也不该带走。
 * 一个 input 选项去完只剩空对象时整项去掉，回到 interface 默认值。
 */
export const stripMaaFWPasswordValues = (
  taskOptions: TaskOptionMap,
  passwordFields: MaaFWPasswordFields
): TaskOptionMap =>
  Object.fromEntries(
    Object.entries(taskOptions).map(([taskId, options]) => {
      const next: Record<string, MaaFWTaskOptionValue> = {}
      for (const [optionName, value] of Object.entries(options || {})) {
        const fields = passwordFields.get(optionName)
        if (!fields || !value || typeof value !== 'object' || Array.isArray(value)) {
          next[optionName] = value
          continue
        }
        const kept = Object.fromEntries(
          Object.entries(value).filter(([field]) => !fields.has(field))
        )
        if (Object.keys(kept).length > 0) next[optionName] = kept
      }
      return [taskId, next]
    })
  )

/**
 * 一份快照（已按勾选过滤、保留 interface 已没有的项）在当前项目下的样子：
 * 受管任务不显示、不计数；interface 已没有或当前不可用的标成失效、不导入。
 */
export const describeMaaFWQueueSource = (
  snapshot: MaaFWTaskSnapshot,
  context: MaaFWQueueSourceContext
): MaaFWQueueSource => {
  const chips: MaaFWQueueSourceChip[] = []
  const entries: MaaFWPresetQueueEntry[] = []
  const seen = new Set<string>()
  for (const taskId of snapshot.taskOrder) {
    if (seen.has(taskId)) continue
    seen.add(taskId)
    const taskName = resolveMaaFWTaskName(taskId, context.taskByName)
    const task = context.taskByName.get(taskName)
    if (task && context.isManagedTask(task)) continue
    const available = context.availableTaskByName.get(taskName)
    if (available) {
      entries.push({ id: taskId, task: available })
      chips.push({ id: taskId, label: context.displayName(available), invalid: false })
    } else {
      const label = task ? context.displayName(task) : maafwMissingTaskName(taskId)
      chips.push({ id: taskId, label, invalid: true })
    }
  }
  const entryIds = new Set(entries.map(entry => entry.id))
  const taskOptions = Object.fromEntries(
    Object.entries(snapshot.taskOptions || {}).filter(([taskId]) => entryIds.has(taskId))
  )
  return {
    chips,
    entries,
    invalidCount: chips.length - entries.length,
    passwordCount: countMaaFWPasswordValues(taskOptions, context.passwordFields),
    taskOptions,
  }
}

/**
 * 替换后队列里实际来自来源的实例数：与当前前置任务同一个 id 的来源项被去重掉（留的是当前那份），
 * 不算导入。成功提示里的「已导入 N 个任务」用它。
 */
export const countMaaFWQueueReplacementImports = (
  source: Pick<MaaFWQueueSource, 'entries'>,
  current: MaaFWTaskSnapshot,
  isPretaskId: (taskId: string) => boolean
): number => {
  const currentPretaskIds = new Set(current.taskOrder.filter(taskId => isPretaskId(taskId)))
  return new Set(
    source.entries.map(entry => entry.id).filter(taskId => !currentPretaskIds.has(taskId))
  ).size
}

/**
 * 用来源的可用项替换当前队列，与套用预设同一套：当前队列里的前置任务留在最前（带着自己的选项），
 * 其余换成来源的各个实例，每个实例带来源的那套选项（密码字段的值去掉）。
 */
export const buildMaaFWQueueReplacement = (
  source: Pick<MaaFWQueueSource, 'entries' | 'taskOptions'>,
  current: MaaFWTaskSnapshot,
  isPretaskId: (taskId: string) => boolean,
  passwordFields: MaaFWPasswordFields
): MaaFWTaskSnapshot => {
  // 每个保留下来的当前前置任务都要盖住来源的同 id 选项：当前没有选项表（如加前置任务后应用过
  // 项目预设）的用空表占位，留在默认值上，不让来源那份混进来
  const currentPretaskOptions = Object.fromEntries(
    current.taskOrder
      .filter(taskId => isPretaskId(taskId))
      .map(taskId => [taskId, current.taskOptions[taskId] ?? {}])
  )
  // 深拷贝一份：之后在队列里改选项不能改到来源（模板列表、别的用户）身上
  const sourceOptions = JSON.parse(
    JSON.stringify(stripMaaFWPasswordValues(source.taskOptions, passwordFields))
  ) as TaskOptionMap
  return buildPresetAppliedSnapshot(
    source.entries,
    { ...sourceOptions, ...currentPretaskOptions },
    current.taskOrder,
    isPretaskId
  )
}
