// 特调的受管任务（flavor.managedTaskEntries）：由后端特调全权控制、不许用户自己加。
// 这里只按 entry 与特调描述对象里的字段判断，不认识任何具体特调；判据与后端特调的整理规则
// （M9A 是 app/task/M9A/managed.py）保持一致，改一边要同步另一边。

import type { MaaFWOptionInfo, MaaFWTaskOptionValue } from '@/types/script'

type TaskWithEntry = { entry?: string | null }
type TaskWithOptions = TaskWithEntry & { name: string; option?: string[] | null }

/** 受管的切号任务：队列里它的有效实例（勾选且目标账号非空）≥ 2 且资源在 resources 里时要拆用户 */
export type MaaFWManagedAccountTask = {
  entry: string
  resources: readonly string[]
}

/** 这个任务是不是受管任务（按 interface 里任务的 entry） */
export const isManagedMaaFWTask = (
  task: TaskWithEntry | null | undefined,
  managedEntries: ReadonlySet<string>
): boolean => Boolean(task?.entry && managedEntries.has(task.entry))

/** 去掉受管任务：「添加任务」候选与预设模板都用它 */
export const withoutManagedMaaFWTasks = <T extends TaskWithEntry>(
  tasks: readonly T[],
  managedEntries: ReadonlySet<string>
): T[] => tasks.filter(task => !isManagedMaaFWTask(task, managedEntries))

const firstText = (value: unknown): string => {
  if (typeof value === 'string') return value.trim()
  if (value && typeof value === 'object') {
    for (const item of Object.values(value as Record<string, unknown>)) {
      const text = firstText(item)
      if (text) return text
    }
  }
  return ''
}

/**
 * 切号实例的目标账号：任务第一个 input 型选项的第一个输入字段；找不到约定字段时取选项里第一个
 * 非空字符串。与后端 flavor 的 _entry_and_account_readers 同一口径。
 */
export const maafwAccountOf = (
  task: TaskWithOptions,
  taskOptions: Record<string, MaaFWTaskOptionValue> | undefined,
  options: readonly MaaFWOptionInfo[]
): string => {
  if (!taskOptions) return ''
  const optionByName = new Map(options.map(option => [option.name, option] as const))
  for (const optionName of task.option || []) {
    const option = optionByName.get(optionName)
    if (option?.type !== 'input' || option.inputs.length === 0) continue
    const value = taskOptions[optionName]
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      return String(value[option.inputs[0].name] ?? '').trim()
    }
    return firstText(value)
  }
  return firstText(taskOptions)
}

export type ManagedMaaFWQueueState =
  /** 要拆用户：该用户在拆分前不会运行 */
  | { kind: 'split'; count: number; accounts: string }
  /** 只是残留：运行照常，下次保存或重启时会移出队列 */
  | { kind: 'notice'; tasks: string }
  | null

/**
 * 队列里受管任务的状态。队列里的项都是勾选的（用户页只存勾选的）。
 * 只有「资源在 accountTask.resources 里、有效切号 ≥ 2」才是 split，其余残留都是 notice。
 */
export const managedMaaFWQueueState = <T extends TaskWithOptions>(
  queued: readonly { id: string; task: T }[],
  params: {
    managedEntries: ReadonlySet<string>
    accountTask: MaaFWManagedAccountTask | null
    resourceName: string
    taskOptions: Record<string, Record<string, MaaFWTaskOptionValue>>
    options: readonly MaaFWOptionInfo[]
    displayName: (task: T) => string
  }
): ManagedMaaFWQueueState => {
  const managed = queued.filter(item => isManagedMaaFWTask(item.task, params.managedEntries))
  if (managed.length === 0) return null
  const accountTask = params.accountTask
  if (accountTask && accountTask.resources.includes(params.resourceName)) {
    const accounts = managed
      .filter(item => item.task.entry === accountTask.entry)
      .map(item => maafwAccountOf(item.task, params.taskOptions[item.id], params.options))
      .filter(Boolean)
    if (accounts.length >= 2) {
      return { kind: 'split', count: accounts.length, accounts: accounts.join('、') }
    }
  }
  return {
    kind: 'notice',
    tasks: [...new Set(managed.map(item => params.displayName(item.task)))].join('、'),
  }
}
