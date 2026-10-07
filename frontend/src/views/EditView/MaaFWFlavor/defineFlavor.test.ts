import { describe, expect, it } from 'vitest'
import {
  defineMaaFWLazyComponent,
  defineMaaFWSection,
  type MaaFWFlavor,
  type MaaFWFlavorCreateOption,
} from '@/composables/maafwFlavorTypes'
import { resolveMaaFWFlavor } from '@/composables/useMaaFWFlavor'
import { MAS_DOC_URLS } from '@/utils/openExternal'
import { SCRIPT_LOGOS } from '@/utils/scriptLogos'
import { defineMaaFWFlavor, mergeMaaFWFlavor, type MaaFWFlavorSpec } from './defineFlavor'
import { MAAFW_FLAVOR } from './maafw'

const card: MaaFWFlavorCreateOption = {
  titleKey: 'scripts.type.X',
  descriptionKey: 'scripts.create.typeDesc.X',
  keywords: ['x'],
  group: 'specialized',
  after: null,
}

const identity: MaaFWFlavorSpec = {
  type: 'MaaFW',
  scriptConfigType: 'XConfig',
  userConfigType: 'XUserConfig',
  defaultScriptName: '新 X 脚本',
  typeTagLabel: 'X',
  typeTagColor: 'red',
  logo: 'x.png',
  docUrl: 'https://x',
  routes: { suffix: 'x' },
  create: { card },
}

/** 每个可为空的字段都有值、带插入点与钩子的底：用来区分「沿用」「关掉」「不继承」 */
const slot = defineMaaFWLazyComponent(async () => ({}))
const prepare = async () => undefined
const basePage = defineMaaFWLazyComponent(async () => ({}))
const runSection = defineMaaFWSection(
  'scriptPage',
  'run',
  () => import('../Script/MaaFWScriptEdit/RunConfigSection.vue')
)
const headerSection = defineMaaFWSection(
  'userPage',
  'header',
  () => import('../User/MaaFWUserEdit/MaaFWUserEditHeader.vue')
)
const sourceSection = defineMaaFWSection(
  'create',
  'source',
  () => import('@/views/scripts/components/MaaFWSourceStep.vue')
)
const RICH_BASE: MaaFWFlavor = {
  ...MAAFW_FLAVOR,
  create: {
    card: MAAFW_FLAVOR.create.card,
    sections: { source: sourceSection },
    slots: { afterSourceStep: [slot] },
  },
  scriptPage: {
    text: {
      titleKey: 'base.title',
      sourceDirectoryKey: 'base.dir',
      sourceHintKey: 'base.hint',
      sourcePlaceholderKey: 'base.placeholder',
    },
    page: basePage,
    sections: { run: runSection },
    slots: {},
    prepare,
  },
  userPage: {
    text: {
      accountPlaceholderKey: 'base.account',
      accountTooltipKey: 'base.accountTooltip',
      queueHintKey: 'base.queue',
    },
    managed: {
      entries: ['Base'],
      accountTask: { entry: 'Base', resources: ['r'] },
      warningKey: 'base.warning',
      noticeKey: 'base.notice',
    },
    page: basePage,
    sections: { header: headerSection },
    slots: { beforeTaskQueue: [slot] },
    prepare,
  },
}

