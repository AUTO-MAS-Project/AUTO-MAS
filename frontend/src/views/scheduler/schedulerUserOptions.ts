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
