import { afterEach, describe, expect, it, vi } from 'vitest'
import { createSSRApp, defineComponent, h, reactive, ref, shallowRef, type Component } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { createI18n } from 'vue-i18n'
import zhCN from '@/i18n/locales/zh-CN'
import {
  defineMaaFWLazyComponent,
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
  /** 每个分节 stub 收到了哪些具名 slot（control 分节的 besidePackageName 由页面按特调决定填不填） */
  const receivedSlots = new Map<string, string[]>()
  // vi.mock 的工厂比本文件的 import 先跑，vue 由调用方传进来
  const recordingStub = (vue: typeof import('vue'), name: string) =>
    vue.defineComponent({
      name,
      inheritAttrs: false,
      setup(_props, { attrs, slots }) {
        received.set(name, { ...attrs })
        receivedSlots.set(name, Object.keys(slots))
        return () => vue.h('section', { 'data-section': name }, slots.besidePackageName?.())
      },
    })
  return {
    received,
    receivedSlots,
    recordingStub,
    script: null as Record<string, unknown> | null,
    user: null as Record<string, unknown> | null,
  }
})
const { received, receivedSlots } = mocks
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
  ImportOutlined: { render: () => null },
  QuestionCircleOutlined: { render: () => null },
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
    setup(_props, { attrs, slots }) {
      return () =>
        h(
          'div',
          { class: [name, attrs.class] },
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
  'AFormItem',
  'ASelect',
  'ATooltip',
  'ASwitch',
  'AEmpty',
  'ADescriptions',
  'ADescriptionsItem',
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
  importShellHotkeys: true,
  shellImporting: false,
  finishButtonLabel: '完成',
  handleFinishWizard: fn('handleFinishWizard'),
  previewProjectTitle: '演示',
  typeTagLabel: flavor.typeTagLabel,
  pageTitle: '演示 项目引导',
  interfaceStats: [],
  handlePreviewInterface: fn('handlePreviewInterface'),
  handleCancel: fn('handleCancel'),
  flavorSlotContext: {
    scriptId: 's1',
    maafwConfig: { Info: { Name: 'n' }, Run: { GameUpdateMode: 'Check' } },
    previewData: { tasks: [] },
    interfaceDisabled: false,
    loading: false,
    isWizard: true,
  },
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
  scriptRoute: { name: `${flavor.type}ScriptEdit`, params: { id: 's1' } },
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
  flavorSlotContext: {
    formData: { Info: {} },
    loading: false,
    queuedTaskCount: 0,
    previewData: null,
    scriptId: 's1',
  },
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
  userImportCandidates: [],
  userImportLoading: false,
  loadUserImportCandidates: fn('loadUserImportCandidates'),
  importQueueFromUser: fn('importQueueFromUser'),
  queueTemplates: [],
  queueTemplateDraft: [],
  saveQueueTemplate: fn('saveQueueTemplate'),
  applyQueueTemplate: fn('applyQueueTemplate'),
  renameQueueTemplate: fn('renameQueueTemplate'),
  deleteQueueTemplate: fn('deleteQueueTemplate'),
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
  // 去掉注释锚点与 scoped 样式的 data-v 属性，只比结构
  return (await renderToString(app))
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/ data-v-[0-9a-f]+(="")?/g, '')
}

const renderScriptPage = async (flavor: MaaFWFlavor, overrides: Record<string, unknown> = {}) => {
  mocks.script = { ...scriptState(flavor), ...overrides }
  return render(MaaFWScriptEdit)
}

