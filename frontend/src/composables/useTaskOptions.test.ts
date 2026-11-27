import { afterEach, describe, expect, it, vi } from 'vite-plus/test'

const api = vi.hoisted(() => ({
  queues: vi.fn(),
  scripts: vi.fn(),
  items: vi.fn(),
  users: vi.fn(),
}))
vi.mock('@/api', async importOriginal => {
  const actual = await importOriginal<typeof import('@/api')>()
  return {
    ...actual,
    GetService: {
      getQueuesApiQueueGetPost: api.queues,
      getScriptApiScriptsGetPost: api.scripts,
      getItemApiQueueItemGetPost: api.items,
      getUserApiScriptsUserGetPost: api.users,
    },
  }
})
vi.mock('@/i18n', () => ({ translate: (key: string) => key }))
import { queryClient } from '@/services/queryClient'
import { reconcileScope, scopeRequest } from './taskSelection'
import { fetchTaskScope, fetchTaskTargets, fetchTaskTargetSnapshot } from './useTaskOptions'

const reply = (body: unknown) => Object.assign(Promise.resolve(body), { cancel: vi.fn() })
afterEach(() => {
  queryClient.clear()
  vi.clearAllMocks()
})

describe('任务配置读取', () => {
  it('并发打开主页与桌面分身时复用同一次任务列表查询', async () => {
    api.queues.mockImplementation(() =>
      reply({ code: 200, index: [{ uid: 'q' }], data: { q: { Info: { Name: '脚本 - 同名' } } } })
    )
    api.scripts.mockImplementation(() =>
      reply({ code: 200, index: [{ uid: 's' }], data: { s: { Info: { Name: '队列 - 同名' } } } })
    )
    const [targets, sharedTargets] = await Promise.all([fetchTaskTargets(), fetchTaskTargets()])
    expect(sharedTargets).toEqual(targets)
    expect(api.queues).toHaveBeenCalledTimes(1)
    expect(api.scripts).toHaveBeenCalledTimes(1)
    expect(targets.map(item => [item.value, item.kind])).toEqual([
      ['q', 'queue'],
      ['s', 'script'],
    ])
  })

  it('混合队列跳过暂不可用的托管，保留其他选择，并报出真正失效的引用', async () => {
    api.queues.mockImplementation(() => reply({ code: 200, index: [{ uid: 'q' }], data: {} }))
    api.scripts.mockImplementation(() =>
      reply({
        code: 200,
        index: [{ uid: 'active' }],
        data: { active: { Info: { Name: 'Active' } } },
        unavailable: [
          { uid: 'detached', type: 'MSSConfig', typeLabel: 'MSS', reason: 'plugin_unavailable' },
        ],
      })
    )
    const snapshot = await fetchTaskTargetSnapshot()
    const queue = snapshot.targets[0]
    const items = (other: string) => ({
      code: 200,
      index: [{ uid: 'first' }, { uid: 'second' }],
      data: { first: { Info: { ScriptId: 'active' } }, second: { Info: { ScriptId: other } } },
    })
    api.users.mockImplementation(({ scriptId }) => {
      if (scriptId !== 'active') throw new Error(scriptId)
      return reply({ code: 200, index: [], data: {} })
    })
    api.items.mockResolvedValueOnce(items('detached')).mockResolvedValueOnce(items('missing'))

    const { scope, unavailableItems } = await fetchTaskScope(queue, snapshot)
    expect(scope.entries.map(entry => entry.uid)).toEqual(['first'])
    const previous = {
      ...scope,
      selection: 'explicit' as const,
      entries: [...scope.entries, { ...scope.entries[0], uid: 'second', scriptId: 'detached' }],
    }
    const request = scopeRequest(reconcileScope(scope, previous, unavailableItems))
    expect(request.tasks['0'].children).toEqual({ '0': { uid: 'first', params: {}, children: {} } })
    await expect(fetchTaskScope(queue, snapshot)).rejects.toThrow(
      'core.scheduler.scope.targetMissing'
    )
  })
})
