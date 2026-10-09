// MFW 用户的全局选项：interface 的 global_option（连同各 case 下挂的子选项）每个用户只存一份
// （快照的 globalOptions），所有任务共用，不再按任务各存一份。迁移与剔除的口径与后端
// interface/task_config.py 的 build_global_option_map / _migrate_global_option_values 一致，
// 改一处要同步另一处。

import { resolveMaaFWTaskName } from '@/utils/maafwTaskInstance'
import type {
  MaaFWInterfacePreviewData,
  MaaFWOptionInfo,
  MaaFWTaskOptionValue,
} from '@/types/script'

type OptionValues = Record<string, MaaFWTaskOptionValue>
type GlobalOptionPreview = Partial<
  Pick<MaaFWInterfacePreviewData, 'globalOption' | 'options' | 'tasks'>
>

/** 前置任务（pretask）伪任务的实例 id 前缀：它的选项一直只认自己声明的，不参与全局选项 */
const PRETASK_TASK_PREFIX = '__MXU_PRETASK__'
const PRETASK_TASK_ENTRY = 'MXU_PRETASK'

const isRecord = (value: unknown): value is Record<string, unknown> =>
  Boolean(value) && typeof value === 'object' && !Array.isArray(value)

/** 全局选项名：global_option 加各 case 下挂的子选项，逐层展开 */
export const collectMaaFWGlobalOptionNames = (
  preview: GlobalOptionPreview | null | undefined
): Set<string> => {
  const names = new Set<string>()
  const optionMap = new Map((preview?.options || []).map(option => [option.name, option]))
  const visit = (optionNames: readonly string[]) => {
    for (const name of optionNames) {
      const option = optionMap.get(name)
      if (!option || names.has(name)) continue
      names.add(name)
      for (const caseItem of option.cases) visit(caseItem.option)
    }
  }
  visit(preview?.globalOption || [])
  return names
}

/** 用户页要不要显示「全局选项」：有一个顶层全局选项能在当前控制器 / 资源下编辑就显示 */
export const hasEditableMaaFWGlobalOptions = (
  preview: GlobalOptionPreview | null | undefined,
  controllerName: string,
  resourceName: string
) => {
  const optionMap = new Map((preview?.options || []).map(option => [option.name, option]))
  return (preview?.globalOption || []).some(name => {
    const option = optionMap.get(name)
    // 快捷键在脚本页统一设置，选项编辑器不显示它（见 MaaFWTaskOptionEditor）
    if (!option || option.type === 'hotkey') return false
    if (option.controller.length > 0 && !option.controller.includes(controllerName)) return false
    if (option.resource.length > 0 && !option.resource.includes(resourceName)) return false
    return true
  })
}

const isValidOptionValue = (option: MaaFWOptionInfo, value: unknown) => {
  if (['select', 'scan_select', 'switch'].includes(option.type)) {
    return typeof value === 'string' && option.cases.some(caseItem => caseItem.name === value)
  }
  if (option.type === 'checkbox') return Array.isArray(value)
  if (option.type === 'input' || option.type === 'hotkey') return isRecord(value)
  return false
}

/**
 * 旧配置兼容：全局选项表里缺的项，按队列顺序取第一个带了合法值的任务实例的值（勾选的优先，
 * 前置任务与 interface 已没有的任务不看）；都没有就不写，留给默认值。
 */
export const migrateMaaFWGlobalOptions = (
  raw: {
    taskOrder?: unknown
    taskChecked?: unknown
    taskOptions?: unknown
    globalOptions?: unknown
  },
  preview: GlobalOptionPreview | null | undefined
): OptionValues => {
  const values: OptionValues = isRecord(raw.globalOptions)
    ? { ...(raw.globalOptions as OptionValues) }
    : {}
  const names = collectMaaFWGlobalOptionNames(preview)
  const missing = [...names].filter(name => !(name in values))
  if (missing.length === 0) return values

  const validTaskNames = new Set(
    (preview?.tasks || []).filter(task => task.entry !== PRETASK_TASK_ENTRY).map(task => task.name)
  )
  const candidates = (Array.isArray(raw.taskOrder) ? raw.taskOrder : []).filter(
    (taskId): taskId is string =>
      typeof taskId === 'string' &&
      !taskId.startsWith(PRETASK_TASK_PREFIX) &&
      validTaskNames.has(resolveMaaFWTaskName(taskId, validTaskNames))
  )
  const checked = isRecord(raw.taskChecked) ? raw.taskChecked : {}
  const ordered = [
    ...candidates.filter(taskId => Boolean(checked[taskId])),
    ...candidates.filter(taskId => !checked[taskId]),
  ]
  const taskOptions = isRecord(raw.taskOptions) ? raw.taskOptions : {}
  const optionMap = new Map((preview?.options || []).map(option => [option.name, option]))
  for (const name of missing) {
    const option = optionMap.get(name)
    if (!option) continue
    for (const taskId of ordered) {
      const options = taskOptions[taskId]
      if (!isRecord(options) || !(name in options)) continue
      if (isValidOptionValue(option, options[name])) {
        values[name] = options[name] as MaaFWTaskOptionValue
        break
      }
    }
  }
  return values
}

/** 各任务实例的选项里去掉全局选项（返回新对象，不改入参）；前置任务的选项原样保留 */
export const withoutMaaFWGlobalOptions = (
  taskOptions: Record<string, OptionValues>,
  globalOptionNames: ReadonlySet<string>
): Record<string, OptionValues> => {
  if (globalOptionNames.size === 0) return taskOptions
  return Object.fromEntries(
    Object.entries(taskOptions).map(([taskId, options]) => [
      taskId,
      taskId.startsWith(PRETASK_TASK_PREFIX) || !isRecord(options)
        ? options
        : Object.fromEntries(
            Object.entries(options).filter(([name]) => !globalOptionNames.has(name))
          ),
    ])
  )
}
