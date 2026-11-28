// @vitest-environment vue-client
import { afterEach, describe, expect, it, vi } from 'vite-plus/test'
import { createApp } from 'vue'
import { QueryClient } from '@tanstack/vue-query'
import { editorView } from '../../../tests/declarativeEditorView'
import { fire } from '../../../tests/vueRenderer'
import { message } from 'ant-design-vue'
import { createMemoryHistory, createRouter, loadRouteLocation, routerKey } from 'vue-router'
import {
  buildScriptEditorRoutes,
  genericEditorRoutes,
  useScriptEditorNavigation,
} from '@/router/scriptEditorRoutes'
import {
  PluginProvidedScriptType,
  Service,
  type PluginRegistryDocument,
  type ScriptIndexItem,
} from '@/api'
import { maafwRouteName } from '@/router/maafwRoutes'
import { queryClient } from '@/services/queryClient'
import { indexPluginScriptTypes } from '@/utils/pluginScriptTypes'
import { getAvailablePlanTypes, getPlanTypeDescriptor } from '@/utils/planTypeRegistry'
import { projectPlanList } from '../plan/planList'
import { buildCreateRequest, getScriptTypeOptions } from './components/scriptCreateFlow'
import { toScriptListUser } from './scriptListModel'

vi.mock('@/composables/useAudioPlayer', () => ({ useAudioPlayer: () => ({ playSound: vi.fn() }) }))
vi.mock('@/components/GameBindingSection.vue', () => ({ default: { render: () => null } }))

const demo = {
  uid: 'plugin',
  ui: {},
  info: { display_name: 'Demo Runner', description: 'Run a demo' },
  providedScript: {
    scriptKey: 'Demo15',
    scriptConfigType: 'DemoRunnerConfig',
    userConfigType: 'Demo15LoginConfig',
    planConfigType: 'Demo15PlanConfig',
    supportsGameBinding: false,
    supportsDesktopSession: false,
    hasAccountField: true,
    hasPasswordField: false,
  },
} satisfies PluginRegistryDocument
const registry = { demo }
const types = indexPluginScriptTypes(registry)

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  queryClient.clear()
})

