import { resolveMaaFWTaskName } from '@/utils/maafwTaskInstance'
import type { MaaFWTaskInfo } from '@/types/script'

/**
 * 任务在脚本当前的控制器 / 资源下能不能用：任务声明了 controller / resource 列表时必须包含当前那个。
 * 控制器或资源还没定（项目没有可用的）时一律不可用。用户页的队列显示、「添加任务」候选与
 * 「N 项不可用已隐藏」都按这一个口径。
 */
export function isMaaFWTaskActiveFor(
  task: Pick<MaaFWTaskInfo, 'controller' | 'resource'>,
  controllerName: string,
  resourceName: string
) {
  if (!controllerName || !resourceName) return false
  if (task.controller.length > 0 && !task.controller.includes(controllerName)) return false
  if (task.resource.length > 0 && !task.resource.includes(resourceName)) return false
  return true
}

export type MaaFWHiddenQueueTask = {
  /** 队列里的实例 id */
  id: string
  /** 队列行上会显示的名字：改过的显示名优先，其次 label、name */
  displayName: string
}

/**
 * 队列里因为当前控制器 / 资源不兼容而不显示的实例（快照里原样留着，切回去就回来）。
 * 只看 interface 里还有的任务；interface 已没有的是虚影，照常显示，不算在这里。只读，不改快照。
 */
export function listMaaFWHiddenQueueTasks(
  taskOrder: readonly string[],
  taskByName: ReadonlyMap<string, MaaFWTaskInfo>,
  controllerName: string,
  resourceName: string,
  taskLabels?: Record<string, string> | null
): MaaFWHiddenQueueTask[] {
  return taskOrder.flatMap(taskId => {
    const task = taskByName.get(resolveMaaFWTaskName(taskId, taskByName))
    if (!task || isMaaFWTaskActiveFor(task, controllerName, resourceName)) return []
    return [{ id: taskId, displayName: taskLabels?.[taskId] || task.label || task.name }]
  })
}

/** 悬停提示里的名单：同名的合成一行，带份数 */
export function summarizeMaaFWHiddenQueueTasks(hidden: readonly MaaFWHiddenQueueTask[]) {
  const counts = new Map<string, number>()
  for (const item of hidden) counts.set(item.displayName, (counts.get(item.displayName) || 0) + 1)
  return Array.from(counts, ([name, count]) => (count > 1 ? `${name} ×${count}` : name))
}
