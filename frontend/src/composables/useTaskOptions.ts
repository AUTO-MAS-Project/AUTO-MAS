import { GetService, TaskMode, type TaskCreateIn } from '@/api'
import { queryClient } from '@/services/queryClient'
import { queryRequest } from '@/utils/queryRequest'
import { translate as t } from '@/i18n'
import { indexed, targetRequest, type TaskScopeDraft, type TaskScopeEntry } from './taskSelection'

export interface TaskTarget {
  value: string
  label: string
  name: string
  kind: 'queue' | 'script'
}

/** 候选目标只读取配置，不因运行锁而消失；共享同一轮在途查询。 */
export function fetchTaskTargets(): Promise<TaskTarget[]> {
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
      return [
        ...queues.index.map(item => ({
          value: item.uid,
          name: queues.data[item.uid]?.Info?.Name ?? item.uid,
          label: `${t('core.scheduler.scope.queue')} · ${queues.data[item.uid]?.Info?.Name ?? item.uid}`,
          kind: 'queue' as const,
        })),
        ...scripts.index.map(item => ({
          value: item.uid,
          name: scripts.data[item.uid]?.Info?.Name ?? item.uid,
          label: `${t('core.scheduler.scope.script')} · ${scripts.data[item.uid]?.Info?.Name ?? item.uid}`,
          kind: 'script' as const,
        })),
      ]
    },
  })
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
  targets: readonly TaskTarget[]
): Promise<TaskScopeDraft> {
  const scripts = new Map(
    targets.filter(item => item.kind === 'script').map(item => [item.value, item])
  )
  const entries: { uid: string; scriptId: string }[] = []
  if (target.kind === 'queue') {
    const response = await GetService.getItemApiQueueItemGetPost({ queueId: target.value })
    if (response.code !== 200) throw new Error(response.message)
    for (const item of response.index) {
      const scriptId = response.data[item.uid]?.Info?.ScriptId
      if (scriptId && scriptId !== '-') entries.push({ uid: item.uid, scriptId })
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
  return {
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
