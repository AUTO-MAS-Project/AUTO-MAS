import { afterEach, beforeEach, describe, expect, it, vi } from 'vite-plus/test'
import { GetService } from '@/api'

vi.mock('vue-router', async importOriginal => {
  const router = await importOriginal<typeof import('vue-router')>()
  return { ...router, createWebHashHistory: router.createMemoryHistory }
})

beforeEach(() => vi.stubGlobal('window', { electronAPI: { getLogger: () => ({ info: vi.fn() }) } }))
afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('应用路由', () => {
  it('保留插件专属设置和游戏管理入口，移除任意插件页面入口', async () => {
    const { default: router } = await import('./index')
    expect(router.resolve('/plugins/demo/settings')).toMatchObject({
      name: 'PluginSettings',
      params: { pluginId: 'demo' },
    })
    expect(router.resolve('/games').name).toBe('Games')
    expect(router.resolve('/emulators').matched).toHaveLength(0)
    expect(router.resolve('/plugins/demo/legacy').matched).toHaveLength(0)
  }, 15000)

  it('按后端当前能力放行插件直达地址', async () => {
    const { default: router } = await import('./index')
    const component = {}
    router.addRoute({ path: '/demo15', component, meta: { skipGuard: true, scriptType: 'Demo15' } })
    router.addRoute({
      path: '/plugins/market',
      name: 'PluginMarket',
      component,
      meta: { skipGuard: true },
    })
    const capabilities = vi.spyOn(GetService, 'getScriptTypesApiScriptsTypesGet')
    capabilities.mockResolvedValue({ code: 200, types: [] })
    await router.push('/demo15')
    expect(router.currentRoute.value.path).toBe('/plugins/market')
    capabilities.mockResolvedValue({ code: 200, types: ['Demo15'] })
    await router.push('/demo15')
    expect(router.currentRoute.value.path).toBe('/demo15')
  })
})
