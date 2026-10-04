/**
 * 队列任务「本次运行范围」的纯逻辑：按托管（脚本）记录本次要运行的账号。
 *
 * 勾选状态用「缺键 = 不限制」表达：某托管没有键就表示全选（交给后端按默认口径筛选），
 * 只有用户真正改动过某个托管时才写键，这样既能保持「默认全勾选」，
 * 又不会把整份用户名单塞进请求体。
 */
export interface QueueScopeGroup {
  scriptId: string
  scriptName: string
  users: Array<{ label: string; value: string }>
}

/** 脚本ID → 本次要运行的账号；空数组表示该托管本次整项跳过。 */
export type QueueUserScope = Record<string, string[]>

/** 队列项还没选脚本、或脚本已失效时后端写入的占位值。 */
export const QUEUE_SCRIPT_PLACEHOLDER = '-'

/** 队列项里的脚本ID是否指向真实脚本；占位值与空值都不可加载。 */
export const isRunnableQueueScriptId = (scriptId: unknown): scriptId is string =>
  typeof scriptId === 'string' && scriptId !== '' && scriptId !== QUEUE_SCRIPT_PLACEHOLDER

const groupUserIds = (group: QueueScopeGroup): string[] => group.users.map(user => user.value)

/** 该托管本次勾选的账号；未改动过的托管默认全选。 */
export const selectedQueueUsers = (scope: QueueUserScope, group: QueueScopeGroup): string[] =>
  scope[group.scriptId] ?? groupUserIds(group)

/** 写回某个托管的勾选；与全选一致时删掉键，保持「默认全选」的语义。 */
export const withQueueGroupSelection = (
  scope: QueueUserScope,
  group: QueueScopeGroup,
  selected: string[]
): QueueUserScope => {
  const next = { ...scope }
  const all = groupUserIds(group)
  const normalized = all.filter(id => selected.includes(id))
  if (all.length > 0 && normalized.length === all.length) {
    delete next[group.scriptId]
    return next
  }
  next[group.scriptId] = normalized
  return next
}

/** 全部取消：每个托管都显式记为不运行任何账号，本次整项跳过。 */
export const withoutAllQueueUsers = (groups: QueueScopeGroup[]): QueueUserScope =>
  Object.fromEntries(groups.map(group => [group.scriptId, []]))

/** 队列里可运行的账号总数；为 0 表示没有可勾选的对象，此时不该拦住启动。 */
export const countQueueUsers = (groups: QueueScopeGroup[]): number =>
  groups.reduce((total, group) => total + group.users.length, 0)

/** 本次要运行的账号总数，用于拦住一个人都不跑的启动。 */
export const countQueueSelectedUsers = (scope: QueueUserScope, groups: QueueScopeGroup[]): number =>
  groups.reduce((total, group) => total + selectedQueueUsers(scope, group).length, 0)

/** 重新加载队列托管后校正勾选：丢掉已不在队列里或已不可运行的账号。 */
export const reconcileQueueScope = (
  scope: QueueUserScope,
  groups: QueueScopeGroup[]
): QueueUserScope => {
  const next: QueueUserScope = {}
  groups.forEach(group => {
    const selected = scope[group.scriptId]
    if (selected === undefined) return
    const all = groupUserIds(group)
    const kept = all.filter(id => selected.includes(id))
    if (kept.length === all.length && all.length > 0) return
    next[group.scriptId] = kept
  })
  return next
}

/** 请求体里的 queueUserIds：只发送当前队列里存在的托管，未改动过就不带这个字段。 */
export const toQueueUserIds = (
  scope: QueueUserScope,
  groups: QueueScopeGroup[]
): Record<string, string[]> | undefined => {
  const payload: Record<string, string[]> = {}
  groups.forEach(group => {
    const selected = scope[group.scriptId]
    if (selected === undefined) return
    payload[group.scriptId] = [...selected]
  })
  return Object.keys(payload).length > 0 ? payload : undefined
}
