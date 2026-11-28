// @vitest-environment vue-client
import { afterEach, beforeEach, describe, expect, it, vi } from 'vite-plus/test'
import { defineComponent, h } from 'vue'
import { RouterView } from 'vue-router'
import { testView } from '../../tests/vueRenderer'
import { GetService, Service, PluginState, type PluginProvidedScriptType } from '@/api'
import { PanelBinding } from '@/api/models/PanelBinding'

vi.mock('@/composables/useAudioPlayer', () => ({ useAudioPlayer: () => ({ playSound: vi.fn() }) }))
vi.mock('vue-router', async importOriginal => {
  const router = await importOriginal<typeof import('vue-router')>()
  return { ...router, createWebHashHistory: router.createMemoryHistory }
})

const pluginRecord = (scriptType = 'MAA', surface = PanelBinding.surface.SCRIPT) => ({
  uid: 'record',
  ui: {},
  info: { plugin_name: 'demo', state: PluginState.ENABLED },
  providedScript: {
    scriptKey: scriptType,
    scriptConfigType: 'Script',
    userConfigType: 'User',
    hasPasswordField: false,
    hasAccountField: false,
    supportsGameBinding: false,
    supportsDesktopSession: false,
    blockSurfaces: [] as NonNullable<PluginProvidedScriptType['blockSurfaces']>,
  },
  frontend: {
    diagnostics: [],
    revision: 'rev',
    activationId: 'active',
    pages: { edit: { web: { entry: 'edit.html', panelApi: 1 } } },
    bindings: [{ surface, page: 'edit', scriptType }],
  },
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
    expect(router.resolve('/signflow').name).toBe('SignFlow')
    expect(router.resolve('/gamesign').matched[0]?.redirect).toBe('/signflow')
    expect(router.resolve('/gamesign/activity').matched[0]?.redirect).toEqual({
      path: '/signflow',
      query: { tab: 'activity' },
    })
    expect(router.resolve('/emulators').matched).toHaveLength(0)
    expect(router.resolve('/plugins/demo/legacy').matched).toHaveLength(0)
  }, 15000)

  it('SRC 旧地址进入插件编辑器并保留参数、查询与锚点', async () => {
    const { default: router } = await import('./index')
    vi.spyOn(GetService, 'getScriptTypesApiScriptsTypesGet').mockResolvedValue({
      code: 200,
      types: ['SRC'],
    })
    for (const [oldPath, newPath, name] of [
      ['/scripts/s/edit/src', '/scripts/s/edit/plugin/SRC', 'GenericScriptEdit'],
      ['/scripts/s/users/add/src', '/scripts/s/users/add/plugin/SRC', 'GenericUserAdd'],
      ['/scripts/s/users/u/edit/src', '/scripts/s/users/u/edit/plugin/SRC', 'GenericUserEdit'],
    ] as const) {
      const record = router.getRoutes().find(route => route.name === name)!
      record.meta.skipGuard = true
      try {
        await router.push(`${oldPath}?from=bookmark#section`)
        expect(router.currentRoute.value).toMatchObject({
          name,
          fullPath: `${newPath}?from=bookmark#section`,
          params: {
            scriptId: 's',
            scriptType: 'SRC',
            ...(name === 'GenericUserEdit' && { userId: 'u' }),
          },
        })
      } finally {
        delete record.meta.skipGuard
      }
    }
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
    const record = pluginRecord()
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

  it.each([
    ['script', 'MaaFWScriptEdit', 'GenericScriptEdit'],
    ['setup', 'MaaFWSetupWizard', 'GenericScriptSetup'],
    ['userEdit', 'MaaFWUserEdit', 'GenericUserEdit'],
  ] as const)('已启用的 %s 区块优先于专项静态页', async (page, legacy, generic) => {
    const { default: router } = await import('./index')
    const user = page === 'userEdit'
    const component = { render: () => null }
    router.addRoute({
      path: user ? '/blocks/:scriptId/user/:userId' : '/blocks/:id/' + page,
      name: legacy,
      component,
      meta: { skipGuard: true, maafwPage: page, scriptType: 'MaaFW' },
    })
    router.addRoute({
      path: '/blocks/:scriptType/:scriptId/' + page + (user ? '/:userId' : ''),
      name: generic,
      component,
      meta: { skipGuard: true, scriptPage: page === 'setup' ? 'script' : page },
    })
    const record = pluginRecord('MaaFW')
    record.frontend.bindings = []
    vi.spyOn(Service, 'getPluginRegistryApiPluginRegistryGetPost').mockResolvedValue({
      code: 200,
      data: { record },
    })
    const params = user ? { scriptId: 's', userId: 'u' } : { id: 's' }
    record.providedScript.blockSurfaces = ['plan']
    await router.push({ name: legacy, params })
    expect(router.currentRoute.value.name).toBe(legacy)
    record.providedScript.blockSurfaces = [user ? 'user' : page]
    await router.push({ name: legacy, params, query: { from: legacy } })
    expect(router.currentRoute.value).toMatchObject({
      name: generic,
      params: { scriptType: 'MaaFW', scriptId: 's', ...(user && { userId: 'u' }) },
      query: { from: legacy },
    })
    record.info.state = PluginState.DISABLED
    await router.push({
      name: generic,
      params: router.currentRoute.value.params,
      hash: '#disabled',
    })
    expect(router.currentRoute.value).toMatchObject({ name: legacy, params, hash: '#disabled' })
  })

  it.each(['wheel', 'blocks'] as const)(
    '新增账号在插件接管账号界面时跳过旧页面（%s）',
    async kind => {
      const { default: router } = await import('./index')
      const { genericEditorRoutes } = await import('./scriptEditorRoutes')
      const component = { render: () => null }
      const add = genericEditorRoutes.find(route => route.name === 'GenericUserAdd')!
      router.addRoute({ ...add, meta: { ...add.meta, skipGuard: true } })
      router.addRoute({
        path: '/maa-add/:scriptId',
        name: 'MAAUserAdd',
        component,
        meta: { skipGuard: true, scriptPage: 'userAdd', scriptType: 'MAA' },
      })
      router.addRoute({
        path: '/maa-edit/:scriptId/:scriptType/:userId',
        name: 'GenericUserEdit',
        component,
        meta: { skipGuard: true, scriptPage: 'userEdit' },
      })
      const record = pluginRecord('MAA', PanelBinding.surface.USER)
      if (kind === 'blocks') {
        record.frontend.bindings = []
        record.providedScript.blockSurfaces = ['user']
      }
      vi.spyOn(Service, 'getPluginRegistryApiPluginRegistryGetPost').mockResolvedValue({
        code: 200,
        data: { record },
      })
      const create = vi.spyOn(Service, 'addUserApiScriptsUserAddPost').mockResolvedValue({
        code: 200,
        userId: 'new-user',
        data: {},
      })
      vi.spyOn(GetService, 'getScriptTypesApiScriptsTypesGet').mockResolvedValue({
        code: 200,
        types: ['MAA'],
      })
      const view = testView(defineComponent(() => () => h(RouterView)))
      view.app.use(router)
      view.stub({ ASpin: 'div' })
      view.mount()
      try {
        for (const [state, version] of [
          [PluginState.DISABLED, 1],
          [PluginState.ENABLED, 2],
        ] as const) {
          record.info.state = state
          record.frontend.pages.edit.web.panelApi = version
          if (kind === 'blocks' && state === PluginState.ENABLED)
            record.providedScript.blockSurfaces = ['plan']
          await router.push({
            name: 'MAAUserAdd',
            params: { scriptId: 's' },
            query: { v: version },
          })
          expect(router.currentRoute.value.name).toBe('MAAUserAdd')
          expect(create).not.toHaveBeenCalled()
        }
        record.frontend.pages.edit.web.panelApi = 1
        if (kind === 'blocks') record.providedScript.blockSurfaces = ['user']
        await router.push({ name: 'MAAUserAdd', params: { scriptId: 's' }, hash: '#account' })
        await vi.waitFor(() =>
          expect(router.currentRoute.value).toMatchObject({
            name: 'GenericUserEdit',
            params: { scriptId: 's', scriptType: 'MAA', userId: 'new-user' },
            hash: '#account',
          })
        )
        expect(create).toHaveBeenCalledExactlyOnceWith({ scriptId: 's', firstOnly: undefined })
      } finally {
        view.app.unmount()
      }
    }
  )

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