describe('defineMaaFWFlavor 合并规则', () => {
  it('身份、路由后缀、新建卡片照抄 spec，不继承', () => {
    const flavor = mergeMaaFWFlavor(RICH_BASE, identity)
    expect(flavor).toMatchObject({
      type: 'MaaFW',
      scriptConfigType: 'XConfig',
      userConfigType: 'XUserConfig',
      defaultScriptName: '新 X 脚本',
      typeTagLabel: 'X',
      typeTagColor: 'red',
      logo: 'x.png',
      docUrl: 'https://x',
      routes: { suffix: 'x' },
      create: { card },
    })
    // 新建卡片不从底继承
    expect(flavor.create.card).toBe(card)
  })

  it('什么都不写：text / managed 整组沿用底；page / sections / slots / prepare 不继承', () => {
    const flavor = mergeMaaFWFlavor(RICH_BASE, identity)
    expect(flavor.scriptPage.text).toEqual(RICH_BASE.scriptPage.text)
    expect(flavor.userPage.text).toEqual(RICH_BASE.userPage.text)
    expect(flavor.userPage.managed).toEqual(RICH_BASE.userPage.managed)
    expect(flavor.scriptPage.page).toBeNull()
    expect(flavor.userPage.page).toBeNull()
    expect(flavor.scriptPage.sections).toEqual({})
    expect(flavor.userPage.sections).toEqual({})
    expect(flavor.scriptPage.slots).toEqual({})
    expect(flavor.userPage.slots).toEqual({})
    expect(flavor.scriptPage.prepare).toBeNull()
    expect(flavor.userPage.prepare).toBeNull()
    expect(flavor.create.sections).toEqual({})
    expect(flavor.create.slots).toEqual({})
    // 合并结果是新对象，改它不会改到底
    expect(flavor.scriptPage.text).not.toBe(RICH_BASE.scriptPage.text)
  })

  it('按字段浅合并：写了的覆盖，undefined 沿用，null 明确关掉', () => {
    const ownSlot = defineMaaFWLazyComponent(async () => ({}))
    const ownPrepare = async () => undefined
    const ownPage = defineMaaFWLazyComponent(async () => ({}))
    const flavor = mergeMaaFWFlavor(RICH_BASE, {
      ...identity,
      scriptPage: {
        text: { sourceHintKey: 'own.hint', sourcePlaceholderKey: undefined, titleKey: null },
        page: ownPage,
        sections: { run: runSection },
      },
      userPage: {
        text: { queueHintKey: null },
        managed: { entries: ['Own'], accountTask: null, warningKey: undefined },
        slots: { beforeTaskQueue: [ownSlot] },
        prepare: ownPrepare,
      },
    })
    expect(flavor.scriptPage.text).toEqual({
      ...RICH_BASE.scriptPage.text,
      sourceHintKey: 'own.hint',
      titleKey: null,
    })
    expect(flavor.userPage.text).toEqual({ ...RICH_BASE.userPage.text, queueHintKey: null })
    expect(flavor.userPage.managed).toEqual({
      entries: ['Own'],
      accountTask: null,
      warningKey: 'base.warning',
      noticeKey: 'base.notice',
    })
    expect(flavor.scriptPage.page).toBe(ownPage)
    expect(flavor.userPage.page).toBeNull()
    expect(flavor.scriptPage.sections).toEqual({ run: runSection })
    expect(flavor.userPage.sections).toEqual({})
    expect(flavor.userPage.slots).toEqual({ beforeTaskQueue: [ownSlot] })
    expect(flavor.userPage.prepare).toBe(ownPrepare)
  })

  it('新建流程：写了的替换分节与插入点照抄，没写的那一项为空', () => {
    const ownSlot = defineMaaFWLazyComponent(async () => ({}))
    const withSection = mergeMaaFWFlavor(RICH_BASE, {
      ...identity,
      create: { card, sections: { source: sourceSection } },
    })
    expect(withSection.create).toEqual({ card, sections: { source: sourceSection }, slots: {} })
    const withSlot = mergeMaaFWFlavor(RICH_BASE, {
      ...identity,
      create: { card, slots: { afterSourceStep: [ownSlot] } },
    })
    expect(withSlot.create).toEqual({
      card,
      sections: {},
      slots: { afterSourceStep: [ownSlot] },
    })
  })

  it('路由标题：不写就按类型标签生成（不继承底的标题），写了的逐条覆盖', () => {
    const generated = mergeMaaFWFlavor(RICH_BASE, identity)
    expect(generated.routes.titles).toEqual({
      script: '编辑X脚本',
      setup: 'X项目引导',
      userAdd: '添加X用户',
      userEdit: '编辑X用户',
    })
    const overridden = mergeMaaFWFlavor(RICH_BASE, {
      ...identity,
      routes: { suffix: 'x', titles: { setup: 'X 引导', userAdd: undefined } },
    })
    expect(overridden.routes).toEqual({
      suffix: 'x',
      titles: { ...generated.routes.titles, setup: 'X 引导' },
    })
  })

  it('defineMaaFWFlavor 以通用 MaaFW 为底', () => {
    expect(defineMaaFWFlavor(identity)).toEqual(mergeMaaFWFlavor(MAAFW_FLAVOR, identity))
    expect(defineMaaFWFlavor(identity).userPage.text).toEqual(MAAFW_FLAVOR.userPage.text)
  })
})

