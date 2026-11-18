import { afterEach, describe, expect, it, vi } from 'vite-plus/test'

const api = vi.hoisted(() => ({
  queues: vi.fn(),
  scripts: vi.fn(),
}))
vi.mock('@/api', async importOriginal => {
  const actual = await importOriginal<typeof import('@/api')>()
  return {
    ...actual,
    GetService: {
      getQueuesApiQueueGetPost: api.queues,
      getScriptApiScriptsGetPost: api.scripts,
    },
  }
})
vi.mock('@/i18n', () => ({ translate: (key: string) => key }))
import { queryClient } from '@/services/queryClient'
import { fetchTaskTargets } from './useTaskOptions'

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
})
