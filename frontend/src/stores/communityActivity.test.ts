import { createPinia, disposePinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vite-plus/test'
import { SignflowError } from '@/services/signflowApi'
import { useCommunityActivityStore } from './communityActivity'

const boundary = vi.hoisted(() => ({ queryActivity: vi.fn() }))

vi.mock('@/views/gamesign/useCommunityActivityApi', () => ({
  useCommunityActivityApi: () => ({ queryActivity: boundary.queryActivity }),
}))

// 每个用例一套全新的 pinia：dispose 过的实例不能再建 store（会抛 Pinia destroyed）
let pinia = createPinia()

afterEach(() => disposePinia(pinia))

beforeEach(() => {
  pinia = createPinia()
  setActivePinia(pinia)
  boundary.queryActivity.mockReset()
})

describe('便笺插件缺失信号', () => {
  it('插件未启用时单独标记，文案仍然保留给刷新按钮以外的提示', async () => {
    boundary.queryActivity.mockRejectedValueOnce(new SignflowError('日常便笺插件未启用', 400, 503))

    const store = useCommunityActivityStore()
    await store.load()

    expect(store.pluginMissing).toBe(true)
    expect(store.errorMessage).toBe('日常便笺插件未启用')
    expect(store.hasLoaded).toBe(false)
  })

  it('普通失败不落到插件缺失上，避免把网络问题引导成装插件', async () => {
    boundary.queryActivity.mockRejectedValueOnce(new Error('网络不可用'))

    const store = useCommunityActivityStore()
    await store.load()

    expect(store.pluginMissing).toBe(false)
    expect(store.errorMessage).toBe('网络不可用')
  })

  it('重试成功后清掉插件缺失标记', async () => {
    boundary.queryActivity.mockRejectedValueOnce(new SignflowError('日常便笺插件未启用', 400))
    const store = useCommunityActivityStore()
    await store.load()

    boundary.queryActivity.mockResolvedValueOnce([])
    await store.load()

    expect(store.pluginMissing).toBe(false)
    expect(store.errorMessage).toBe('')
  })
})
