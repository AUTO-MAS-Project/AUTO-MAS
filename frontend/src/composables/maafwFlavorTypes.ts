// MaaFW 特调注册表的类型与声明工具。与注册表（useMaaFWFlavor.ts）分开放：
// 各特调目录下的描述对象要从这里取类型和 defineMaaFWLazyComponent / defineMaaFWSection，
// 而注册表又要 import 那些描述对象，放在同一个文件里会成环。

import { defineAsyncComponent, type Component } from 'vue'
import type {
  MaaFWInterfacePreviewData,
  MaaFWScriptConfig,
  MaaFWUserConfig,
  ScriptType,
} from '@/types/script'
import type { MaaFWSectionContractMap } from '@/views/EditView/MaaFWFlavor/sectionContracts'

/** 由 MaaFW 引擎运行的脚本类型：MaaFW 本身 + 各特调。新增特调时在这里加一项 */
export type MaaFWFlavorType = Extract<ScriptType, 'MaaFW' | 'M9A' | 'MSS'>

/** 用户页表单草稿：用户配置 + 顶部的用户名输入 */
export type MaaFWUserFormData = MaaFWUserConfig & { userName: string }

/**
 * 插入点：公共页面上留给特调独有区块的位置，按部分（脚本页 / 用户页 / 新建流程）分组，名字只在
 * 本部分内有意义。需要新位置时在对应部分下加名字，再在公共页面对应处放一个
 * `<MaaFWFlavorSlot part="…" name="…">`。脚本页的插入点都在引导的步骤块里面，
 * 所以在引导里随所在步骤出现，在编辑页紧跟对应分节。
 */
export interface MaaFWFlavorSlotContextMap {
  scriptPage: {
    /** 基本信息（名称、项目目录、运行环境）之后；引导第 1 步 */
    afterBasicInfo: MaaFWScriptSlotContext
    /** 控制方式一步顶部、控制方式分节之前（如 MSS 的控制方式提示）；引导第 2 步 */
    beforeControl: MaaFWScriptSlotContext
    /**
     * 控制方式分节里与「游戏包名」并排的位置（宽屏两列、窄屏上下排）；没有组件时包名独占一行。
     * 由 control 分节的同名 slot 提供：特调替换 control 分节时要自己留这个 slot。引导第 2 步
     */
    besidePackageName: MaaFWScriptSlotContext
    /** 控制方式分节之后；引导第 2 步 */
    afterControl: MaaFWScriptSlotContext
    /** 项目更新分节之后；引导第 3 步 */
    afterUpdate: MaaFWScriptSlotContext
    /** 运行设置分节之后；引导第 4 步 */
    afterRun: MaaFWScriptSlotContext
  }
  userPage: {
    /** 用户基本信息之后、「任务队列配置」标题之前 */
    afterBasicInfo: MaaFWUserSlotContext
    /** 「任务队列配置」标题与队列提示之下、任务队列两栏之上 */
    beforeTaskQueue: MaaFWUserSlotContext
    /** 任务队列两栏之后、附加脚本之前 */
    afterTaskQueue: MaaFWUserSlotContext
  }
  create: {
    /** 新建对话框 MFW 家族第二步「项目从哪来」的选项之后 */
    afterSourceStep: MaaFWCreateSlotContext
  }
}

/** 描述对象里按部分分组的那几组：脚本页、用户页、新建流程 */
export type MaaFWFlavorPart = keyof MaaFWFlavorSlotContextMap

/** 某一部分的插入点名 */
export type MaaFWFlavorSlotName<P extends MaaFWFlavorPart> = keyof MaaFWFlavorSlotContextMap[P] &
  string

/**
 * 插入点组件交回页面的事件：脚本页交 change（按 category.key 落盘），用户页交 save；
 * 新建流程的插入点只读，什么事件都不转发（新建请求里不带特调的数据）
 */
export interface MaaFWFlavorSlotEmitMap {
  scriptPage: { change: [category: keyof MaaFWScriptConfig, key: string, value: unknown] }
  userPage: { save: [key: string, value: unknown] }
  create: Record<never, never>
}

