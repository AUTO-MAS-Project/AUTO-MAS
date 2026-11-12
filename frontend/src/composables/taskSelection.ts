import { TaskMode, type TaskCreateIn, type TaskSelectionNode, type TaskParams } from '@/api'
import { translate as t } from '@/i18n'
import type { TaskTarget } from './useTaskOptions'

export type ScopeSelection = 'all' | 'explicit' | 'none'
export interface TaskScopeUser {
  uid: string
  name: string
  enabled: boolean
  remainedDay: number
  params?: TaskParams
}
export interface TaskScopeEntry {
  /** 队列中是队列项 UUID，直接运行时是托管 UUID。 */
  uid: string
  scriptId: string
  missing?: boolean
  name: string
  users: TaskScopeUser[]
  selection: ScopeSelection
  selected: string[]
  params: TaskParams
}
export interface TaskScopeDraft {
  uid: string
  kind: TaskTarget['kind']
  selection: ScopeSelection
  params: TaskParams
  entries: TaskScopeEntry[]
}

export const indexed = (nodes: TaskSelectionNode[]): Record<string, TaskSelectionNode> =>
  Object.fromEntries(nodes.map((node, index) => [String(index), node]))

/** 快捷启动与范围编辑共用创建形状，目标类型来自配置而非文案。 */
export function targetRequest(
  target: Pick<TaskTarget, 'kind' | 'value'>,
  mode = TaskMode.AUTO_PROXY
): TaskCreateIn {
  if (mode !== TaskMode.AUTO_PROXY) {
    if (target.kind !== 'script') throw new Error(t('core.scheduler.scope.targetMissing'))
    return {
      mode,
      tasks: indexed([{ uid: target.value, children: indexed([{ uid: 'default' }]) }]),
    }
  }
  return {
    mode,
    tasks: indexed([
      target.kind === 'queue'
        ? { uid: target.value }
        : { uid: '-', children: indexed([{ uid: target.value }]) },
    ]),
  }
}

export function selectedScopeUsers(entry: TaskScopeEntry): string[] {
  if (entry.selection === 'none') return []
  return entry.selection === 'all' ? entry.users.map(user => user.uid) : entry.selected
}

/** 显式全选仍保留具体用户；只在选择语义为 all 时使用空子树。 */
export function scopeRequest(draft: TaskScopeDraft, mode = TaskMode.AUTO_PROXY): TaskCreateIn {
  if (mode !== TaskMode.AUTO_PROXY) throw new Error(t('core.scheduler.scope.targetMissing'))
  const overrides = draft.entries.some(
    entry =>
      Object.keys(entry.params).length ||
      entry.users.some(user => user.params && Object.keys(user.params).length)
  )
  if (draft.selection === 'all' && !overrides) {
    const request = targetRequest({ value: draft.uid, kind: draft.kind }, mode)
    if (Object.keys(draft.params).length) request.tasks['0'].params = draft.params
    return request
  }
  const entries =
    draft.selection === 'none' ? [] : draft.entries.filter(entry => entry.selection !== 'none')
  if (!entries.length) throw new Error(t('core.scheduler.scope.emptySelection'))
  const scripts = entries.map(entry => {
    if (entry.missing) throw new Error(t('core.scheduler.scope.targetMissing'))
    let children: Record<string, TaskSelectionNode> = {}
    const available = new Set(entry.users.map(user => user.uid))
    if (
      entry.selection === 'explicit' &&
      (!entry.selected.length || entry.selected.some(uid => !available.has(uid)))
    ) {
      throw new Error(t('core.scheduler.scope.targetMissing'))
    }
    if (
      entry.selection === 'explicit' ||
      entry.users.some(user => user.params && Object.keys(user.params).length)
    ) {
      const selected = new Set(selectedScopeUsers(entry))
      children = indexed(
        entry.users
          .filter(user => selected.has(user.uid))
          .map(user => ({ uid: user.uid, params: user.params }))
      )
    }
    return { uid: entry.uid, params: entry.params, children }
  })
  return {
    mode,
    tasks: indexed([
      draft.kind === 'queue'
        ? { uid: draft.uid, params: draft.params, children: indexed(scripts) }
        : { uid: '-', children: indexed(scripts) },
    ]),
  }
}

/** 配置刷新只更新展示值，保留选择意图及失效 ID，让启动显式报错。 */
export function reconcileScope(fresh: TaskScopeDraft, previous?: TaskScopeDraft): TaskScopeDraft {
  if (!previous || previous.uid !== fresh.uid || previous.kind !== fresh.kind) return fresh
  const choices = new Map(previous.entries.map(entry => [entry.uid, entry]))
  const entries = fresh.entries.map(entry => {
    const old = choices.get(entry.uid)
    if (!old) return previous.selection === 'all' ? entry : { ...entry, selection: 'none' as const }
    if (old.scriptId !== entry.scriptId)
      return previous.selection === 'all' ? entry : { ...old, missing: true }
    return {
      ...entry,
      selection: old.selection,
      selected: [...old.selected],
      params: old.params,
      users: entry.users.map(user => ({
        ...user,
        params: old.users.find(item => item.uid === user.uid)?.params,
      })),
    }
  })
  // 删除了显式选中的队列项，保留失效分支供用户确认，不悄悄扩大范围。
  if (previous.selection !== 'all') {
    for (const old of previous.entries) {
      if (old.selection !== 'none' && !fresh.entries.some(entry => entry.uid === old.uid))
        entries.push({ ...old, missing: true })
    }
  }
  return { ...fresh, selection: previous.selection, params: previous.params, entries }
}

/** 会话存储仅保留本次选择，不复制配置展示或脚本参数。 */
export function persistScope(draft?: TaskScopeDraft): TaskScopeDraft | undefined {
  if (!draft) return undefined
  return {
    ...draft,
    params: {},
    entries: draft.entries.map(entry => ({
      ...entry,
      name: '',
      users: [],
      params: {},
      selected: [...entry.selected],
    })),
  }
}
