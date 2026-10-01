import { afterEach, describe, expect, it, vi } from 'vitest'
import { createSSRApp, defineComponent, h, reactive, shallowRef, type Component } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { createI18n } from 'vue-i18n'
import zhCN from '@/i18n/locales/zh-CN'
import {
  defineMaaFWSection,
  type MaaFWFlavor,
  type MaaFWFlavorPart,
  type MaaFWSection,
  type MaaFWSectionKey,
} from '@/composables/maafwFlavorTypes'
import { resolveMaaFWFlavor } from '@/composables/useMaaFWFlavor'

// 渲染真实的两个页面模板（编排层换成假的状态），验证分节替换走的是页面里那几个
// <component :is>：默认分节、替换分节收到的属性与监听完全相同。仓库没有 DOM 环境，用 SSR。

const mocks = vi.hoisted(() => {
  const logger = { debug: () => {}, info: () => {}, warn: () => {}, error: () => {} }
  ;(globalThis as { window?: unknown }).window = { electronAPI: { getLogger: () => logger } }
  /** 每个分节 stub 收到的全部属性与监听（不声明 props，全落在 attrs 上），按渲染者分开记 */
  const received = new Map<string, Record<string, unknown>>()
  // vi.mock 的工厂比本文件的 import 先跑，vue 由调用方传进来
  const recordingStub = (vue: typeof import('vue'), name: string) =>
    vue.defineComponent({
      name,
      inheritAttrs: false,
      setup(_props, { attrs }) {
        received.set(name, { ...attrs })
        return () => vue.h('section', { 'data-section': name })
      },
    })
  return {
    received,
    recordingStub,
    script: null as Record<string, unknown> | null,
    user: null as Record<string, unknown> | null,
  }
})
const { received } = mocks
const recordingStub = (name: string) => mocks.recordingStub({ defineComponent, h } as never, name)

/** 测试里的替换分节 stub 不声明契约 props，绕开 defineMaaFWSection 的类型检查（运行时同一个函数） */
const fakeSection = <P extends MaaFWFlavorPart, K extends MaaFWSectionKey<P>>(
  part: P,
  key: K,
  load: () => Promise<Component>
) =>
  (
    defineMaaFWSection as unknown as (
      part: P,
      key: K,
      load: () => Promise<Component>
    ) => MaaFWSection<P, K>
  )(part, key, load)

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { id: 's1', scriptId: 's1', userId: 'u1' } }),
}))
vi.mock('@ant-design/icons-vue', () => ({
  ArrowLeftOutlined: { render: () => null },
  HistoryOutlined: { render: () => null },
}))
vi.mock('@/components/ConfigLockPanel.vue', () => ({
  default: {
    setup:
      (_: unknown, { slots }: { slots: Record<string, () => unknown> }) =>
      () =>
        slots.default?.(),
  },
}))
vi.mock('@/components/DocLink.vue', () => ({ default: { render: () => null } }))
vi.mock('@/components/ExtraScriptSection.vue', () => ({ default: { render: () => null } }))
vi.mock('@/components/UserNotifyConfig.vue', () => ({ default: { render: () => null } }))
vi.mock('@/views/EditView/User/components/ConfigRestoreSection.vue', () => ({
  default: { render: () => null },
}))
vi.mock('../Script/MaaFWScriptEdit/useMaaFWScriptPage', () => ({
  useMaaFWScriptPage: () => mocks.script,
}))
vi.mock('../User/MaaFWUserEdit/useMaaFWUserPage', () => ({
  useMaaFWUserPage: () => mocks.user,
}))
// MFW 默认分节换成会记录入参的 stub
vi.mock('../Script/MaaFWScriptEdit/BasicInfoSection.vue', async () => ({
  default: mocks.recordingStub(await import('vue'), 'default:basicInfo'),
}))
vi.mock('../Script/MaaFWScriptEdit/ControlConfigSection.vue', async () => ({
  default: mocks.recordingStub(await import('vue'), 'default:control'),
}))
vi.mock('../Script/MaaFWScriptEdit/UpdateSettingsSection.vue', async () => ({
  default: mocks.recordingStub(await import('vue'), 'default:update'),
}))
vi.mock('../Script/MaaFWScriptEdit/RunConfigSection.vue', async () => ({
  default: mocks.recordingStub(await import('vue'), 'default:run'),
}))
vi.mock('../Script/MaaFWScriptEdit/ShellInstanceImportSection.vue', async () => ({
  default: mocks.recordingStub(await import('vue'), 'default:shellImport'),
}))
vi.mock('../User/MaaFWUserEdit/MaaFWUserEditHeader.vue', async () => ({
  default: mocks.recordingStub(await import('vue'), 'default:header'),
}))
vi.mock('../User/MaaFWUserEdit/BasicInfoSection.vue', async () => ({
  default: mocks.recordingStub(await import('vue'), 'default:userBasicInfo'),
}))
vi.mock('../User/MaaFWUserEdit/TaskQueueSection.vue', async () => ({
  default: mocks.recordingStub(await import('vue'), 'default:taskQueue'),
}))