/**
 * 脚本页插入点的上下文。组件以 `context` 一个 prop 接收；配置草稿归页面所有，组件可以直接
 * 改 maafwConfig 的字段，落盘通过 `change(category, key, value)` 交回页面（初始化期间页面不落盘）。
 */
export interface MaaFWScriptSlotContext {
  readonly scriptId: string
  maafwConfig: MaaFWScriptConfig
  readonly previewData: MaaFWInterfacePreviewData | null
  /** interface 还没读到或正在读：依赖 interface 的控件置灰 */
  readonly interfaceDisabled: boolean
  /** 页面仍在加载 */
  readonly loading: boolean
  /** 当前是引导（新建脚本后的分步向导）而不是编辑页 */
  readonly isWizard: boolean
}

/**
 * 用户页插入点的上下文。组件以 `context` 一个 prop 接收，改动直接写进 formData
 * （与 BasicInfoSection 等分节一样，草稿归页面所有），落盘通过 `save` 事件交回页面。
 */
export interface MaaFWUserSlotContext {
  formData: MaaFWUserFormData
  /** 页面仍在加载：控件置灰 */
  readonly loading: boolean
  /** 任务队列里的任务实例数（虚影不算） */
  readonly queuedTaskCount: number
  /** 读到的 interface；没读到为 null */
  readonly previewData: MaaFWInterfacePreviewData | null
  readonly scriptId: string
}

/** 新建流程插入点的上下文：只读，组件以 `context` 一个 prop 接收 */
export interface MaaFWCreateSlotContext {
  /** 选中的类型卡片 */
  readonly type: MaaFWFlavorType
  /** 「项目从哪来」当前的选择：'new' = 新建一个别的项目；否则是要复用的项目所属脚本的 id */
  readonly selection: string
}

/**
 * 按需加载的组件：渲染用的异步组件 + 同一个加载函数（页面加载期间预取，首屏不闪）。
 * 插入点组件与替换分节都是它。
 */
export interface MaaFWLazyComponent {
  component: Component
  load: () => Promise<unknown>
}

/** 声明按需加载的组件：只有当前特调用到时才会加载对应的 chunk */
export const defineMaaFWLazyComponent = (
  load: () => Promise<Component | { default: Component }>
): MaaFWLazyComponent => ({
  component: defineAsyncComponent(load),
  load,
})

/** 某一部分的插入点 → 组件（按数组顺序渲染）；没有独有区块写 {} */
export type MaaFWFlavorSlots<P extends MaaFWFlavorPart> = {
  [N in MaaFWFlavorSlotName<P>]?: readonly MaaFWLazyComponent[]
}

// ---- 分节替换 ----

/** 某一部分可替换的分节键（契约见 views/EditView/MaaFWFlavor/sectionContracts.ts） */
export type MaaFWSectionKey<P extends MaaFWFlavorPart> = keyof MaaFWSectionContractMap[P] & string

/** 某个页面某个分节的 props 契约 */
export type MaaFWSectionContract<
  P extends MaaFWFlavorPart,
  K extends MaaFWSectionKey<P>,
> = MaaFWSectionContractMap[P][K]

/** 替换分节：按需加载的组件，记着自己替换的是哪一页的哪一节（只能由 defineMaaFWSection 造出来） */
export interface MaaFWSection<
  P extends MaaFWFlavorPart = MaaFWFlavorPart,
  K extends MaaFWSectionKey<P> = MaaFWSectionKey<P>,
> extends MaaFWLazyComponent {
  part: P
  key: K
}

/** 某个页面的分节替换表：只写要替换的分节，其余用 MFW 默认分节 */
export type MaaFWFlavorSections<P extends MaaFWFlavorPart> = {
  [K in MaaFWSectionKey<P>]?: MaaFWSection<P, K>
}

/** 组件实例上的 props 类型（SFC 的类型由 vue-tsc 推出） */
type ComponentPropsOf<C> = C extends abstract new (...args: never[]) => { $props: infer Props }
  ? Props
  : never

type RequiredKeys<T> = {
  [K in keyof T]-?: Record<never, never> extends Pick<T, K> ? never : K
}[keyof T]

/**
 * 组件 C 能否顶替契约为 Contract 的分节：契约里的每个 prop 它都声明了、类型接得住，
 * 而且它没有契约之外的必填 prop（页面只会传契约里的那些）。
 */
