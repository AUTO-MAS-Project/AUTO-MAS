// 特调的受管任务（flavor.managedTaskEntries）：由后端特调全权控制、不许用户自己加。
// 这里只按 entry 过滤，不认识任何具体特调；哪些 entry 受管写在各特调的描述对象里。

type TaskWithEntry = { entry?: string | null }

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

/** 队列里残留的受管任务的警告插值：个数与去重后的显示名（没有就返回 null） */
export const managedMaaFWQueueSummary = <T extends TaskWithEntry & { name: string }>(
  queuedTasks: readonly T[],
  managedEntries: ReadonlySet<string>,
  displayName: (task: T) => string
): { count: number; tasks: string } | null => {
  const managed = queuedTasks.filter(task => isManagedMaaFWTask(task, managedEntries))
  if (managed.length === 0) return null
  return {
    count: managed.length,
    tasks: [...new Set(managed.map(displayName))].join('、'),
  }
}