import MaaFWScriptEdit from '../Script/MaaFWScriptEdit.vue'
import MaaFWUserEdit from '../User/MaaFWUserEdit.vue'

const i18n = createI18n({
  legacy: false,
  locale: 'zh-CN',
  fallbackLocale: 'zh-CN',
  missingWarn: false,
  fallbackWarn: false,
  messages: { 'zh-CN': zhCN },
})

/** antd 组件一律换成只渲染插槽的壳 */
const shell = (name: string) =>
  defineComponent({
    name,
    inheritAttrs: false,
    setup(_props, { slots }) {
      return () =>
        h(
          'div',
          { class: name },
          Object.values(slots).map(slot => slot?.())
        )
    },
  })
const SHELLS = [
  'ABreadcrumb',
  'ABreadcrumbItem',
  'ASpace',
  'AButton',
  'ACard',
  'ASteps',
  'AForm',
  'AAlert',
  'ATag',
  'AFlex',
  'RouterLink',
]

const fn = (name: string) => Object.assign(() => undefined, { displayName: name })

const scriptState = (flavor: MaaFWFlavor) => ({
  pageLoading: false,
  previewLoading: false,
  previewData: { tasks: [] },
  maafwConfig: reactive({ Info: { Name: 'n' } }),
  formData: reactive({ type: flavor.type, name: 'n', path: 'p' }),
  rules: { name: [], path: [] },
  handleChange: fn('handleChange'),
  flavor: shallowRef(flavor),
  emulatorLoading: false,
  emulatorOptionsReady: true,
  emulatorDeviceLoading: false,
  emulatorOptions: [],
  emulatorDeviceOptions: [],
  emulatorTypeById: {},
  controllerOptions: [],
  effectiveControllerName: 'Win',
  effectiveControllerType: 'Win32',
  isAdbController: false,
  isDesktopController: true,
  resourceOptions: [],
  interfaceDependentDisabled: false,
  selectedEmulatorLabel: '',
  adbControlStrategyItems: [],
  handleControllerChange: fn('handleControllerChange'),
  handleResourceChangeWithPackage: fn('handleResourceChangeWithPackage'),
  handleEmulatorSelectChange: fn('handleEmulatorSelectChange'),
  selectLaunchPath: fn('selectLaunchPath'),
  dailyOnceTasks: [],
  weeklyOnceTasks: [],
  monthlyOnceTasks: [],
  periodTaskOptions: [],
  handlePeriodTaskChange: fn('handlePeriodTaskChange'),
  envPreparing: false,
  envReady: true,
  envFailed: false,
  envMessage: '',
  envPercent: null,
  envLogs: [],
  envAgents: [],
  envOutcome: null,
  embeddedStatus: { copyPath: '', copyHealthy: true },
  embeddedBusy: false,
  importPercent: null,
  importMessage: '',
  selectMaaFWPath: fn('selectMaaFWPath'),
  isAutoUpdateDisabled: false,
  updateChecking: false,
  updateApplying: false,
  updateError: '',
  updateResult: null,
  updateProgress: { phase: 'idle' },
  runUpdateCheck: fn('runUpdateCheck'),
  runUpdateApply: fn('runUpdateApply'),
  cdkPrefilled: false,
  // 引导最后一步：外壳导入分节也渲染出来
  isWizard: true,
  currentStep: 3,
  stepItems: [{}, {}, {}, {}],
  canLeaveCurrentStep: true,
  shellInstances: [{ id: 'i1' }],
  selectedShellInstanceIds: [],
  shellImporting: false,
  finishButtonLabel: '完成',
  handleFinishWizard: fn('handleFinishWizard'),
  previewProjectTitle: '演示',
  typeTagLabel: flavor.typeTagLabel,
  pageTitle: '演示 项目引导',
  interfaceStats: [],
  handlePreviewInterface: fn('handlePreviewInterface'),
  handleCancel: fn('handleCancel'),
})

