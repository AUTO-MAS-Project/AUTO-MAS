import { buildMaaFWTaskInstanceId, resolveMaaFWTaskName } from '@/utils/maafwTaskInstance'
import type { MaaFWInterfacePreviewData, MaaFWTaskSnapshot } from '@/types/script'

/** 实例显示名的最大长度（重命名输入框的上限） */
export const MAAFW_TASK_LABEL_MAX_LENGTH = 40

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
 * 快照里的实例显示名：只留 `taskIds` 里的实例、键值都是字符串、去首尾空白后非空的。
 * 显示名跟着实例走，实例不在队列里了名字也不留。
 */
export const pickMaaFWTaskLabels = (
  raw: unknown,
  taskIds: Iterable<string>
): Record<string, string> => {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return {}
  const taskIdSet = new Set(taskIds)
  const labels: Record<string, string> = {}
  for (const [taskId, label] of Object.entries(raw as Record<string, unknown>)) {
    if (!taskIdSet.has(taskId) || typeof label !== 'string') continue
    const trimmed = label.trim()
    if (trimmed) labels[taskId] = trimmed
  }
  return labels
}

/** 没有显示名时不写 `taskLabels` 这个键：没改过名的用户快照与以前逐字节相同 */
export const taskLabelsField = (labels: Record<string, string>) =>
  Object.keys(labels).length > 0 ? { taskLabels: labels } : {}

/**
 * 改一份实例的显示名，返回新的显示名表（不改入参）。去首尾空白后为空、或与任务原本的显示名
 * （interface 的 label，没有就是 name）相同时删掉这一条，视为没改名；其余截到上限后存下。
 * 先比原名再截断：原名本身超过上限时，不改直接确定不能存下一份截断后的名字。
 */
export const withMaaFWTaskLabel = (
  labels: Record<string, string> | undefined,
  taskId: string,
  name: string,
  defaultName: string
): Record<string, string> => {
  const next = { ...(labels || {}) }
  const trimmed = name.trim()
  if (!trimmed || trimmed === defaultName) {
    delete next[taskId]
  } else {
    next[taskId] = trimmed.slice(0, MAAFW_TASK_LABEL_MAX_LENGTH)
  }
  return next
}

/**
 * 在 `taskId` 正下方插一份同任务的新实例：勾选、选项（深拷贝）与显示名一起复制。
 * 新实例 id 走重复实例体系（`<任务名>__MAS_DUP__<随机后缀>`）。原实例不在队列里时返回 null。
 */
export const duplicateMaaFWQueuedTask = (
  snapshot: MaaFWTaskSnapshot,
  taskId: string,
  taskName: string
): { snapshot: MaaFWTaskSnapshot; taskId: string } | null => {
  const index = snapshot.taskOrder.indexOf(taskId)
  if (index < 0) return null
  const newTaskId = buildMaaFWTaskInstanceId(taskName, new Set(snapshot.taskOrder))
  const taskOrder = [...snapshot.taskOrder]
  taskOrder.splice(index + 1, 0, newTaskId)
  const taskOptions = { ...snapshot.taskOptions }
  if (snapshot.taskOptions[taskId]) {
    taskOptions[newTaskId] = JSON.parse(JSON.stringify(snapshot.taskOptions[taskId]))
  }
  const label = snapshot.taskLabels?.[taskId]
  const taskLabels = label ? { ...snapshot.taskLabels, [newTaskId]: label } : snapshot.taskLabels
  return {
    taskId: newTaskId,
    snapshot: {
      taskOrder,
      taskChecked: {
        ...snapshot.taskChecked,
        [newTaskId]: snapshot.taskChecked[taskId] !== false,
      },
      taskOptions,
      ...taskLabelsField(taskLabels || {}),
    },
  }
}

/**
 * `keepMissing`：用户自己的队列要保留 interface 已没有的任务（项目更新改了 name），
 * 它们在队列里显示成虚影，删不删由用户定；预设模板照旧只要认得的任务。
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

  const taskOptions = Object.fromEntries(
    Object.entries(parsed.taskOptions || {}).filter(([taskId]) => queuedTaskIds.has(taskId))
  )

  return {
    taskOrder: queuedOrder,
    taskChecked,
    taskOptions,
    ...taskLabelsField(pickMaaFWTaskLabels(parsed.taskLabels, queuedTaskIds)),
  }
}
