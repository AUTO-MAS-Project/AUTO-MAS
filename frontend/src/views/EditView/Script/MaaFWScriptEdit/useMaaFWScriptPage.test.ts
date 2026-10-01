import { effectScope } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

// 调用记录：按发生顺序记下每个后端请求，最后对顺序下断言
const mocks = vi.hoisted(() => {
  const calls: string[] = []
  const logger = { debug: () => {}, info: () => {}, warn: () => {}, error: () => {} }
  ;(globalThis as { window?: unknown }).window = {
    electronAPI: { getLogger: () => logger },
  }
  return {
    calls,
    mounted: [] as Array<() => unknown>,
    beforeUnmount: [] as Array<() => unknown>,
    getScript: vi.fn(),
    updateScript: vi.fn(),
    previewMaaFWInterface: vi.fn(),
    prepareMaaFWAgentEnv: vi.fn(),
    getEmbeddedStatus: vi.fn(),
    reimportEmbedded: vi.fn(),
    getSettings: vi.fn(),
    resolveGamePackage: vi.fn(),
    subscribe: vi.fn(() => 'sub_1'),
    unsubscribe: vi.fn(),
    push: vi.fn(),
    /** 特调准备钩子被调时：已经发生过的请求、flavor 类型、页面 */
    prepareFlavor: [] as Array<{ after: string[]; type: string; part: string }>,
  }
})

vi.mock('@/composables/useMaaFWFlavor', async original => {
  const actual = await original<typeof import('@/composables/useMaaFWFlavor')>()
  return {
    ...actual,
    prepareMaaFWFlavorPage: async (flavor: { type: string }, part: string) => {
      mocks.prepareFlavor.push({ after: [...mocks.calls], type: flavor.type, part })
    },
  }
})

