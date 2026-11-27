import { afterEach, describe, expect, it, vi } from 'vite-plus/test'
import { Service, type PluginRegistryDocument, type ScriptIndexItem } from '@/api'
import { queryClient } from '@/services/queryClient'
import { indexPluginScriptTypes } from '@/utils/pluginScriptTypes'
import { getAvailablePlanTypes, getPlanTypeDescriptor } from '@/utils/planTypeRegistry'
import { projectPlanList } from '../plan/planList'
import { buildCreateRequest, getScriptTypeOptions } from './components/scriptCreateFlow'
import { toScriptListUser } from './scriptListModel'

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
    const { nextPlanList } = projectPlanList(
      {
        index: [{ uid: 'p', type: configType }],
        data: { p: { Info: { Name: 'Nightly' } } },
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
