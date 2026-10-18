import type { SchedulerTab } from './schedulerConstants'

/**
 * 找一个能接着跑该队列 / 脚本的调度台：选的是同一个任务项、当前没有任务在跑、不是主调度台。
 *
 * 定时、启动时运行、首页快速开始和托盘每次启动都是新的运行 ID，只按运行 ID 找台会一次多一个；
 * 主调度台留给手动操作，自动启动的任务不去覆盖上面的日志和已选的起始脚本 / 用户。
 * `startingKeys` 是手动启动还没等到返回的台，它们马上要挂上自己的任务，同样跳过。
 */
export const findReusableSchedulerTab = (
  tabs: SchedulerTab[],
  selectedTaskId: string | null | undefined,
  startingKeys: ReadonlySet<string> = new Set()
): SchedulerTab | undefined => {
  if (!selectedTaskId) return undefined
  return tabs.find(
    tab =>
      tab.key !== 'main' &&
      !startingKeys.has(tab.key) &&
      // 状态值是逻辑用的中文字面量，不接词表
      tab.status !== '运行' &&
      !tab.taskId &&
      tab.selectedTaskId === selectedTaskId
  )
}
