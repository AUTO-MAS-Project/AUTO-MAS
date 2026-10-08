import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { MyAppearanceItem, ShareCallResult } from '@/composables/useShareApi'

const listMyAppearances = vi.fn<() => Promise<ShareCallResult<MyAppearanceItem[]>>>()
const getMyAppearanceCover =
  vi.fn<(fileId: number, versionNo?: number) => Promise<ShareCallResult<string>>>()
const updateMyAppearanceDescription =
  vi.fn<(fileId: number, description: string) => Promise<ShareCallResult<MyAppearanceItem>>>()

vi.mock('@/composables/useShareApi', () => ({
  useShareApi: () => ({ listMyAppearances, getMyAppearanceCover, updateMyAppearanceDescription }),
}))

vi.stubGlobal('window', {
  electronAPI: {
    getLogger: () => ({ debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() }),
  },
})

const { useMyAppearances } = await import('./useMyAppearances')

const mine = (overrides: Partial<MyAppearanceItem> = {}): MyAppearanceItem => ({
  fileId: 1,
  fileKey: 'sakura',
  displayName: '樱花',
  description: '',
  status: 'active',
  publishedVersionNo: 1,
  latestVersionNo: 2,
  latestReviewStatus: 'pending',
  latestReviewComment: '',
  latestHasCover: true,
  updatedAt: '',
  ...overrides,
})

const flush = () => new Promise(resolve => setTimeout(resolve, 0))

beforeEach(() => {
  listMyAppearances.mockReset()
  getMyAppearanceCover.mockReset()
  updateMyAppearanceDescription.mockReset()
  listMyAppearances.mockResolvedValue({
    ok: true,
    data: [mine(), mine({ fileId: 2, fileKey: 'plain', latestHasCover: false })],
  })
  getMyAppearanceCover.mockImplementation(async fileId => ({
    ok: true,
    data: `data:image/webp;base64,${fileId}`,
  }))
})

describe('useMyAppearances', () => {
  it('loads my themes and the latest covers of those that have one', async () => {
    const store = useMyAppearances()
    await store.load()
    await flush()

    expect(store.items.value.map(item => item.fileId)).toEqual([1, 2])
    expect(store.loaded.value).toBe(true)
    expect(getMyAppearanceCover).toHaveBeenCalledTimes(1)
    expect(getMyAppearanceCover).toHaveBeenCalledWith(1)
    expect(store.coverFor(store.items.value[0])).toBe('data:image/webp;base64,1')
    expect(store.coverFor(store.items.value[1])).toBeUndefined()
    expect(store.findByFileKey('plain')?.fileId).toBe(2)
    expect(store.findById(1)?.fileKey).toBe('sakura')
  })

  it('loads once until reset and shares a request in flight', async () => {
    const store = useMyAppearances()
    await Promise.all([store.ensureLoaded(), store.ensureLoaded()])
    await store.ensureLoaded()
    expect(listMyAppearances).toHaveBeenCalledTimes(1)

    store.reset()
    expect(store.items.value).toEqual([])
    expect(store.coverFor(mine())).toBeUndefined()
    await store.ensureLoaded()
    expect(listMyAppearances).toHaveBeenCalledTimes(2)
  })

  it('reports failures and asks to sign in again on 401', async () => {
    const onUnauthorized = vi.fn()
    const store = useMyAppearances({ onUnauthorized })
    listMyAppearances.mockResolvedValueOnce({ ok: false, code: 401, message: '登录已失效' })
    await store.load()
    expect(store.error.value).toBe('登录已失效')
    expect(store.loaded.value).toBe(false)
    expect(onUnauthorized).toHaveBeenCalledTimes(1)
  })

  it('ignores a list that arrives after reset', async () => {
    let release: (value: ShareCallResult<MyAppearanceItem[]>) => void = () => undefined
    listMyAppearances.mockImplementationOnce(() => new Promise(resolve => (release = resolve)))
    const store = useMyAppearances()
    const loading = store.load()
    store.reset()
    release({ ok: true, data: [mine()] })
    await loading
    expect(store.items.value).toEqual([])
  })

  it('replaces the edited item with what the share site returns', async () => {
    const store = useMyAppearances()
    await store.load()
    updateMyAppearanceDescription.mockResolvedValueOnce({
      ok: true,
      data: mine({ description: '新的简介' }),
    })
    await expect(store.updateDescription(1, '新的简介')).resolves.toEqual({ ok: true })
    expect(updateMyAppearanceDescription).toHaveBeenCalledWith(1, '新的简介')
    expect(store.findById(1)?.description).toBe('新的简介')

    updateMyAppearanceDescription.mockResolvedValueOnce({
      ok: false,
      code: 403,
      message: '没有权限',
    })
    await expect(store.updateDescription(1, 'x')).resolves.toEqual({
      ok: false,
      message: '没有权限',
    })
    expect(store.findById(1)?.description).toBe('新的简介')
  })
})
