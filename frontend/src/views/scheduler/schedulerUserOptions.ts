import type { UserGetOut } from '@/api/models/UserGetOut'
import type { QueueScopeGroup, QueueUserScope } from './schedulerQueueScope'

/**
 * 把脚本用户接口的返回整理成用户下拉选项。
 *
 * 筛选口径必须与各脚本适配器构建运行用户列表时一致：已启用且剩余天数不为 0。
 * 顺序沿用 index，与用户管理页看到的顺序相同。用户名不唯一也不保证有值，
 * 缺名时退回 uid，至少让两条重名项还能区分开。
 */
export const toRunnableUserOptions = (
  response: Pick<UserGetOut, 'index' | 'data'>
): Array<{ label: string; value: string }> => {
  const options: Array<{ label: string; value: string }> = []
  response.index.forEach(item => {
    const info = response.data?.[item.uid]?.Info
    if (!info?.Status || info.RemainedDay === 0) return
    options.push({ value: item.uid, label: info.Name || item.uid })
  })
  return options
}

/** 全选保持不限制范围；刷新显式子集时只移除已不可运行的用户。 */
export const reconcileSelectedUserIds = (
  selectedUserIds: string[] | undefined,
  options: Array<{ value: string }>
): string[] | undefined => {
  if (selectedUserIds === undefined) {
    return undefined
  }
  const available = new Set(options.map(option => option.value))
  return selectedUserIds.filter(id => available.has(id))
}

/**
 * 调度台的「本次运行范围」面板只认「托管分组」这一种形状，
 * 脚本任务（非队列）把单个脚本包成只有一个托管的分组，就能复用同一套勾选逻辑。
 */
export const scriptScopeGroup = (
  scriptId: string | null,
  scriptName: string,
  users: Array<{ label: string; value: string }>
): QueueScopeGroup | null => (scriptId ? { scriptId, scriptName, users } : null)

/** 脚本任务的勾选口径：selectedUserIds 为 undefined 表示不限制（全部账号）。 */
export const scriptScopeSelection = (
  group: QueueScopeGroup,
  selectedUserIds: string[] | undefined
): QueueUserScope => ({
  [group.scriptId]: selectedUserIds ?? group.users.map(user => user.value),
})

/** 面板写回脚本任务的 userIds：缺键（勾满）回到 undefined，与「不限制」口径一致。 */
export const toScriptUserIds = (
  scope: QueueUserScope,
  group: QueueScopeGroup
): string[] | undefined => scope[group.scriptId]
