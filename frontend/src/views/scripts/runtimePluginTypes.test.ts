import { afterEach, describe, expect, it, vi } from 'vite-plus/test'
import { createApp } from 'vue'
import { createMemoryHistory, createRouter, loadRouteLocation, routerKey } from 'vue-router'
import {
  buildScriptEditorRoutes,
  genericEditorRoutes,
  useScriptEditorNavigation,
} from '@/router/scriptEditorRoutes'
import { Service, type PluginRegistryDocument, type ScriptIndexItem } from '@/api'
import { queryClient } from '@/services/queryClient'
import { indexPluginScriptTypes } from '@/utils/pluginScriptTypes'
import { getAvailablePlanTypes, getPlanTypeDescriptor } from '@/utils/planTypeRegistry'
import { projectPlanList } from '../plan/planList'
import { buildCreateRequest, getScriptTypeOptions } from './components/scriptCreateFlow'
import { toScriptListUser } from './scriptListModel'

vi.mock('@/composables/useAudioPlayer', () => ({ useAudioPlayer: () => ({ playSound: vi.fn() }) }))

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
    openEditor('General', 'userAdd', { scriptId: 's' })
    expect(resolve().name).toBe('GeneralUserAdd')
  })

  it('创建 Demo15 后进入新托管，再新增账号时进入返回的账号', async () => {
    vi.stubGlobal('window', { electronAPI: { getLogger: () => ({}) } })
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
    await creation.createUser({ id: 'new-script', type: 'Demo15' })
    await vi.waitFor(() =>
      expect(router.currentRoute.value).toMatchObject({
        name: 'GenericUserEdit',
        params: { scriptId: 'new-script', userId: 'second', scriptType: 'Demo15' },
      })
    )
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