// 改成分组前（dev 5b3129815）三个描述对象的平铺字段，逐项照抄。解析后的值必须一字不差。
const FLAT_BEFORE = {
  MaaFW: {
    type: 'MaaFW',
    scriptConfigType: 'MaaFWConfig',
    userConfigType: 'MaaFWUserConfig',
    routeSuffix: 'maafw',
    defaultScriptName: '新 MFW 脚本',
    typeTagLabel: 'MFW',
    typeTagColor: 'geekblue',
    logo: SCRIPT_LOGOS.MaaFW,
    docUrl: MAS_DOC_URLS.scripts,
    createOption: {
      titleKey: 'scripts.type.MaaFW',
      descriptionKey: 'scripts.create.typeDesc.MaaFW',
      keywords: ['maafw', 'maaframework', 'framework', 'mfw', 'interface.json', '通用'],
      group: 'general',
      after: 'General',
    },
    scriptTitleKey: null,
    sourceDirectoryKey: 'edit.localProjectDirectory',
    sourceHintKey: 'edit.pickMfwProjectDirectory',
    sourcePlaceholderKey: 'edit.pickActualMfwProject',
    accountPlaceholderKey: 'edit.localNoteOnly',
    accountTooltipKey: 'edit.maafwAccountRecordTooltip',
    queueHintKey: null,
    // 改前的 gameUpdateHintKey（只有 M9A 有）与 controllerHintKey（只有 MSS 有）现在都是该特调
    // 自己的插入点组件，见 scriptSlotNames
    scriptSlotNames: [],
    managedTaskEntries: [],
    managedAccountTask: null,
    managedTaskWarningKey: null,
    managedTaskNoticeKey: null,
    slotCount: 0,
    hasPrepareUserPage: false,
  },
  M9A: {
    type: 'M9A',
    scriptConfigType: 'M9AConfig',
    userConfigType: 'M9AUserConfig',
    routeSuffix: 'm9a',
    defaultScriptName: '新 M9A 脚本',
    typeTagLabel: 'M9A',
    typeTagColor: 'cyan',
    logo: SCRIPT_LOGOS.M9A,
    docUrl: MAS_DOC_URLS.scriptTypes.M9A,
    createOption: {
      titleKey: 'scripts.type.M9A',
      descriptionKey: 'scripts.create.typeDesc.M9A',
      keywords: ['m9a', '1999', '重返未来'],
      group: 'specialized',
      after: 'MaaEnd',
    },
    scriptTitleKey: 'edit.m9aFlavorScriptTitle',
    sourceDirectoryKey: 'edit.m9aFlavorSourceDirectory',
    sourceHintKey: 'edit.m9aFlavorSourceHint',
    sourcePlaceholderKey: 'edit.m9aFlavorSourcePlaceholder',
    accountPlaceholderKey: 'edit.m9aFlavorAccountPlaceholder',
    accountTooltipKey: 'edit.m9aFlavorAccountTooltip',
    queueHintKey: 'edit.m9aFlavorQueueHint',
    // 改前 gameUpdateHintKey: 'edit.m9aFlavorGameUpdateHint'（共用控制方式分节里的下拉），现在由
    // M9A 在 besidePackageName 插入点挂自己的组件，问号提示仍是那个 key
    scriptSlotNames: ['besidePackageName'],
    managedTaskEntries: ['StartUp', 'SwitchAccount', 'Close1999'],
    managedAccountTask: { entry: 'SwitchAccount', resources: ['官服'] },
    managedTaskWarningKey: 'edit.m9aFlavorManagedTaskWarning',
    managedTaskNoticeKey: 'edit.m9aFlavorManagedTaskNotice',
    slotCount: 0,
    hasPrepareUserPage: false,
  },
  MSS: {
    type: 'MSS',
    scriptConfigType: 'MSSConfig',
    userConfigType: 'MSSUserConfig',
    routeSuffix: 'mss',
    defaultScriptName: '新 MSS 脚本',
    typeTagLabel: 'MSS',
    typeTagColor: 'orange',
    logo: SCRIPT_LOGOS.MSS,
    docUrl: MAS_DOC_URLS.scripts,
    createOption: {
      titleKey: 'scripts.type.MSS',
      descriptionKey: 'scripts.create.typeDesc.MSS',
      keywords: ['mss', 'maastellasora', '星塔旅人', 'stella', 'maaframework'],
      group: 'specialized',
      after: null,
    },
    scriptTitleKey: 'edit.mssFlavorScriptTitle',
    sourceDirectoryKey: 'edit.mssFlavorSourceDirectory',
    sourceHintKey: 'edit.mssFlavorSourceHint',
    sourcePlaceholderKey: 'edit.mssFlavorSourcePlaceholder',
    accountPlaceholderKey: 'edit.localNoteOnly',
    accountTooltipKey: 'edit.maafwAccountRecordTooltip',
    queueHintKey: 'edit.mssFlavorQueueHint',
    // 改前 controllerHintKey: 'edit.mssFlavorControllerHint'（公共脚本页顶部的提示），现在由
    // MSS 在 beforeControl 插入点挂自己的组件，文案仍是那个 key
    scriptSlotNames: ['beforeControl'],
    managedTaskEntries: [],
    managedAccountTask: null,
    managedTaskWarningKey: null,
    managedTaskNoticeKey: null,
    slotCount: 3,
    hasPrepareUserPage: true,
  },
} as const

