import type { UserGetOut } from '@/api/models/UserGetOut'

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

export type UserScopeField = 'selectedUserId' | 'resumeFromUserId'

/**
 * 「单独运行指定用户」与「从指定用户开始」只能二选一，后端同时收到会拒绝。
 * 选中其中一个时清掉另一个；清空时只清自己，不动另一个。返回需要写回的字段。
 */
export const exclusiveUserScope = (
  field: UserScopeField,
  value: string | null
): Partial<Record<UserScopeField, string | null>> => {
  if (!value) return { [field]: null }
  const other: UserScopeField = field === 'selectedUserId' ? 'resumeFromUserId' : 'selectedUserId'
  return { [field]: value, [other]: null }
}
