// 特调声明不可选的任务（后端 unselectable_entries → 预览里的 unselectableReason）：项目里有，
// 但 MAS 无人值守跑不了（M9A 的小游戏要用户先手动停在对应页面）。和受管任务不是一回事：受管是
// 「MAS 自己加」，这里是「谁都不该跑」。不进「添加任务」与预设模板；已在队列里的照常显示、可删，
// 运行时由后端剔掉。

type TaskWithReason = { unselectableReason?: string | null }

/** 这个任务是不是特调声明的不可选任务 */
export const isUnselectableMaaFWTask = (task: TaskWithReason | null | undefined): boolean =>
  Boolean(task?.unselectableReason)

/** 队列里不可选任务的提示：同一原因的任务并成一条，一个原因一条（M9A 只有一条） */
export const unselectableMaaFWQueueNotices = <T extends TaskWithReason>(
  queued: readonly { task: T }[],
  displayName: (task: T) => string
): { tasks: string; reason: string }[] => {
  const byReason = new Map<string, Set<string>>()
  for (const { task } of queued) {
    const reason = task.unselectableReason?.trim()
    if (!reason) continue
    const names = byReason.get(reason) ?? new Set<string>()
    names.add(displayName(task))
    byReason.set(reason, names)
  }
  return [...byReason].map(([reason, names]) => ({ tasks: [...names].join('、'), reason }))
}