/** 分组后的描述对象按旧的平铺字段名读回来 */
const flatten = (flavor: MaaFWFlavor) => ({
  type: flavor.type,
  scriptConfigType: flavor.scriptConfigType,
  userConfigType: flavor.userConfigType,
  routeSuffix: flavor.routes.suffix,
  defaultScriptName: flavor.defaultScriptName,
  typeTagLabel: flavor.typeTagLabel,
  typeTagColor: flavor.typeTagColor,
  logo: flavor.logo,
  docUrl: flavor.docUrl,
  createOption: flavor.create.card,
  scriptTitleKey: flavor.scriptPage.text.titleKey,
  sourceDirectoryKey: flavor.scriptPage.text.sourceDirectoryKey,
  sourceHintKey: flavor.scriptPage.text.sourceHintKey,
  sourcePlaceholderKey: flavor.scriptPage.text.sourcePlaceholderKey,
  accountPlaceholderKey: flavor.userPage.text.accountPlaceholderKey,
  accountTooltipKey: flavor.userPage.text.accountTooltipKey,
  queueHintKey: flavor.userPage.text.queueHintKey,
  scriptSlotNames: Object.keys(flavor.scriptPage.slots),
  managedTaskEntries: flavor.userPage.managed.entries,
  managedAccountTask: flavor.userPage.managed.accountTask,
  managedTaskWarningKey: flavor.userPage.managed.warningKey,
  managedTaskNoticeKey: flavor.userPage.managed.noticeKey,
  slotCount: Object.values(flavor.userPage.slots).flat().length,
  hasPrepareUserPage: typeof flavor.userPage.prepare === 'function',
})

describe('分组前后等价', () => {
  it.each(Object.keys(FLAT_BEFORE) as Array<keyof typeof FLAT_BEFORE>)(
    '%s 解析后的每个字段与改前的平铺值相同',
    type => {
      expect(flatten(resolveMaaFWFlavor(type))).toEqual(FLAT_BEFORE[type])
    }
  )

  // 改成按注册表生成前的路由标题：MaaFW 四条手写，M9A / MSS 只有脚本页与用户页三条（引导是新增的）
  it('路由标题与改前一致', () => {
    expect(resolveMaaFWFlavor('MaaFW').routes.titles).toEqual({
      script: '编辑MFW脚本',
      setup: 'MaaFramework项目引导',
      userAdd: '添加 MFW 用户',
      userEdit: '编辑 MFW 用户',
    })
    for (const label of ['M9A', 'MSS']) {
      expect(resolveMaaFWFlavor(label).routes.titles).toEqual({
        script: `编辑${label}脚本`,
        setup: `${label}项目引导`,
        userAdd: `添加${label}用户`,
        userEdit: `编辑${label}用户`,
      })
    }
  })
})
