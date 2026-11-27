import { afterEach, describe, expect, it, vi } from 'vite-plus/test'

vi.mock('vue-router', async importOriginal => {
  const router = await importOriginal<typeof import('vue-router')>()
  return { ...router, createWebHashHistory: router.createMemoryHistory }
})

afterEach(() => vi.unstubAllGlobals())

describe('应用路由', () => {
  it('保留插件专属设置和游戏管理入口，移除任意插件页面入口', async () => {
    vi.stubGlobal('window', { electronAPI: { getLogger: () => ({}) } })
    const { default: router } = await import('./index')
    expect(router.resolve('/plugins/demo/settings')).toMatchObject({
      name: 'PluginSettings',
      params: { pluginId: 'demo' },
    })
    expect(router.resolve('/games').name).toBe('Games')
    expect(router.resolve('/signflow').name).toBe('SignFlow')
    expect(router.resolve('/gamesign').matched[0]?.redirect).toBe('/signflow')
    expect(router.resolve('/gamesign/activity').matched[0]?.redirect).toEqual({
      path: '/signflow',
      query: { tab: 'activity' },
    })
    expect(router.resolve('/emulators').matched).toHaveLength(0)
    expect(router.resolve('/plugins/demo/legacy').matched).toHaveLength(0)
  }, 15000)
})
