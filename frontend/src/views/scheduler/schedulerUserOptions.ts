import { TaskCreateIn } from '@/api/models/TaskCreateIn'
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

/**
 * 用户下拉是否可用：只有自动代理接受「只跑某一个用户」。
 *
 * 后端任务入口对 userId 的守卫是「指定单个用户仅支持脚本的自动代理任务」，脚本设置、
 * 更新与循环运行带上它一律被拒。下拉不跟着模式消失，用户就会挑到一个注定启动失败的
 * 用户，最后只看到一句「启动任务失败」。
 */
export const isUserSelectAvailable = (
  mode: TaskCreateIn['mode'] | null | undefined
): boolean => mode === TaskCreateIn.mode.AUTO_PROXY

/**
 * 请求里实际要带的 userId：与后端守卫同口径，非自动代理即使还留着上次的选择也不能带。
 */
export const resolveRequestUserId = (
  mode: TaskCreateIn['mode'] | null | undefined,
  selectedUserId: string | null | undefined
): string | undefined =>
  isUserSelectAvailable(mode) && selectedUserId ? selectedUserId : undefined