const renderUserPage = async (flavor: MaaFWFlavor, overrides: Record<string, unknown> = {}) => {
  mocks.user = { ...userState(flavor), ...overrides }
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
    expect(Object.keys(defaultReceived)).toContain('interface-dependent-disabled')
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

  it('控制方式提示：只有 MSS 在 beforeControl 插入点渲染自己的提示，位置在控制方式分节之前', async () => {
    const hint = '<div class="AAlert flavor-controller-hint"></div>'
    for (const type of ['MaaFW', 'M9A']) {
      const html = await renderScriptPage(resolveMaaFWFlavor(type))
      expect([type, html.includes('flavor-controller-hint')]).toEqual([type, false])
    }
    const html = await renderScriptPage(resolveMaaFWFlavor('MSS'))
    expect(html).toContain(`${hint}<section data-section="default:control"></section>`)
  })

  it('包名旁插入点：只有 M9A 填 control 分节的 besidePackageName（游戏更新下拉），MaaFW / MSS 不填', async () => {
    for (const type of ['MaaFW', 'MSS']) {
      const html = await renderScriptPage(resolveMaaFWFlavor(type))
      expect([type, receivedSlots.get('default:control')]).toEqual([type, []])
      expect(html).not.toContain(zhCN.edit.gameUpdate)
    }
    const html = await renderScriptPage(resolveMaaFWFlavor('M9A'))
    expect(receivedSlots.get('default:control')).toEqual(['besidePackageName'])
    // M9A 自己的组件（按需加载）渲染在 control 分节里，标签与问号提示与改前相同
    expect(html).toContain(zhCN.edit.gameUpdate)
  })

  it('外壳导入分节换掉后 v-model 照样双向绑定（selectedIds / importHotkeys 与对应 update 事件）', async () => {
    const maafw = resolveMaaFWFlavor('MaaFW')
    await renderScriptPage(maafw)
    const defaultReceived = received.get('default:shellImport')!
    expect(Object.keys(defaultReceived).sort()).toEqual(
      [
        'disabled',
        'import-hotkeys',
        'instances',
        'onUpdate:importHotkeys',
        'onUpdate:selectedIds',
        'selected-ids',
      ].sort()
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

/** 插入点里的组件：渲染一个标记，并在 setup 里替用户发一次事件 */
const markerSlot = (name: string, event?: { name: string; args: unknown[] }) =>
  defineMaaFWLazyComponent(async () =>
    defineComponent({
      props: { context: { type: Object, required: true } },
      emits: event ? [event.name] : [],
      setup(props, { emit }) {
        received.set(name, { context: props.context })
        if (event) emit(event.name, ...event.args)
        return () => h('p', name)
      },
    })
  )

const withSlots = (
  base: MaaFWFlavor,
  scriptSlots: MaaFWFlavor['scriptPage']['slots'],
  userSlots: MaaFWFlavor['userPage']['slots'] = {}
): MaaFWFlavor => ({
  ...base,
  scriptPage: { ...base.scriptPage, slots: scriptSlots },
  userPage: { ...base.userPage, slots: userSlots },
})

describe('MFW 页面插入点', () => {
  it('脚本页五个插入点各在自己的引导步骤块里，紧跟对应分节', async () => {
    const base = resolveMaaFWFlavor('MSS')
    const flavor = withSlots(base, {
      afterBasicInfo: [markerSlot('slot:afterBasicInfo')],
      beforeControl: [markerSlot('slot:beforeControl')],
      afterControl: [markerSlot('slot:afterControl')],
      afterUpdate: [markerSlot('slot:afterUpdate')],
      afterRun: [markerSlot('slot:afterRun')],
    })
    const html = await renderScriptPage(flavor)
    const section = (key: string) => `<section data-section="default:${key}"></section>`
    const slot = (name: string) => `<p>slot:${name}</p>`
    // 引导停在最后一步：前三步的块隐藏，插入点跟着所在步骤一起隐藏
    const hidden = '<div style="display:none;">'
    expect(html).toContain(`${hidden}${section('basicInfo')}${slot('afterBasicInfo')}</div>`)
    expect(html).toContain(
      `${hidden}${slot('beforeControl')}${section('control')}${slot('afterControl')}</div>`
    )
    expect(html).toContain(`${hidden}${section('update')}${slot('afterUpdate')}</div>`)
    expect(html).toContain(`<div>${section('run')}${slot('afterRun')}</div>`)
    // 上下文：脚本 id、配置草稿、interface、置灰与引导标记
    expect(received.get('slot:afterControl')).toMatchObject({
      context: {
        scriptId: 's1',
        interfaceDisabled: false,
        loading: false,
        isWizard: true,
        previewData: { tasks: [] },
        maafwConfig: { Info: { Name: 'n' } },
      },
    })
  })

  it('脚本页插入点的 change 交给页面的 handleChange（初始化闸门在那里）', async () => {
    const handleChange = vi.fn()
    const flavor = withSlots(resolveMaaFWFlavor('MaaFW'), {
      afterRun: [markerSlot('slot:afterRun', { name: 'change', args: ['Run', 'Foo', true] })],
    })
    await renderScriptPage(flavor, {
      handleChange,
      flavorSlotContext: { scriptId: 's1' },
    })
    expect(handleChange.mock.calls).toEqual([['Run', 'Foo', true]])
  })

  it('用户页三个插入点：基本信息之后、队列标题之后两栏之前、两栏之后；save 交给 handleFieldSave', async () => {
    const handleFieldSave = vi.fn()
    const flavor = withSlots(
      resolveMaaFWFlavor('MaaFW'),
      {},
      {
        afterBasicInfo: [markerSlot('slot:afterBasicInfo')],
        beforeTaskQueue: [markerSlot('slot:beforeTaskQueue')],
        afterTaskQueue: [
          markerSlot('slot:afterTaskQueue', { name: 'save', args: ['Info.Foo', 1] }),
        ],
      }
    )
    const html = await renderUserPage(flavor, { handleFieldSave })
    const order = [
      '<section data-section="default:userBasicInfo">',
      '<p>slot:afterBasicInfo</p>',
      '<h3>任务队列配置</h3>',
      '<p>slot:beforeTaskQueue</p>',
      '<section data-section="default:taskQueue">',
      '<p>slot:afterTaskQueue</p>',
    ].map(marker => html.indexOf(marker))
    expect(order.every(index => index >= 0)).toBe(true)
    expect([...order].sort((a, b) => a - b)).toEqual(order)
    expect(handleFieldSave.mock.calls).toEqual([['Info.Foo', 1]])
  })

  it('MSS 的计划表与活动优先仍在队列标题之后、两栏之前', async () => {
    const html = await renderUserPage(resolveMaaFWFlavor('MSS'), {
      flavorSlotContext: {
        formData: { Info: { PlanMode: 'Fixed' } },
        loading: false,
        queuedTaskCount: 1,
        previewData: null,
        scriptId: 's1',
      },
    })
    const header = html.indexOf('<h3>任务队列配置</h3>')
    const plan = html.indexOf('flavor-plan-mode')
    const activity = html.indexOf('flavor-activity-first')
    const queue = html.indexOf('data-section="default:taskQueue"')
    expect(header).toBeGreaterThanOrEqual(0)
    expect(plan).toBeGreaterThan(header)
    expect(activity).toBeGreaterThan(plan)
    expect(queue).toBeGreaterThan(activity)
  })
})

describe('用户页队列标题分节 queueHeader', () => {
  it('默认分节：标题 + 配置恢复按钮 + 一行一个提示框 + 受管任务提示，与抽出前同样的结构', async () => {
    const html = await renderUserPage(resolveMaaFWFlavor('MaaFW'), {
      queueHintLines: ['第一行', '第二行'],
      managedQueueAlert: { type: 'warning', message: '要拆用户' },
    })
    const start = html.indexOf('<div class="AFlex section-header"')
    const end = html.indexOf('<section data-section="default:taskQueue">')
    expect(start).toBeGreaterThanOrEqual(0)
    expect(end).toBeGreaterThan(start)
    const section = html.slice(start, end)
    // 标题一行右侧并排两个入口：配置导入、配置恢复
    expect(section).toContain('<h3>任务队列配置</h3>')
    expect(section.indexOf('配置导入')).toBeGreaterThan(section.indexOf('<h3>'))
    expect(section.indexOf('配置恢复')).toBeGreaterThan(section.indexOf('配置导入'))
    // 一行一个提示框（两条提示 + 一条受管提示）
    expect(section.match(/class="AAlert flavor-queue-hint"/g)).toHaveLength(3)
  })

  it('换成特调的 queueHeader：收到提示行、受管提示与 open-restore 监听，点了打开恢复弹窗', async () => {
    const restoreOpen = ref(false)
    const flavor = withSections(
      resolveMaaFWFlavor('MaaFW'),
      {},
      {
        queueHeader: fakeSection('userPage', 'queueHeader', async () =>
          recordingStub('flavor:queueHeader')
        ),
      }
    )
    const html = await renderUserPage(flavor, {
      restoreOpen,
      queueHintLines: ['提示'],
      managedQueueAlert: null,
    })
    expect(html).toContain('data-section="flavor:queueHeader"')
    expect(html).not.toContain('<h3>任务队列配置</h3>')
    const attrs = received.get('flavor:queueHeader')!
    expect(Object.keys(attrs).sort()).toEqual(
      [
        'managed-queue-alert',
        'onImportFromUser',
        'onImported',
        'onLoadUserImport',
        'onOpenRestore',
        'queue-hint-lines',
        'user-import-candidates',
        'user-import-loading',
      ].sort()
    )
    expect(attrs['queue-hint-lines']).toEqual(['提示'])
    ;(attrs.onOpenRestore as () => void)()
    expect(restoreOpen.value).toBe(true)
  })
})