const userState = (flavor: MaaFWFlavor) => ({
  loading: false,
  saveStatus: 'idle',
  saveErrorMessage: '',
  userIdHolder: { value: 'u1' },
  isEdit: true,
  configLocked: false,
  scriptName: '演示',
  flavor: shallowRef(flavor),
  previewData: { tasks: [] },
  interfaceLoading: false,
  projectIconUrl: '',
  handleProjectIconError: fn('handleProjectIconError'),
  taskSnapshot: { taskOrder: [], taskChecked: {}, taskOptions: {} },
  formData: reactive({ userName: '', Info: { Name: '' }, Task: {}, Notify: {}, Data: {} }),
  rules: {},
  queueHintLines: [],
  accountRecordTooltip: '提示',
  managedQueueAlert: null,
  flavorSlotContext: { formData: {}, loading: false, queuedTaskCount: 0 },
  taskByName: new Map(),
  effectiveControllerName: 'Win',
  effectiveResourceName: 'Official',
  interfaceDependentDisabled: false,
  handleFieldSave: fn('handleFieldSave'),
  showPresetModal: false,
  orderedTasks: [],
  availableTasks: [],
  presetTemplates: [],
  selectedQueuedTask: null,
  selectedTask: null,
  applyQueuedTaskIds: fn('applyQueuedTaskIds'),
  selectTask: fn('selectTask'),
  applyPresetTemplate: fn('applyPresetTemplate'),
  deleteSelectedTask: fn('deleteSelectedTask'),
  deleteTask: fn('deleteTask'),
  handleTaskOptionUpdate: fn('handleTaskOptionUpdate'),
  moveTask: fn('moveTask'),
  handleTaskDragEnd: fn('handleTaskDragEnd'),
  addTaskCascaderValue: [],
  addTaskCascaderOptions: [],
  hasNewTasks: false,
  handleAddTaskCascaderChange: fn('handleAddTaskCascaderChange'),
  MAAFW_DISPLAY_NAME: 'MFW',
  restoreOpen: false,
  restoreTargets: [],
  restoreApi: {},
  previewSections: () => [],
  handleRestored: fn('handleRestored'),
  handleCancel: fn('handleCancel'),
})

const render = async (page: Component) => {
  const app = createSSRApp(page)
  app.use(i18n)
  for (const name of SHELLS) app.component(name, shell(name))
  return (await renderToString(app)).replace(/<!--[\s\S]*?-->/g, '')
}

const renderScriptPage = async (flavor: MaaFWFlavor) => {
  mocks.script = scriptState(flavor)
  return render(MaaFWScriptEdit)
}

const renderUserPage = async (flavor: MaaFWFlavor) => {
  mocks.user = userState(flavor)
  return render(MaaFWUserEdit)
}

/** 收到的入参换成可比较的形状：函数按名字比（页面传的是同一个处理函数） */
const comparable = (attrs: Record<string, unknown> | undefined) =>
  Object.fromEntries(
    Object.entries(attrs ?? {}).map(([key, value]) => [
      key,
      typeof value === 'function'
        ? `fn:${(value as { displayName?: string }).displayName ?? value.name}`
        : value,
    ])
  )

const withSections = (
  base: MaaFWFlavor,
  scriptSections: MaaFWFlavor['scriptPage']['sections'],
  userSections: MaaFWFlavor['userPage']['sections'] = {}
): MaaFWFlavor => ({
  ...base,
  scriptPage: { ...base.scriptPage, sections: scriptSections },
  userPage: { ...base.userPage, sections: userSections },
})

afterEach(() => {
  received.clear()
})

