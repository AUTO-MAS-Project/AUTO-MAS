/**
 * 插件市场快照启动预热契约：
 * - 由 appEntry 在进入应用后 fire-and-forget 调用，绝不抛错（失败静默）；
 * - 已有缓存或 WebSocket 未连接时跳过，不打网络；
 * - 成功后写入 sessionStorage 缓存，市场页挂载时直接命中；
 * - 单飞行：一次应用会话只预热一次。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const wsMocks = vi.hoisted(() => ({
  request: vi.fn(),
  state: { value: 'open' },
}))

vi.mock('@/composables/useWebSocket', () => ({
  useWebSocket: () => ({
    request: wsMocks.request,
    state: wsMocks.state,
  }),
}))

const storage = new Map<string, string>()
const sessionStorageStub = {
  getItem: (key: string) => storage.get(key) ?? null,
  setItem: (key: string, value: string) => storage.set(key, value),
  removeItem: (key: string) => storage.delete(key),
  clear: () => storage.clear(),
}

const CACHE_KEY = 'auto-mas-plugin-market-cache-v1'

const snapshotPayload = {
  schema_version: 1,
  prefix_tags: ['automas_'],
  fetched_at: '2026-07-26T00:00:00Z',
  items: [
    {
      package: 'automas_demo',
      version: '1.0.0',
      summary: 'demo',
      project_url: '',
      prefix_tag: 'automas_',
    },
  ],
  installed_map: { automas_demo: false },
  total: 1,
}

const importPrewarm = async () => {
  vi.resetModules()
  return await import('./marketPrewarm')
}

describe('plugin market snapshot prewarm', () => {
  beforeEach(() => {
    storage.clear()
    wsMocks.state.value = 'open'
    wsMocks.request.mockReset().mockResolvedValue({
      type: 'market.snapshot.response',
      data: { payload: snapshotPayload },
    })
    vi.stubGlobal('sessionStorage', sessionStorageStub)
    vi.stubGlobal('window', {
      electronAPI: {
        getLogger: () => ({
          debug: vi.fn(),
          info: vi.fn(),
          warn: vi.fn(),
          error: vi.fn(),
        }),
      },
    })
  })

  it('连接可用且无缓存时拉取快照并写入缓存', async () => {
    const { prewarmPluginMarketSnapshot } = await importPrewarm()
    await prewarmPluginMarketSnapshot()

    expect(wsMocks.request).toHaveBeenCalledWith(
      'PluginMarket',
      'market.snapshot.request',
      ['market.snapshot.response', 'market.error'],
      { perPrefixLimit: 60 },
      15000
    )
    const cached = JSON.parse(storage.get(CACHE_KEY) || 'null')
    expect(cached?.snapshot?.total).toBe(1)
    expect(cached?.snapshot?.items?.[0]?.package).toBe('automas_demo')
  })

  it('已有缓存时跳过预热，不发起请求', async () => {
    storage.set(
      CACHE_KEY,
      JSON.stringify({ snapshot: snapshotPayload, saved_at: '2026-07-26T00:01:00Z' })
    )
    const { prewarmPluginMarketSnapshot } = await importPrewarm()
    await prewarmPluginMarketSnapshot()

    expect(wsMocks.request).not.toHaveBeenCalled()
  })

  it('WebSocket 未连接时静默跳过（由市场页兜底请求）', async () => {
    wsMocks.state.value = 'closed'
    const { prewarmPluginMarketSnapshot } = await importPrewarm()
    await expect(prewarmPluginMarketSnapshot()).resolves.toBeUndefined()

    expect(wsMocks.request).not.toHaveBeenCalled()
    expect(storage.has(CACHE_KEY)).toBe(false)
  })

  it('请求失败时静默吞掉异常且不写缓存', async () => {
    wsMocks.request.mockRejectedValue(new Error('请求超时'))
    const { prewarmPluginMarketSnapshot } = await importPrewarm()
    await expect(prewarmPluginMarketSnapshot()).resolves.toBeUndefined()

    expect(storage.has(CACHE_KEY)).toBe(false)
  })

  it('市场返回错误时不写缓存', async () => {
    wsMocks.request.mockResolvedValue({
      type: 'market.error',
      data: { message: '快照构建失败' },
    })
    const { prewarmPluginMarketSnapshot } = await importPrewarm()
    await expect(prewarmPluginMarketSnapshot()).resolves.toBeUndefined()

    expect(storage.has(CACHE_KEY)).toBe(false)
  })

  it('单飞行：一次会话内重复调用只预热一次', async () => {
    const { prewarmPluginMarketSnapshot } = await importPrewarm()
    await Promise.all([prewarmPluginMarketSnapshot(), prewarmPluginMarketSnapshot()])
    await prewarmPluginMarketSnapshot()

    expect(wsMocks.request).toHaveBeenCalledTimes(1)
  })
})