export type MaaFWAcceptsSectionContract<C, Contract> = [ComponentPropsOf<C>] extends [never]
  ? false
  : [Exclude<keyof Contract, keyof ComponentPropsOf<C>>] extends [never]
    ? [Exclude<RequiredKeys<ComponentPropsOf<C>>, keyof Contract>] extends [never]
      ? Contract extends Pick<ComponentPropsOf<C>, keyof Contract & keyof ComponentPropsOf<C>>
        ? true
        : false
      : false
    : false

/**
 * 声明一个替换分节：`defineMaaFWSection('scriptPage', 'control', () => import('./X.vue'))`。
 * 只有当前特调用到时才会加载对应的 chunk。替换组件必须能接受 MFW 契约里的全部 props
 * （最省事的写法是直接 `defineProps<MaaFWScriptControlSectionProps>()`），否则 typecheck 报
 * 「缺第四个参数」，参数名就是原因。
 */
export function defineMaaFWSection<
  P extends MaaFWFlavorPart,
  K extends MaaFWSectionKey<P>,
  C extends Component,
>(
  part: P,
  key: K,
  load: () => Promise<C | { default: C }>,
  ..._contractCheck: MaaFWAcceptsSectionContract<C, MaaFWSectionContract<P, K>> extends true
    ? []
    : [replacementMustAcceptAllContractProps: never]
): MaaFWSection<P, K> {
  return { ...defineMaaFWLazyComponent(load), part, key }
}

/** 页面加载期间调用的钩子，给独有区块备数据；失败自行兜底，不要抛 */
export type MaaFWFlavorPrepare = (() => Promise<void>) | null

/** 新建脚本对话框里的类型卡片 */
export interface MaaFWFlavorCreateOption {
  titleKey: string
  descriptionKey: string
  /** 搜索别名。刻意保留中文：译成英文中文用户就搜不到了 */
  keywords: string[]
  group: 'specialized' | 'general'
  /** 卡片排在哪个类型的卡片后面；null 排到最后 */
  after: ScriptType | null
}

/**
 * 页面种类：每个特调各有这四条路由（router/maafwFlavorRoutes.ts 按注册表生成）。
 * script / setup 渲染脚本页（编辑形态 / 新建后的分步引导），userAdd / userEdit 渲染用户页。
 */
export type MaaFWPageKind = 'script' | 'setup' | 'userAdd' | 'userEdit'

/** 页面种类 → 渲染哪一页（描述对象里的哪一组） */
export const MAAFW_PAGE_PART = {
  script: 'scriptPage',
  setup: 'scriptPage',
  userAdd: 'userPage',
  userEdit: 'userPage',
} as const satisfies Record<MaaFWPageKind, MaaFWFlavorPart>

/** 有路由、能整页替换的部分（新建流程是对话框里的一步，不在此列） */
export type MaaFWPagePart = (typeof MAAFW_PAGE_PART)[MaaFWPageKind]

/** 路由 */
export interface MaaFWFlavorRoutes {
  /** 路由后缀：/scripts/:id/edit/<suffix>、/scripts/:id/users/add/<suffix> 等 */
  suffix: string
  /** 四条路由的标题（route.meta.title） */
  titles: Record<MaaFWPageKind, string>
}

/**
 * 新建流程（新建脚本对话框）。没有整页替换，也没有 prepare：这一步没有要预取的特调数据，
 * 新建请求也不带特调的数据（后端新建只认类型）。
 */
export interface MaaFWFlavorCreate {
  card: MaaFWFlavorCreateOption
  /** 替换的分节（MFW 家族第二步 source）；没有写 {} */
  sections: MaaFWFlavorSections<'create'>
  slots: MaaFWFlavorSlots<'create'>
}

/** 脚本页文案（t() 用的 key；为空表示沿用通用写法或不显示） */
export interface MaaFWScriptPageText {
  /** 脚本页标题；为空表示沿用 MaaFW 的「<项目名> 项目配置 / 项目引导」 */
  titleKey: string | null
  /** 项目目录字段：标签 / 问号提示 / 输入框占位（导入后字段锁死，提示换成统一的「已导入」那句） */
  sourceDirectoryKey: string
  sourceHintKey: string
  sourcePlaceholderKey: string
}