describe('MFW 页面分节替换', () => {
  it('通用 MaaFW：脚本页五个分节、用户页三个分节都是 MFW 默认的', async () => {
    const maafw = resolveMaaFWFlavor('MaaFW')
    const scriptHtml = await renderScriptPage(maafw)
    for (const key of ['basicInfo', 'control', 'update', 'run', 'shellImport']) {
      expect(scriptHtml).toContain(`data-section="default:${key}"`)
    }
    const userHtml = await renderUserPage(maafw)
    for (const key of ['header', 'userBasicInfo', 'taskQueue']) {
      expect(userHtml).toContain(`data-section="default:${key}"`)
    }
  })

  it('特调替换脚本页 control：按需加载的替换分节顶上，收到的属性与监听和默认分节一模一样', async () => {
    const maafw = resolveMaaFWFlavor('MaaFW')
    await renderScriptPage(maafw)
    const defaultReceived = comparable(received.get('default:control'))
    expect(Object.keys(defaultReceived)).toContain('game-update-hint-key')
    expect(defaultReceived.onChange).toBe('fn:handleChange')

    const load = vi.fn(async () => recordingStub('flavor:control'))
    const flavor = withSections(maafw, {
      control: fakeSection('scriptPage', 'control', load),
    })
    const html = await renderScriptPage(flavor)
    expect(html).toContain('data-section="flavor:control"')
    expect(html).not.toContain('data-section="default:control"')
    // 其余分节不受影响
    expect(html).toContain('data-section="default:basicInfo"')
    expect(html).toContain('data-section="default:run"')
    expect(load).toHaveBeenCalledOnce()
    expect(comparable(received.get('flavor:control'))).toEqual(defaultReceived)
  })

  it('外壳导入分节换掉后 v-model 照样双向绑定（selectedIds + update:selectedIds）', async () => {
    const maafw = resolveMaaFWFlavor('MaaFW')
    await renderScriptPage(maafw)
    const defaultReceived = received.get('default:shellImport')!
    expect(Object.keys(defaultReceived).sort()).toEqual(
      ['disabled', 'instances', 'onUpdate:selectedIds', 'selected-ids'].sort()
    )
    const flavor = withSections(maafw, {
      shellImport: fakeSection('scriptPage', 'shellImport', async () =>
        recordingStub('flavor:shellImport')
      ),
    })
    await renderScriptPage(flavor)
    expect(Object.keys(received.get('flavor:shellImport')!).sort()).toEqual(
      Object.keys(defaultReceived).sort()
    )
  })

  it('特调替换用户页 taskQueue：两栏整个换成特调的，属性、v-model 与监听同默认', async () => {
    const maafw = resolveMaaFWFlavor('MaaFW')
    await renderUserPage(maafw)
    const defaultReceived = comparable(received.get('default:taskQueue'))
    expect(defaultReceived.onReorderTasks).toBe('fn:applyQueuedTaskIds')
    expect(Object.keys(defaultReceived)).toContain('onUpdate:showPresetModal')

    const flavor = withSections(
      maafw,
      {},
      {
        taskQueue: fakeSection('userPage', 'taskQueue', async () =>
          recordingStub('flavor:taskQueue')
        ),
      }
    )
    const html = await renderUserPage(flavor)
    expect(html).toContain('data-section="flavor:taskQueue"')
    expect(html).not.toContain('data-section="default:taskQueue"')
    expect(html).toContain('data-section="default:header"')
    const flavorReceived = comparable(received.get('flavor:taskQueue'))
    // v-model 的更新回调是模板里现生成的箭头函数，只比键
    expect(Object.keys(flavorReceived).sort()).toEqual(Object.keys(defaultReceived).sort())
    for (const [key, value] of Object.entries(defaultReceived)) {
      if (!key.startsWith('onUpdate:')) expect([key, flavorReceived[key]]).toEqual([key, value])
    }
  })

  it('页面上 M9A / MSS 没有替换分节，渲染的仍是 MFW 默认分节', async () => {
    for (const type of ['M9A', 'MSS']) {
      const html = await renderScriptPage(resolveMaaFWFlavor(type))
      expect(html).toContain('data-section="default:control"')
    }
  })
})
