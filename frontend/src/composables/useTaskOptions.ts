import { GetService, TaskMode, type PowerSignal, type TaskCreateIn } from '@/api'
import { queryClient } from '@/services/queryClient'
import { queryRequest } from '@/utils/queryRequest'
import { translate as t } from '@/i18n'
import { indexed, targetRequest, type TaskScopeDraft, type TaskScopeEntry } from './taskSelection'
import type { ConfigSnapshot } from '@/services/configUiSync'

export interface TaskTarget {
  value: string
  label: string
  name: string
  kind: 'queue' | 'script'
  afterAccomplish?: PowerSignal
}

export interface TaskTargetSnapshot extends ConfigSnapshot {
  targets: TaskTarget[]
  unavailableScriptIds: string[]
  /** 插件暂不可用的托管名称，供只读展示；名称取不到时为 uid。 */
  unavailableScripts?: { uid: string; name: string }[]
}

/** 可选目标和暂不可用的托管来自同一次读取，队列展开时可据此区分停用与失效的引用。 */
export function fetchTaskTargetSnapshot(): Promise<TaskTargetSnapshot> {
  return queryClient.fetchQuery({
    queryKey: ['task-config-targets'],
    staleTime: 0,
    queryFn: async ({ signal }) => {
      const [queues, scripts] = await Promise.all([
        queryRequest(signal, () => GetService.getQueuesApiQueueGetPost({})),
        queryRequest(signal, () => GetService.getScriptApiScriptsGetPost({})),
      ])
      if (queues.code !== 200) throw new Error(queues.message)
      if (scripts.code !== 200) throw new Error(scripts.message)
      const targets = [
        ...queues.index.map(item => ({
          value: item.uid,
          name: queues.data[item.uid]?.Info?.Name ?? item.uid,
          label: `${t('core.scheduler.scope.queue')} · ${queues.data[item.uid]?.Info?.Name ?? item.uid}`,
          kind: 'queue' as const,
          afterAccomplish: queues.data[item.uid]?.Info?.AfterAccomplish ?? undefined,
        })),
        ...scripts.index.map(item => ({
          value: item.uid,
          name: scripts.data[item.uid]?.Info?.Name ?? item.uid,
          label: `${t('core.scheduler.scope.script')} · ${scripts.data[item.uid]?.Info?.Name ?? item.uid}`,
          kind: 'script' as const,
        })),
      ]
      return {
        targets,
        unavailableScriptIds: (scripts.unavailable ?? []).map(item => item.uid),
        unavailableScripts: (scripts.unavailable ?? []).map(item => ({
          uid: item.uid,
          name: item.name || item.uid,
        })),
        uiSources: [...(queues.uiSources ?? []), ...(scripts.uiSources ?? [])],
      }
    },
  })
}

/** 候选目标只读取配置，不因运行锁而消失；共享同一轮在途查询。 */
export async function fetchTaskTargets(
  read?: (snapshot: ConfigSnapshot) => void
): Promise<TaskTarget[]> {
  const snapshot = await fetchTaskTargetSnapshot()
  read?.(snapshot)
  return snapshot.targets
}

export async function configuredTaskRequest(
  uid: string,
  mode = TaskMode.AUTO_PROXY
): Promise<TaskCreateIn> {
  const target = (await fetchTaskTargets()).find(item => item.value === uid)
  if (!target) throw new Error(t('core.scheduler.scope.targetMissing'))
  return targetRequest(target, mode)
}

/** 每个队列项独立展开；重复托管共享用户名单读取，不共享选择状态。 */
export async function fetchTaskScope(
  target: TaskTarget,
  { targets, unavailableScriptIds }: TaskTargetSnapshot
) {
  const scripts = new Map(
    targets.filter(item => item.kind === 'script').map(item => [item.value, item])
  )
  const entries: { uid: string; scriptId: string }[] = []
  const unavailableItems = new Set<string>()
  if (target.kind === 'queue') {
    const response = await GetService.getItemApiQueueItemGetPost({ queueId: target.value })
    if (response.code !== 200) throw new Error(response.message)
    const unavailable = new Set(unavailableScriptIds)
    for (const item of response.index) {
      const scriptId = response.data[item.uid]?.Info?.ScriptId
      if (!scriptId || scriptId === '-') continue
      if (unavailable.has(scriptId)) unavailableItems.add(item.uid)
      else entries.push({ uid: item.uid, scriptId })
    }
  } else entries.push({ uid: target.value, scriptId: target.value })
  const pending = new Map<string, Promise<TaskScopeEntry['users']>>()
  const users = (scriptId: string) => {
    let request = pending.get(scriptId)
    if (!request) {
      request = queryClient.fetchQuery({
        queryKey: ['task-config-users', scriptId],
        staleTime: 0,
        queryFn: async ({ signal }) => {
          const response = await queryRequest(signal, () =>
            GetService.getUserApiScriptsUserGetPost({ scriptId })
          )
          if (response.code !== 200) throw new Error(response.message)
          return response.index.map(item => {
            const info = response.data[item.uid]?.Info
            if (!info) throw new Error(t('core.scheduler.scope.targetMissing'))
            return {
              uid: item.uid,
              name: info.Name || item.uid,
              enabled: info.Status !== false,
              remainedDay: info.RemainedDay ?? -1,
            }
          })
        },
      })
      pending.set(scriptId, request)
    }
    return request
  }
  const scope: TaskScopeDraft = {
    uid: target.value,
    kind: target.kind,
    selection: 'all',
    params: {},
    entries: await Promise.all(
      entries.map(async entry => {
        const script = scripts.get(entry.scriptId)
        if (!script) throw new Error(t('core.scheduler.scope.targetMissing'))
        return {
          ...entry,
          name: script.name,
          selection: 'all' as const,
          selected: [],
          params: {},
          users: await users(entry.scriptId),
        }
      })
    ),
  }
  return { scope, unavailableItems }
}

/** [兼容旧专项] 存量配置按钮只携带目标 UUID；插件入口直接提供托管及用户要求树。 */
export async function configSessionRequest(
  uid: string,
  mode: TaskMode,
  kind: 'queue' | 'script' | 'user' | 'unknown',
  params: NonNullable<TaskCreateIn['tasks']['0']['params']> = {}
): Promise<TaskCreateIn> {
  const targets = await fetchTaskTargets()
  const script = targets.find(item => item.kind === 'script' && item.value === uid)
  if (script && kind !== 'user')
    return { mode, tasks: indexed([{ uid, params, children: indexed([{ uid: 'default' }]) }]) }
  for (const target of targets.filter(item => item.kind === 'script')) {
    const response = await GetService.getUserApiScriptsUserGetPost({ scriptId: target.value })
    if (response.code !== 200) throw new Error(response.message)
    if (response.index.some(item => item.uid === uid)) {
      return { mode, tasks: indexed([{ uid: target.value, params, children: indexed([{ uid }]) }]) }
    }
  }
  throw new Error(t('core.scheduler.scope.targetMissing'))
}