vi.mock('vue', async original => ({
  ...(await original<typeof import('vue')>()),
  onMounted: (hook: () => unknown) => mocks.mounted.push(hook),
  onBeforeUnmount: (hook: () => unknown) => mocks.beforeUnmount.push(hook),
}))
vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (key: string) => key }) }))
vi.mock('@/i18n', () => ({ translate: (key: string) => key }))
vi.mock('vue-router', () => ({
  useRoute: () => ({
    name: 'MaaFWScriptEdit',
    params: { id: 's1' },
    meta: { scriptType: 'MaaFW', maafwPage: 'script' },
  }),
  useRouter: () => ({ push: mocks.push }),
}))
vi.mock('ant-design-vue', () => ({
  message: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))
vi.mock('@/composables/useWebSocket', () => ({
  subscribe: mocks.subscribe,
  unsubscribe: mocks.unsubscribe,
}))
vi.mock('@/composables/useScriptApi', () => ({
  useScriptApi: () => ({
    getScript: mocks.getScript,
    updateScript: mocks.updateScript,
    previewMaaFWInterface: mocks.previewMaaFWInterface,
    prepareMaaFWAgentEnv: mocks.prepareMaaFWAgentEnv,
  }),
}))
vi.mock('@/composables/useMaaFWEmbeddedApi', () => ({
  EMPTY_EMBEDDED_STATUS: { copyPath: '', copyHealthy: false },
  useMaaFWEmbeddedApi: () => ({
    getEmbeddedStatus: mocks.getEmbeddedStatus,
    reimportEmbedded: mocks.reimportEmbedded,
  }),
}))
vi.mock('@/composables/useMaaFWUpdateApi', () => ({
  useMaaFWUpdateApi: () => ({ checkMaaFWUpdate: vi.fn(), applyMaaFWUpdate: vi.fn() }),
}))
vi.mock('@/composables/useMaaFWShellInstanceApi', () => ({
  useMaaFWShellInstanceApi: () => ({ listShellInstances: vi.fn(), importShellInstances: vi.fn() }),
}))
vi.mock('@/api', () => ({
  GetService: { getScriptsApiSettingGetPost: mocks.getSettings },
  MaaFwService: { resolveMaafwGamePackageApiScriptsMaafwGamePackagePost: mocks.resolveGamePackage },
  Service: {
    getEmulatorComboxApiInfoComboxEmulatorPost: async () => {
      mocks.calls.push('emulatorCombox')
      return { code: 200, data: [] }
    },
    getEmulatorApiEmulatorGetPost: async () => {
      mocks.calls.push('emulatorDetail')
      return { code: 200, data: {} }
    },
    getEmulatorDevicesComboxApiInfoComboxEmulatorDevicesPost: vi.fn(),
  },
  Emulator20Service: { listDevicesApiEmulator2DevicesPost: vi.fn() },
}))

import { useMaaFWScriptPage } from './useMaaFWScriptPage'

const preview = {
  path: 'D:/project',
  project: { name: 'demo', label: null, title: '演示项目 v1.2.3', version: '1.2.3' },
  globalOption: [],
  controlCapabilities: { emulatorExtras: {} },
  controllers: [{ name: 'Win', type: 'Win32' }],
  resources: [{ name: 'Official', controller: [] }],
  groups: [],
  settings: [],
  tasks: [{ name: 'Daily', entry: 'Daily', group: [], controller: [], resource: [], option: [] }],
  options: [],
  presets: [],
  importCount: 0,
  agentCount: 0,
}

const mountPage = () => {
  const scope = effectScope()
  const page = scope.run(() => useMaaFWScriptPage({ scriptId: 's1' }))!
  return { scope, page }
}

describe('useMaaFWScriptPage 加载顺序', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.calls.length = 0
    mocks.mounted.length = 0
    mocks.beforeUnmount.length = 0
    mocks.prepareFlavor.length = 0
    mocks.getScript.mockImplementation(async () => {
      mocks.calls.push('getScript')
      return {
        type: 'MaaFW',
        name: '新 MFW 脚本',
        config: {
          Info: { Name: '新 MFW 脚本', Path: 'D:/project', Controller: '', Resource: '' },
          Run: { DailyOnceTasks: '["Daily","Gone"]' },
        },
      }
    })
    mocks.updateScript.mockImplementation(async (_id: string, patch: Record<string, object>) => {
      const [category] = Object.keys(patch)
      const [key] = Object.keys(patch[category])
      mocks.calls.push(`update:${category}.${key}`)
      return true
    })
    mocks.getEmbeddedStatus.mockImplementation(async () => {
      mocks.calls.push('embeddedStatus')
      return { status: { copyPath: 'copy', copyHealthy: true } }
    })
    mocks.previewMaaFWInterface.mockImplementation(async () => {
      mocks.calls.push('preview')
      return { code: 200, data: preview }
    })
    mocks.prepareMaaFWAgentEnv.mockImplementation(async () => {
      mocks.calls.push('prepareEnv')
      return { code: 200, data: { agents: [], logs: [], cached: true } }
    })
    mocks.getSettings.mockImplementation(async () => {
      mocks.calls.push('globalSettings')
      return { code: 200, data: { Update: { MirrorChyanCDK: 'cdk' } } }
    })
    mocks.resolveGamePackage.mockImplementation(async () => {
      mocks.calls.push('gamePackage')
      return { code: 200, data: { reason: 'resolved', package: 'com.demo' } }
    })
  })

  it('onMounted 只挂一个 load；初始化结束之前没有任何 updateScript', async () => {
    const { scope, page } = mountPage()
    expect(mocks.mounted).toHaveLength(1)
    expect(mocks.mounted[0]).toBe(page.load)
    await mocks.mounted[0]()

    const firstUpdate = mocks.calls.findIndex(call => call.startsWith('update:'))
    const lastEmbedded = mocks.calls.lastIndexOf('embeddedStatus')
    // 读 interface 前后各读一次内嵌状态；期间的控制器 / 资源 / 项目名 / 周期任务修剪都只改草稿
    expect(mocks.calls.slice(0, lastEmbedded + 1).filter(call => call !== 'prepareEnv')).toEqual([
      'getScript',
      'emulatorCombox',
      'emulatorDetail',
      'embeddedStatus',
      'preview',
      'embeddedStatus',
    ])
    expect(firstUpdate).toBeGreaterThan(lastEmbedded)
    // 初始化结束后依次：项目名同步 → CDK 预填 → 包名推断
    expect(mocks.calls.slice(firstUpdate).filter(call => call !== 'prepareEnv')).toEqual([
      'update:Info.Name',
      'update:Info.ProjectLabel',
      'globalSettings',
      'update:Update.MirrorChyanCDK',
      'gamePackage',
      'update:Game.PackageName',
    ])
    // 草稿上已经是同步后的值
    expect(page.maafwConfig.Info.Name).toBe('演示项目')
    expect(page.formData.name).toBe('演示项目')
    expect(page.maafwConfig.Info.Controller).toBe('Win')
    expect(page.maafwConfig.Info.Resource).toBe('Official')
    expect(page.dailyOnceTasks.value).toEqual(['Daily'])
    expect(page.pageLoading.value).toBe(false)
    expect(page.cdkPrefilled.value).toBe(true)
    scope.stop()
  })

  it('初始化期间 handleChange 不落盘，结束后照常排队写回', async () => {
    const { scope, page } = mountPage()
    await page.handleChange('Info', 'Name', 'x')
    expect(mocks.updateScript).not.toHaveBeenCalled()
    await page.load()
    mocks.updateScript.mockClear()
    await page.handleChange('Info', 'Notes', 'y')
    expect(mocks.updateScript).toHaveBeenCalledWith('s1', { Info: { Notes: 'y' } })
    scope.stop()
  })

  it('读到脚本详情就（不等地）准备特调脚本页；类型变了再准备一次；插入点上下文跟着页面状态', async () => {
    const { scope, page } = mountPage()
    await page.load()
    // 只在读到详情（与模拟器选项）后调一次，在读内嵌状态等后续请求之前，且不等它
    expect(mocks.prepareFlavor).toEqual([
      {
        after: ['getScript', 'emulatorCombox', 'emulatorDetail'],
        type: 'MaaFW',
        part: 'scriptPage',
      },
    ])
    expect(page.flavorSlotContext.value).toMatchObject({
      scriptId: 's1',
      previewData: preview,
      interfaceDisabled: false,
      loading: false,
      isWizard: false,
    })
    expect(page.flavorSlotContext.value.maafwConfig).toBe(page.maafwConfig)

    // 类型没变：不再准备；导入后换成了特调：准备新特调的脚本页
    await page.refreshScriptType()
    expect(mocks.prepareFlavor).toHaveLength(1)
    mocks.getScript.mockImplementation(async () => ({ type: 'M9A', name: 'x', config: {} }))
    await page.refreshScriptType()
    expect(mocks.prepareFlavor.map(entry => [entry.type, entry.part])).toEqual([
      ['MaaFW', 'scriptPage'],
      ['M9A', 'scriptPage'],
    ])
    scope.stop()
  })

  it('选目录导入：先挂订阅再发请求，导入成功后重新拉脚本类型；作用域销毁时退订', async () => {
    const { scope, page } = mountPage()
    ;(
      globalThis.window as unknown as { electronAPI: Record<string, unknown> }
    ).electronAPI.selectFolder = async () => 'D:/other'
    mocks.subscribe.mockImplementation(() => {
      mocks.calls.push('subscribe')
      return 'sub_1'
    })
    mocks.reimportEmbedded.mockImplementation(async () => {
      mocks.calls.push('reimport')
      return { status: { copyPath: 'copy', copyHealthy: true }, message: '' }
    })
    await page.selectMaaFWPath()
    expect(mocks.calls.slice(0, 3)).toEqual(['subscribe', 'reimport', 'getScript'])
    expect(page.maafwConfig.Info.Path).toBe('D:/other')
    expect(mocks.calls).toContain('preview')
    scope.stop()
    expect(mocks.unsubscribe).toHaveBeenCalledWith('sub_1')
  })
})
