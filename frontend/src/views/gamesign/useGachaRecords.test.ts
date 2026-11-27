import { beforeEach, describe, expect, it, vi } from 'vite-plus/test'

const boundary = vi.hoisted(() => ({
  gachaGames: vi.fn(),
  queryGacha: vi.fn(),
  fetchGacha: vi.fn(),
  warning: vi.fn(),
  success: vi.fn(),
}))

vi.mock('@/services/signflowApi', () => {
  class SignflowError extends Error {
    readonly code: number

    constructor(message: string, code: number) {
      super(message)
      this.code = code
    }
  }

  return { SignflowError, signflowApi: boundary }
})

vi.mock('@/i18n', () => ({ translate: (key: string) => key }))
vi.mock('ant-design-vue', () => ({
  message: { success: boundary.success, warning: boundary.warning },
}))

import { useGachaRecords } from './useGachaRecords'

const deferred = <T>() => {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

const record = (id: string) => ({
  id,
  time: '2026-01-01 12:00:00',
  poolName: '限定寻访',
  name: '号角',
  rarity: 6,
})

/** 让 composable 里 await 过的探测与请求推进到真正发起那一步 */
const flush = () => new Promise(resolve => setTimeout(resolve, 0))

describe('抽卡记录的请求代次', () => {
  beforeEach(() => {
    boundary.gachaGames.mockReset().mockResolvedValue({ code: 200, games: ['arknights'] })
    boundary.queryGacha.mockReset()
    boundary.fetchGacha.mockReset()
    boundary.warning.mockReset()
    boundary.success.mockReset()
  })

  it('连点查询只让最后一次落地', async () => {
    const first = deferred<{ code: number; data: unknown[]; pools: unknown[]; total: number }>()
    const second = deferred<{ code: number; data: unknown[]; pools: unknown[]; total: number }>()
    boundary.queryGacha.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)

    const gacha = useGachaRecords()
    const filter = { game: 'arknights', playerUid: '100', pool: '' }
    const older = gacha.query(filter)
    await flush()
    const newer = gacha.query(filter)
    await flush()

    second.resolve({ code: 200, data: [record('b')], pools: [], total: 1 })
    await newer
    first.resolve({ code: 200, data: [record('a')], pools: [], total: 9 })
    await older

    expect(gacha.records.value.map(item => item.id)).toEqual(['b'])
    expect(gacha.total.value).toBe(1)
  })

  it('读取期间换了角色，结果回来也不再按旧目标补一次查询', async () => {
    const fetching = deferred<{
      code: number
      added: number
      fetched: number
      warnings: string[]
    }>()
    boundary.fetchGacha.mockReturnValueOnce(fetching.promise)

    const gacha = useGachaRecords()
    const target = { game: 'arknights', accountUid: 'account', playerUid: '100' }
    const pending = gacha.fetchRecords(target)
    await flush()

    // 用户在读取返回前换了角色：旧目标的结果不能再落到当前页面
    gacha.reset()
    fetching.resolve({ code: 200, added: 3, fetched: 3, warnings: [] })
    await pending

    expect(boundary.queryGacha).not.toHaveBeenCalled()
    expect(gacha.records.value).toEqual([])
    expect(gacha.fetching.value).toBe(false)
    expect(boundary.success).not.toHaveBeenCalled()
  })

  it('读取成功后按页面当时选中的卡池刷新，不再切回全部卡池', async () => {
    // 读取还在路上时，用户把标签从「限定寻访」切到「标准寻访」
    let selectedPool = '限定寻访'
    boundary.fetchGacha.mockImplementationOnce(async () => {
      selectedPool = '标准寻访'
      return { code: 200, added: 2, fetched: 2, warnings: [] }
    })
    boundary.queryGacha.mockResolvedValueOnce({
      code: 200,
      data: [record('a')],
      pools: [],
      total: 1,
    })

    const gacha = useGachaRecords()
    await gacha.fetchRecords({
      game: 'arknights',
      accountUid: 'account',
      playerUid: '100',
      resolvePool: () => selectedPool,
    })

    expect(boundary.queryGacha).toHaveBeenCalledTimes(1)
    expect(boundary.queryGacha.mock.calls[0][0]).toMatchObject({
      game: 'arknights',
      playerUid: '100',
      pool: '标准寻访',
      page: 1,
    })
  })

  it('切角色时收回旧请求占用的加载态，按钮不会一直转圈', async () => {
    const querying = deferred<{ code: number; data: unknown[]; pools: unknown[]; total: number }>()
    boundary.queryGacha.mockReturnValueOnce(querying.promise)

    const gacha = useGachaRecords()
    const pending = gacha.query({ game: 'arknights', playerUid: '100', pool: '' })
    await flush()
    expect(gacha.querying.value).toBe(true)

    gacha.reset()
    expect(gacha.querying.value).toBe(false)
    expect(gacha.fetching.value).toBe(false)

    querying.resolve({ code: 200, data: [record('a')], pools: [], total: 1 })
    await pending

    expect(gacha.records.value).toEqual([])
    expect(gacha.querying.value).toBe(false)
  })
})