describe('运行时专项', () => {
  it('按插件名称创建新类型，保留原始创建标识和备用图标', () => {
    const options = getScriptTypeOptions(['Demo15'], types, key => key)
    expect(options).toEqual([
      expect.objectContaining({
        value: 'Demo15',
        title: 'Demo Runner',
        description: 'Run a demo',
        icon: expect.stringMatching(/.+/),
      }),
    ])
    expect(
      buildCreateRequest({ type: options[0].value, configMode: 'custom', template: null })
    ).toEqual({ kind: 'new', type: 'Demo15' })
    expect(getScriptTypeOptions([], types, key => key)).toEqual([])
  })

  it('未知类型进入通用托管和账号编辑器，已注册的专用入口优先', async () => {
    vi.stubGlobal('window', { electronAPI: { getLogger: () => ({}) } })
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [...buildScriptEditorRoutes(), ...genericEditorRoutes],
    })
    const push = vi.spyOn(router, 'push').mockResolvedValue()
    const openEditor = createApp({})
      .provide(routerKey, router)
      .runWithContext(useScriptEditorNavigation)
    const resolve = () => router.resolve(push.mock.lastCall![0])
    const editor = (await import('@/views/plugins/ConfigEditor.vue')).default
    for (const mode of ['script', 'user'] as const) {
      if (mode === 'script') openEditor('Demo15', mode, { id: 's' })
      else openEditor('Demo15', mode, { scriptId: 's', userId: 'u' })
      const route = resolve()
      expect(router.resolve(route.fullPath).name).toBe(
        mode === 'script' ? 'GenericScriptEdit' : 'GenericUserEdit'
      )
      expect(route.params).toEqual({
        scriptType: 'Demo15',
        scriptId: 's',
        ...(mode === 'user' ? { userId: 'u' } : {}),
      })
      const loaded = await loadRouteLocation(route)
      expect(loaded.matched[0].components?.default).toBe(editor)
      expect(loaded.matched[0].props.default).toEqual({ mode })
    }
    openEditor('General', 'script', { id: 's' })
    expect(router.resolve(resolve().fullPath).name).toBe('GeneralScriptEdit')
    openEditor('General', 'user', { scriptId: 's', userId: 'u' })
    expect(resolve().name).toBe('GeneralUserEdit')
    expect(openEditor('Demo15', 'userAdd', { scriptId: 's' })).toBe(false)
    expect(openEditor('SRC', 'userAdd', { scriptId: 's' })).toBe(true)
    expect(resolve().path).toBe('/scripts/s/users/add/plugin/SRC')
    expect(openEditor('MAA', 'userAdd', { scriptId: 's' })).toBe(true)
    expect(resolve().path).toBe('/scripts/s/users/add/plugin/MAA')
    expect(openEditor('Whimbox', 'userAdd', { scriptId: 's' })).toBe(true)
    expect(resolve().path).toBe('/scripts/s/users/add/plugin/Whimbox')
    expect(openEditor('BetterGI', 'userAdd', { scriptId: 's' })).toBe(true)
    expect(resolve().path).toBe('/scripts/s/users/add/plugin/BetterGI')
    openEditor('General', 'userAdd', { scriptId: 's' })
    expect(resolve().name).toBe('GeneralUserAdd')
  })

  it('创建 Demo15 后进入新托管，再新增账号时进入返回的账号', async () => {
    vi.stubGlobal('window', { electronAPI: { getLogger: () => ({}) } })
    vi.spyOn(Service, 'getPluginRegistryApiPluginRegistryGetPost').mockResolvedValue({
      code: 200,
      data: registry,
    })
    vi.spyOn(Service, 'addScriptApiScriptsAddPost').mockResolvedValue({
      code: 200,
      scriptId: 'new-script',
      data: {},
    })
    vi.spyOn(Service, 'addUserApiScriptsUserAddPost')
      .mockResolvedValueOnce({ code: 200, userId: 'first', data: {} })
      .mockResolvedValueOnce({ code: 200, userId: 'second', data: {} })
    const router = createRouter({ history: createMemoryHistory(), routes: genericEditorRoutes })
    const { useScriptCreation } = await import('./useScriptCreation')
    const creation = createApp({})
      .provide(routerKey, router)
      .runWithContext(() =>
        useScriptCreation({
          reloadScripts: vi.fn(),
          closeDialog: vi.fn(),
          importTemplate: vi.fn(),
          cloneProject: vi.fn(),
        })
      )
    await creation.submit({ kind: 'new', type: 'Demo15' })
    await vi.waitFor(() =>
      expect(router.currentRoute.value).toMatchObject({
        name: 'GenericScriptEdit',
        params: { scriptId: 'new-script', scriptType: 'Demo15' },
      })
    )
    await creation.createUser({ id: 'new-script', type: 'Demo15', users: [], usersLoadError: null })
    await vi.waitFor(() =>
      expect(router.currentRoute.value).toMatchObject({
        name: 'GenericUserEdit',
        params: { scriptId: 'new-script', userId: 'second', scriptType: 'Demo15' },
      })
    )
  })

  it('向导托管只建托管，退出后可由新增首账号重入，MFW 仍走自己的引导', async () => {
    vi.stubGlobal('window', { electronAPI: { getLogger: () => ({ error: vi.fn() }) } })
    const wizard = {
      ...demo,
      providedScript: {
        ...demo.providedScript,
        firstAccountMode: PluginProvidedScriptType.firstAccountMode.WIZARD,
      },
    }
    vi.spyOn(Service, 'getPluginRegistryApiPluginRegistryGetPost').mockResolvedValue({
      code: 200,
      data: { demo: wizard },
    })
    vi.spyOn(Service, 'addScriptApiScriptsAddPost').mockResolvedValue({
      code: 200,
      scriptId: 's',
      data: {},
    })
    const addUser = vi.spyOn(Service, 'addUserApiScriptsUserAddPost')
    const empty = { render: () => null }
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        ...genericEditorRoutes,
        { path: '/scripts', name: 'Scripts', component: empty },
        {
          path: '/scripts/:id/setup/mfw',
          name: maafwRouteName('MaaFW', 'setup'),
          component: empty,
        },
      ],
    })
    const { useScriptCreation } = await import('./useScriptCreation')
    const creation = createApp({})
      .provide(routerKey, router)
      .runWithContext(() =>
        useScriptCreation({
          reloadScripts: vi.fn(),
          closeDialog: vi.fn(),
          importTemplate: vi.fn(),
          cloneProject: vi.fn(),
        })
      )
    await creation.submit({ kind: 'new', type: 'Demo15' })
    await vi.waitFor(() =>
      expect(router.currentRoute.value.fullPath).toBe('/scripts/s/setup/plugin/Demo15')
    )
    await router.push({ name: 'Scripts' })
    await creation.createUser({ id: 's', type: 'Demo15', users: [], usersLoadError: null })
    await vi.waitFor(() => expect(router.currentRoute.value.name).toBe('GenericScriptSetup'))
    await creation.submit({ kind: 'new', type: 'MaaFW' })
    await vi.waitFor(() =>
      expect(router.currentRoute.value.name).toBe(maafwRouteName('MaaFW', 'setup'))
    )
    expect(addUser).not.toHaveBeenCalled()
  })

  it.each([
    { mode: 'setup', dirty: true },
    { mode: 'setup', dirty: false },
    { mode: 'script', dirty: true },
    { mode: 'cancel', dirty: false },
  ] as const)('$mode 编辑在 dirty=$dirty 时仅在向导完成后创建首账号', async ({ mode, dirty }) => {
    vi.spyOn(message, 'success').mockImplementation(vi.fn())
    vi.spyOn(message, 'error').mockImplementation(vi.fn())
    vi.stubGlobal('window', { electronAPI: { getLogger: () => ({ error: vi.fn() }) } })
    const settings: Record<string, Record<string, unknown>> = { Setup: { Name: 'initial' } }
    const state = {
      code: 200,
      data: { s: settings },
      index: [],
      ui: {
        configUid: 'uid',
        hints: { Setup: [{ field: 'Name' }], Run: [{ field: 'Count' }] },
        tables: [],
        steps: [{ key: 'setup' }, { key: 'run' }],
        sections: { 'group:Run': { step: 'run' } },
      },
    }
    vi.spyOn(Service, 'getScriptApiScriptsGetPost').mockResolvedValue(state)
    vi.spyOn(Service, 'getScriptLockApiScriptsLockPost').mockResolvedValue({
      code: 200,
      locked: false,
    })
    vi.spyOn(Service, 'getUserApiScriptsUserGetPost').mockResolvedValue({
      code: 200,
      index: [],
      data: { first: {} },
    })
    vi.spyOn(Service, 'getActiveConfigTriggersApiConfigTriggersActiveGet').mockResolvedValue({
      code: 200,
      data: [],
    })
    const write = vi
      .spyOn(Service, 'updateScriptApiScriptsUpdatePost')
      .mockResolvedValueOnce({
        code: 422,
        fieldErrors: { 'Setup.Name': 'invalid' },
      })
      .mockResolvedValue({ code: 200 })
    const create = vi
      .spyOn(Service, 'addUserApiScriptsUserAddPost')
      .mockResolvedValue({ code: 200, userId: 'first', data: {} })
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const view = await editorView(
      `/scripts/s/${mode === 'script' ? 'edit' : 'setup'}/plugin/Demo15`,
      client
    )
    view.mount()
    try {
      await vi.waitFor(() => expect(view.find('input')?.props.value).toBe('initial'))
      if (mode === 'cancel') {
        await view.click('core.comp.back')
        await vi.waitFor(() => expect(view.router.currentRoute.value.name).toBe('Scripts'))
        expect(write).not.toHaveBeenCalled()
        expect(create).not.toHaveBeenCalled()
        return
      }
      if (dirty) {
        await fire(view.find('input')!, 'onUpdate:value', 'invalid')
        await view.click('core.edit.next')
        await view.click('core.taskboard.complete')
        await vi.waitFor(() => expect(view.find('p', 'invalid')?.props.role).toBe('alert'))
        expect(view.find('steps')?.props.current).toBe(0)
        expect(create).not.toHaveBeenCalled()
        await fire(view.find('input')!, 'onUpdate:value', 'valid')
      }
      await view.click('core.edit.next')
      expect(view.find('button', 'core.taskboard.complete')!.props.disabled).toBe(false)
      await view.click('core.taskboard.complete')
      if (dirty)
        expect(write).toHaveBeenLastCalledWith({
          scriptId: 's',
          data: { Setup: { Name: 'valid' } },
        })
      else expect(write).not.toHaveBeenCalled()
      if (mode === 'script') {
        await vi.waitFor(() =>
          expect(view.find('button', 'core.taskboard.complete')!.props.loading).toBe(false)
        )
        expect(view.router.currentRoute.value.name).toBe('GenericScriptEdit')
        expect(create).not.toHaveBeenCalled()
        return
      }
      await vi.waitFor(() =>
        expect(view.router.currentRoute.value.fullPath).toBe(
          '/scripts/s/users/first/edit/plugin/Demo15'
        )
      )
      expect(create.mock.calls).toEqual([[{ scriptId: 's', firstOnly: true }]])
    } finally {
      view.app.unmount()
      client.clear()
    }
  })

  it('列表和详情按注册表解析脚本配置类名', async () => {
    vi.stubGlobal('window', { electronAPI: { getLogger: () => ({}) } })
    vi.spyOn(Service, 'getPluginRegistryApiPluginRegistryGetPost').mockResolvedValue({
      code: 200,
      data: registry,
    })
    vi.spyOn(Service, 'getScriptApiScriptsGetPost').mockResolvedValue({
      code: 200,
      index: [{ uid: 's', type: 'DemoRunnerConfig' as ScriptIndexItem['type'] }],
      data: { s: { Info: { Name: 'Demo task' } } },
    })
    const { useScriptApi } = await import('@/composables/useScriptApi')
    const api = useScriptApi()
    const expected = { uid: 's', type: 'Demo15', scriptConfigType: 'DemoRunnerConfig' }
    expect(await api.getScripts()).toMatchObject([expected])
    expect(await api.getScript('s')).toMatchObject(expected)
  })

  it.each([
    [true, false],
    [false, true],
  ])('按声明独立投影账号 %s 和密码 %s', (hasAccountField, hasPasswordField) => {
    const plugins = indexPluginScriptTypes({
      demo: {
        ...demo,
        providedScript: { ...demo.providedScript, hasAccountField, hasPasswordField },
      },
    })
    const index = { uid: 'u', type: 'Demo15LoginConfig' }
    const user = toScriptListUser(
      's',
      index,
      { Info: { Id: 'login', Password: 'example' } },
      plugins.byUserConfigType.get(index.type)
    )
    expect(user).toMatchObject({
      id: 'u',
      scriptId: 's',
      showAccount: hasAccountField,
      Info: {
        Id: hasAccountField ? 'login' : undefined,
        Password: hasPasswordField ? 'example' : undefined,
      },
    })
  })

  it('没有专用表格的计划可列出和创建，停用后退出新建菜单', () => {
    const configType = 'Demo15PlanConfig'
    const data: Record<string, Record<string, unknown>> = { p: { info: { name: 'Nightly' } } }
    const { nextPlanList } = projectPlanList(
      {
        index: [{ uid: 'p', type: configType }],
        data,
      },
      types,
      message => {
        throw new Error(message)
      }
    )
    expect(nextPlanList).toEqual([
      { id: 'p', type: configType, typeLabel: 'Demo Runner', name: 'Nightly' },
    ])
    expect(getPlanTypeDescriptor(configType)).toBeNull()
    expect(getAvailablePlanTypes(['Demo15'], types)).toContainEqual(
      expect.objectContaining({
        configType,
        createType: configType,
        displayName: 'Demo Runner',
      })
    )
    expect(getAvailablePlanTypes([], types).map(option => option.configType)).not.toContain(
      configType
    )
  })
})
