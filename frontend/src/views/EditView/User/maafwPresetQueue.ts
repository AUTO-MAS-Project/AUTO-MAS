import { resolveMaaFWTaskName } from '@/utils/maafwTaskInstance'
import type { MaaFWTaskInfo, MaaFWTaskOptionValue, MaaFWTaskSnapshot } from '@/types/script'

type TaskNameLookup = { has: (value: string) => boolean }

/** 预设里的一项：`id` 是任务实例 id，同一任务在预设里第二次起是 `<任务名>__MAS_DUP__presetN`。 */
export type MaaFWPresetQueueEntry = {
  id: string
  task: MaaFWTaskInfo
}

/**
 * 预设快照（已按勾选过滤）里当前 controller / resource 下可用的项，保持预设顺序。
 *
 * 必须先把实例 id 解析回任务名再判断可用性：后端把预设里重复出现的任务展开成
 * 实例 id（MRA「周常配置」把「自动出征」排了 9 次，每次选项不同），拿实例 id 直接
 * 按任务名查会把第二次起的全部滤掉。
 */
export const selectPresetQueueEntries = (
  taskOrder: readonly string[],
  activeTaskByName: ReadonlyMap<string, MaaFWTaskInfo>,
  validTaskNames: TaskNameLookup
): MaaFWPresetQueueEntry[] => {
  const entries: MaaFWPresetQueueEntry[] = []
  const seen = new Set<string>()
  for (const taskId of taskOrder) {
    if (seen.has(taskId)) continue
    const task = activeTaskByName.get(resolveMaaFWTaskName(taskId, validTaskNames))
    if (!task) continue
    seen.add(taskId)
    entries.push({ id: taskId, task })
  }
  return entries
}

/**
 * 应用预设后的队列快照：原队列里的前置任务（pretask）保留在最前，其余换成预设的各个
 * 实例，每个实例带预设给它的那一套选项。
 */
export const buildPresetAppliedSnapshot = (
  entries: readonly MaaFWPresetQueueEntry[],
  presetTaskOptions: Record<string, Record<string, MaaFWTaskOptionValue>>,
  currentTaskOrder: readonly string[],
  isPretaskId: (taskId: string) => boolean
): MaaFWTaskSnapshot => {
  const candidateIds = [
    ...currentTaskOrder.filter(taskId => isPretaskId(taskId)),
    ...entries.map(entry => entry.id),
  ].filter((taskId, index, values) => values.indexOf(taskId) === index)
  const taskOrder = [
    ...candidateIds.filter(taskId => isPretaskId(taskId)),
    ...candidateIds.filter(taskId => !isPretaskId(taskId)),
  ]
  const taskIdSet = new Set(taskOrder)
  return {
    taskOrder,
    taskChecked: Object.fromEntries(taskOrder.map(taskId => [taskId, true])),
    // 每个实例的选项表拷一份：之后在队列里改选项是原地改这张表，不能改到预设本身。
    taskOptions: Object.fromEntries(
      Object.entries(presetTaskOptions)
        .filter(([taskId]) => taskIdSet.has(taskId))
        .map(([taskId, options]) => [taskId, { ...options }])
    ),
  }
}