/** 用户页文案 */
export interface MaaFWUserPageText {
  /** 账号字段的占位与问号提示（密码字段所有 flavor 都是「仅本地记录」） */
  accountPlaceholderKey: string
  accountTooltipKey: string
  /** 任务队列区顶部的提示（\n 分行，一行一个框）；为空则不显示 */
  queueHintKey: string | null
}

/** 受管任务：由后端特调全权控制的任务 */
export interface MaaFWManagedTasks {
  /**
   * 不许用户自己加的任务（interface 里任务的 entry）：用户页「添加任务」与预设模板里都不出现。
   * 已经在队列里的照常显示（能看能删），并按 warningKey 在队列上方给一条警告。没有写 []
   */
  entries: readonly string[]
  /**
   * 受管的切号任务：资源在 resources 里、队列里它的有效实例（目标账号非空）≥ 2 时，后端拒绝
   * 运行该用户、要求拆成多个用户（与后端特调同一判据）。没有写 null
   */
  accountTask: { entry: string; resources: readonly string[] } | null
  /** 需要拆用户时的警告（插值 count：个数，accounts：各目标账号）；为空则不显示 */
  warningKey: string | null
  /** 其余受管任务残留在队列里时的提示（插值 tasks：任务名；运行照常）；为空则不显示 */
  noticeKey: string | null
}

/** 脚本页 */
export interface MaaFWScriptPagePart {
  text: MaaFWScriptPageText
  /**
   * 整页替换：特调自己的脚本页（编辑与引导两种形态都由它渲染），没有写 null。用 MFW 导出的分节与
   * 编排层拼（views/EditView/Script/MaaFWScriptEdit/pageKit.ts），页面宿主按脚本实际类型选它。
   */
  page: MaaFWLazyComponent | null
  /** 替换的分节；没有写 {} */
  sections: MaaFWFlavorSections<'scriptPage'>
  slots: MaaFWFlavorSlots<'scriptPage'>
  /** 脚本页读到脚本详情后（与后续加载并行）调用；导入后类型变成本特调时再调一次 */
  prepare: MaaFWFlavorPrepare
}

/** 用户页 */
export interface MaaFWUserPagePart {
  text: MaaFWUserPageText
  managed: MaaFWManagedTasks
  /**
   * 整页替换：特调自己的用户页（加用户与编辑用户都由它渲染），没有写 null。用 MFW 导出的分节与
   * 编排层拼（views/EditView/User/MaaFWUserEdit/pageKit.ts），页面宿主按脚本实际类型选它。
   */
  page: MaaFWLazyComponent | null
  /** 替换的分节；没有写 {} */
  sections: MaaFWFlavorSections<'userPage'>
  slots: MaaFWFlavorSlots<'userPage'>
  /** 用户页加载期间（与读取 interface 并行）调用 */
  prepare: MaaFWFlavorPrepare
}

/**
 * 一个特调 = 一个描述对象。身份平铺在顶层，其余按部分（路由、新建流程、脚本页、用户页）分组。注册表里的描述对象字段全部齐全
 * （没有就是 null / {}），组件只按这一组字段取值；特调自己用 defineMaaFWFlavor 只写差异。
 */
export interface MaaFWFlavor {
  // ---- 身份 ----
  type: MaaFWFlavorType
  /** 后端脚本配置类名（脚本索引里的 type） */
  scriptConfigType: string
  /** 后端用户配置类名（用户索引里的 type） */
  userConfigType: string
  /** 后端新建脚本时给的默认名（配置类的 DEFAULT_SCRIPT_NAME）：还是这个名字时导入后自动改成项目名 */
  defaultScriptName: string
  /** 脚本页卡片右上角、脚本列表的类型标签文字与颜色 */
  typeTagLabel: string
  typeTagColor: string
  logo: string
  /** 脚本页帮助链接 */
  docUrl: string

  // ---- 按部分分组 ----
  routes: MaaFWFlavorRoutes
  create: MaaFWFlavorCreate
  scriptPage: MaaFWScriptPagePart
  userPage: MaaFWUserPagePart
}
