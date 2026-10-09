import { resolveMaaFWTaskName } from '@/utils/maafwTaskInstance'
import type { MaaFWInterfacePreviewData, MaaFWTaskSnapshot } from '@/types/script'
import {
  collectMaaFWGlobalOptionNames,
  migrateMaaFWGlobalOptions,
  withoutMaaFWGlobalOptions,
} from './maafwGlobalOptions'

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
 * 全局选项（见 maafwGlobalOptions.ts）：旧配置里散在各任务上的值迁进 `globalOptions`，
 * 任务选项里的同名值去掉，下次保存就是新形状；没有任何全局选项值时不带这个键。
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

  const globalOptionNames = collectMaaFWGlobalOptionNames(preview)
  const globalOptions = migrateMaaFWGlobalOptions(parsed, preview)
  const taskOptions = withoutMaaFWGlobalOptions(
    Object.fromEntries(
      Object.entries(parsed.taskOptions || {}).filter(([taskId]) => queuedTaskIds.has(taskId))
    ),
    globalOptionNames
  )

  return {
    taskOrder: queuedOrder,
    taskChecked,
    taskOptions,
    ...(Object.keys(globalOptions).length > 0 ? { globalOptions } : {}),
  }
}
