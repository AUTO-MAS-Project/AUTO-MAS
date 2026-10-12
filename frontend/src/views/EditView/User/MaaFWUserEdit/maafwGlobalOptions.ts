// MFW 用户的全局选项：interface 的 global_option（连同各 case 下挂的子选项）每个用户只存一份
// （快照的 globalOptions）。同一个选项任务 / 资源 / 控制器自己也引用时，任务上照常存一份自己的值，
// 运行时按 PI 顺序叠在全局之上（与 MXU、MaaPiCli 一致）；只属于全局的选项（对某个任务而言）
// 任务上存的值不生效。迁移与剔除的口径与后端 interface/task_config.py 的
// build_global_option_map / build_task_option_maps / _migrate_global_option_values 一致，
// 改一处要同步另一处。

import { resolveMaaFWTaskName } from '@/utils/maafwTaskInstance'
import type {
  MaaFWInterfacePreviewData,
  MaaFWOptionInfo,
  MaaFWTaskOptionValue,
} from '@/types/script'

type OptionValues = Record<string, MaaFWTaskOptionValue>
type GlobalOptionPreview = Partial<
  Pick<
    MaaFWInterfacePreviewData,
    'globalOption' | 'options' | 'tasks' | 'resources' | 'controllers'
  >
>

/** 前置任务（pretask）伪任务的实例 id 前缀：它的选项一直只认自己声明的，不参与全局选项 */
const PRETASK_TASK_PREFIX = '__MXU_PRETASK__'
const PRETASK_TASK_ENTRY = 'MXU_PRETASK'

const isRecord = (value: unknown): value is Record<string, unknown> =>
  Boolean(value) && typeof value === 'object' && !Array.isArray(value)

const optionMapOf = (preview: GlobalOptionPreview | null | undefined) =>
  new Map((preview?.options || []).map(option => [option.name, option]))

/** 从一组顶层选项出发，连同各 case 下挂的子选项逐层展开（只收 interface 里有定义的） */
const collectOptionClosure = (
  optionMap: ReadonlyMap<string, MaaFWOptionInfo>,
  roots: readonly string[]
): Set<string> => {
  const names = new Set<string>()
  const visit = (optionNames: readonly string[]) => {
    for (const name of optionNames) {
      const option = optionMap.get(name)
      if (!option || names.has(name)) continue
      names.add(name)
      for (const caseItem of option.cases) visit(caseItem.option)
    }
  }
  visit(roots)
  return names
}

/** 全局选项名：global_option 加各 case 下挂的子选项，逐层展开 */
export const collectMaaFWGlobalOptionNames = (
  preview: GlobalOptionPreview | null | undefined
): Set<string> => collectOptionClosure(optionMapOf(preview), preview?.globalOption || [])

/**
 * 任务自己可配的选项名（任务上存值的那些）：全部资源与控制器的 option 加任务自己的 option，
 * 逐层展开（与后端 build_task_option_maps 同口径，不按当前控制器 / 资源过滤）。
 * interface 已没有的任务只算资源与控制器的。
 */
const collectTaskOwnOptionNames = (
  preview: GlobalOptionPreview | null | undefined,
  optionMap: ReadonlyMap<string, MaaFWOptionInfo>,
  taskName: string
): Set<string> => {
  const task = (preview?.tasks || []).find(
    item => item.name === taskName && item.entry !== PRETASK_TASK_ENTRY
  )
  return collectOptionClosure(optionMap, [
    ...(preview?.resources || []).flatMap(resource => resource.option || []),
    ...(preview?.controllers || []).flatMap(controller => controller.option || []),
    ...(task?.option || []),
  ])
}

