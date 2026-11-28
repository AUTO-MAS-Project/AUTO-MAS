import { afterEach, beforeEach, describe, expect, it, vi } from 'vite-plus/test'
import { GetService, Service, PluginState } from '@/api'
import { PanelBinding } from '@/api/models/PanelBinding'

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

  it('按绑定与启用状态选择静态编辑器或插件面板，保留直达地址参数', async () => {
    const { default: router } = await import('./index')
    const component = {}
    router.addRoute({
      path: '/probe/:id',
      name: 'MAAScriptEdit',
      component,
      meta: { skipGuard: true, scriptType: 'MAA', scriptPage: 'script' },
    })
    router.addRoute({
      path: '/probe/:scriptType/:scriptId',
      name: 'GenericScriptEdit',
      component,
      meta: { skipGuard: true, scriptPage: 'script' },
    })
    const record = {
      uid: 'record',
      ui: {},
      info: { plugin_name: 'demo', state: PluginState.ENABLED },
      providedScript: {
        scriptKey: 'MAA',
        scriptConfigType: 'Script',
        userConfigType: 'User',
        hasPasswordField: false,
        hasAccountField: false,
        supportsGameBinding: false,
        supportsDesktopSession: false,
      },
      frontend: {
        diagnostics: [],
        revision: 'rev',
        activationId: 'active',
        pages: { edit: { web: { entry: 'edit.html', panelApi: 1 } } },
        bindings: [{ surface: PanelBinding.surface.SCRIPT, page: 'edit', scriptType: 'MAA' }],
      },
    }
    vi.spyOn(Service, 'getPluginRegistryApiPluginRegistryGetPost').mockResolvedValue({
      code: 200,
      data: { record },
    })
    for (const [state, version, name] of [
      [PluginState.DISABLED, 1, 'MAAScriptEdit'],
      [PluginState.ENABLED, 2, 'MAAScriptEdit'],
      [PluginState.ENABLED, 1, 'GenericScriptEdit'],
    ] as const) {
      record.info.state = state
      record.frontend.pages.edit.web.panelApi = version
      await router.push(`/probe/id?v=${state}${version}#here`)
      expect(router.currentRoute.value).toMatchObject({
        name,
        hash: '#here',
        query: { v: `${state}${version}` },
      })
    }
    record.info.state = PluginState.DISABLED
    await router.push('/probe/MAA/id?v=refresh')
    expect(router.currentRoute.value).toMatchObject({
      name: 'MAAScriptEdit',
      params: { id: 'id' },
    })
  })

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
