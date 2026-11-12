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
import { fetchTaskScope, fetchTaskTargets } from './useTaskOptions'

const reply = (body: unknown) => Object.assign(Promise.resolve(body), { cancel: vi.fn() })
afterEach(() => {
  queryClient.clear()
  vi.clearAllMocks()
})

describe('任务配置读取', () => {
  it('从队列与托管配置取得显式类型，不根据名称前缀判断', async () => {
    api.queues.mockImplementation(() =>
      reply({ code: 200, index: [{ uid: 'q' }], data: { q: { Info: { Name: '脚本 - 同名' } } } })
    )
    api.scripts.mockImplementation(() =>
      reply({ code: 200, index: [{ uid: 's' }], data: { s: { Info: { Name: '队列 - 同名' } } } })
    )
    const targets = await fetchTaskTargets()
    expect(targets.map(item => [item.value, item.kind])).toEqual([
      ['q', 'queue'],
      ['s', 'script'],
    ])
  })
  it('重复队列项分别保留，用户名单只读取一次且保留禁用和天数不足的用户', async () => {
    api.items.mockImplementation(() =>
      reply({
        code: 200,
        index: [{ uid: 'first' }, { uid: 'second' }],
        data: { first: { Info: { ScriptId: 's' } }, second: { Info: { ScriptId: 's' } } },
      })
    )
    api.users.mockImplementation(() =>
      reply({
        code: 200,
        index: [{ uid: 'u' }],
        data: { u: { Info: { Name: 'user', Status: false, RemainedDay: 0 } } },
      })
    )
    const target = { kind: 'queue' as const, value: 'q', name: 'queue', label: 'queue' }
    const scope = await fetchTaskScope(target, [
      { kind: 'script', value: 's', name: 'script', label: 'script' },
    ])
    expect(scope.entries.map(item => item.uid)).toEqual(['first', 'second'])
    expect(api.users).toHaveBeenCalledTimes(1)
    expect(scope.entries[0].users).toEqual([
      { uid: 'u', name: 'user', enabled: false, remainedDay: 0 },
    ])
    scope.entries[0].selected.push('u')
    expect(scope.entries[1].selected).toEqual([])
  })
  it('配置查询失败抛出原业务失败，不能伪装成成功的空列表', async () => {
    api.queues.mockImplementation(() => reply({ code: 503, message: 'unavailable' }))
    api.scripts.mockImplementation(() => reply({ code: 200, index: [], data: {} }))
    await expect(fetchTaskTargets()).rejects.toThrow('unavailable')
  })
})