/** 用户页要不要显示「全局选项」：有一个顶层全局选项能在当前控制器 / 资源下编辑就显示 */
export const hasEditableMaaFWGlobalOptions = (
  preview: GlobalOptionPreview | null | undefined,
  controllerName: string,
  resourceName: string
) => {
  const optionMap = optionMapOf(preview)
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
 * 旧配置兼容：全局选项表里没有合法值的项（缺、null、数字、不存在的 case……先丢掉），按队列
 * 顺序取第一个勾选的、带合法值的任务实例的值；没有再取第一个未勾选的；都没有就不写，留给
 * 默认值。只看这一项对该实例来说「只属于全局」的实例（任务 / 资源 / 控制器自己也引用的，
 * 任务上的值是任务自己的）；前置任务与 interface 已没有的任务不看。
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
  const optionMap = optionMapOf(preview)
  const names = collectMaaFWGlobalOptionNames(preview)
  const values: OptionValues = Object.fromEntries(
    Object.entries(isRecord(raw.globalOptions) ? raw.globalOptions : {}).filter(
      ([name, value]) => !names.has(name) || isValidOptionValue(optionMap.get(name)!, value)
    )
  ) as OptionValues
  const missing = [...names].filter(name => !(name in values))
  if (missing.length === 0) return values

  const validTaskNames = new Set(
    (preview?.tasks || []).filter(task => task.entry !== PRETASK_TASK_ENTRY).map(task => task.name)
  )
  const candidates = (Array.isArray(raw.taskOrder) ? raw.taskOrder : [])
    .filter(
      (taskId): taskId is string =>
        typeof taskId === 'string' && !taskId.startsWith(PRETASK_TASK_PREFIX)
    )
    .map(taskId => ({ taskId, taskName: resolveMaaFWTaskName(taskId, validTaskNames) }))
    .filter(({ taskName }) => validTaskNames.has(taskName))
  const checked = isRecord(raw.taskChecked) ? raw.taskChecked : {}
  const ordered = [
    ...candidates.filter(({ taskId }) => Boolean(checked[taskId])),
    ...candidates.filter(({ taskId }) => !checked[taskId]),
  ]
  const ownNamesByTask = new Map<string, Set<string>>()
  const ownNamesOf = (taskName: string) => {
    let own = ownNamesByTask.get(taskName)
    if (!own) {
      own = collectTaskOwnOptionNames(preview, optionMap, taskName)
      ownNamesByTask.set(taskName, own)
    }
    return own
  }
  const taskOptions = isRecord(raw.taskOptions) ? raw.taskOptions : {}
  for (const name of missing) {
    const option = optionMap.get(name)
    if (!option) continue
    for (const { taskId, taskName } of ordered) {
      if (ownNamesOf(taskName).has(name)) continue
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

/**
 * 各任务实例的选项里去掉对它只属于全局的选项（返回新对象，不改入参）：任务 / 资源 / 控制器
 * 自己也引用的留着（那是任务自己的值）；前置任务的选项原样保留。没有 interface 时原样返回。
 */
export const withoutMaaFWGlobalOnlyOptions = (
  taskOptions: Record<string, OptionValues>,
  preview: GlobalOptionPreview | null | undefined
): Record<string, OptionValues> => {
  const globalNames = collectMaaFWGlobalOptionNames(preview)
  if (globalNames.size === 0) return taskOptions
  const optionMap = optionMapOf(preview)
  const validTaskNames = new Set(
    (preview?.tasks || []).filter(task => task.entry !== PRETASK_TASK_ENTRY).map(task => task.name)
  )
  return Object.fromEntries(
    Object.entries(taskOptions).map(([taskId, options]) => {
      if (taskId.startsWith(PRETASK_TASK_PREFIX) || !isRecord(options)) return [taskId, options]
      const own = collectTaskOwnOptionNames(
        preview,
        optionMap,
        resolveMaaFWTaskName(taskId, validTaskNames)
      )
      return [
        taskId,
        Object.fromEntries(
          Object.entries(options).filter(([name]) => !globalNames.has(name) || own.has(name))
        ),
      ]
    })
  )
}
