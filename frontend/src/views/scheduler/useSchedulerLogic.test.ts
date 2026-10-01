import { describe, expect, it, vi } from 'vitest'
import { Service } from '@/api/services/Service'
import type { SchedulerTab } from './schedulerConstants'

vi.mock('@/api/services/Service', () => ({
  Service: { getUserApiScriptsUserGetPost: vi.fn() },
}))
vi.mock('@/composables/useWebSocket', () => ({ useWebSocket: () => ({}) }))
vi.mock('@/composables/useMaaEndIssueReport', () => ({
  useMaaEndIssueReport: () => ({ exportMaaEndIssueReport: vi.fn() }),
}))
vi.mock('@/i18n', () => ({ translate: (key: string) => key }))

const userResponse = (ids: string[]) => ({
  code: 200,
  index: ids.map(uid => ({ uid, type: 'MaaUserConfig' })),
  data: Object.fromEntries(
    ids.map(uid => [uid, { Info: { Name: uid, Status: true, RemainedDay: 1 } }])
  ),
})

const deferred = <T>() => {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(done => {
    resolve = done
  })
  return { promise, resolve }
}

vi.stubGlobal('window', {
  electronAPI: {
    getLogger: () => ({ info: vi.fn(), warn: vi.fn(), error: vi.fn() }),
  },
  setTimeout,
  clearTimeout,
})
vi.stubGlobal('sessionStorage', {
  getItem: () => null,
  setItem: vi.fn(),
  removeItem: vi.fn(),
})

// 模块初始化会读取 window 和 sessionStorage，必须在设桩后导入。
const { useSchedulerLogic } = await import('./useSchedulerLogic')

describe('loadUserOptions', () => {
  it('只应用最新响应，旧列表不能删除 A+C 子集', async () => {
    const first = deferred<ReturnType<typeof userResponse>>()
    const second = deferred<ReturnType<typeof userResponse>>()
    vi.mocked(Service.getUserApiScriptsUserGetPost)
      .mockReturnValueOnce(first.promise as never)
      .mockReturnValueOnce(second.promise as never)

    const logic = useSchedulerLogic()
    logic.taskOptions.value = [{ label: 'MAA - 官服', value: 'script' }]
    const tab = {
      key: 'race-test',
      selectedTaskId: 'script',
      selectedUserIds: ['a', 'c'],
      userOptions: [],
      userOptionsLoading: false,
      userOptionsLoaded: true,
    } as unknown as SchedulerTab

    const olderLoad = logic.loadUserOptions(tab)
    const newerLoad = logic.loadUserOptions(tab)
    second.resolve(userResponse(['a', 'b', 'c']))
    await newerLoad
    expect(tab.selectedUserIds).toEqual(['a', 'c'])
    expect(tab.userOptionsLoaded).toBe(true)
    expect(tab.userOptionsLoading).toBe(false)

    first.resolve(userResponse(['a']))
    await olderLoad
    expect(tab.selectedUserIds).toEqual(['a', 'c'])
    expect(tab.userOptions?.map(option => option.value)).toEqual(['a', 'b', 'c'])
    expect(tab.userOptionsLoaded).toBe(true)
  })
})
