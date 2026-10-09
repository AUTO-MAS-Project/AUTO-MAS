import { resolveMaaFWTaskName } from '@/utils/maafwTaskInstance'
import type { MaaFWInterfacePreviewData, MaaFWTaskSnapshot } from '@/types/script'
import { migrateMaaFWGlobalOptions, withoutMaaFWGlobalOnlyOptions } from './maafwGlobalOptions'

export const parseTaskSnapshot = (
  raw: string | MaaFWTaskSnapshot | Record<string, unknown> | null | undefined
) => {
  if (!raw) return {}
  if (typeof raw !== 'string') return raw
  try {
    return JSON.parse(raw)
  } catch {
    return {}
  }
}

/**
 * `keepMissing`：用户自己的队列要保留 interface 已没有的任务（项目更新改了 name），
 * 它们在队列里显示成虚影，删不删由用户定；预设模板照旧只要认得的任务。
 *
 * 全局选项（见 maafwGlobalOptions.ts）：旧配置里散在各任务上的、只属于全局的值迁进
 * `globalOptions`，任务选项里的这些值（含后端为降级兼容双写的副本）去掉，不显示、不生效；
 * 任务 / 资源 / 控制器自己也引用的选项是任务自己的值，留着。没有任何全局选项值时不带这个键。
 * 没有 interface 时认不出哪些是全局选项，原样保留。
 */
export const normalizeTaskSnapshot = (
  raw: string | MaaFWTaskSnapshot | Record<string, unknown> | null | undefined,
  preview: MaaFWInterfacePreviewData | null,
  { keepMissing = false }: { keepMissing?: boolean } = {}
): MaaFWTaskSnapshot => {
  const parsed = parseTaskSnapshot(raw) as Partial<MaaFWTaskSnapshot>
  const tasks = preview?.tasks || []
  const knownTaskNames = new Set(tasks.map(task => task.name))
  const order = Array.isArray(parsed.taskOrder)
    ? parsed.taskOrder.filter(
        taskId =>
          typeof taskId === 'string' &&
          (keepMissing || knownTaskNames.has(resolveMaaFWTaskName(taskId, knownTaskNames)))
      )
    : []
  const taskChecked: Record<string, boolean> = Object.fromEntries(
    order.filter(taskId => parsed.taskChecked?.[taskId] !== false).map(taskId => [taskId, true])
  )
  const queuedOrder = order.filter(taskId => taskChecked[taskId])
  const queuedTaskIds = new Set(queuedOrder)

  const globalOptions = migrateMaaFWGlobalOptions(parsed, preview)
  const taskOptions = withoutMaaFWGlobalOnlyOptions(
    Object.fromEntries(
      Object.entries(parsed.taskOptions || {}).filter(([taskId]) => queuedTaskIds.has(taskId))
    ),
    preview
  )

  return {
    taskOrder: queuedOrder,
    taskChecked,
    taskOptions,
    ...(Object.keys(globalOptions).length > 0 ? { globalOptions } : {}),
  }
}
