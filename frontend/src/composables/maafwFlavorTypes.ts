// MaaFW 特调注册表的类型与声明工具。与注册表（useMaaFWFlavor.ts）分开放：
// 各特调目录下的描述对象要从这里取类型和 defineMaaFWFlavorSlotComponent，
// 而注册表又要 import 那些描述对象，放在同一个文件里会成环。

import { defineAsyncComponent, type Component } from 'vue'
import type { MaaFWUserConfig, ScriptType } from '@/types/script'

/** 由 MaaFW 引擎运行的脚本类型：MaaFW 本身 + 各特调。新增特调时在这里加一项 */
export type MaaFWFlavorType = Extract<ScriptType, 'MaaFW' | 'M9A' | 'MSS'>

/** 用户页表单草稿：用户配置 + 顶部的用户名输入 */
export type MaaFWUserFormData = MaaFWUserConfig & { userName: string }

/**
 * 插入点：公共页面上留给特调独有区块的位置，按页面分组。只按现有特调实际用到的位置定义，
 * 需要新位置时在对应页面下加名字和它的上下文，再在公共页面对应处放一个 <MaaFWFlavorSlot>。
 */
export interface MaaFWFlavorPartSlotContextMap {
  scriptPage: Record<never, never>
  userPage: {
    /** 用户页「任务队列配置」标题与队列提示之下、任务队列两栏之上 */
    userBeforeTaskQueue: MaaFWUserSlotContext
  }
}

/** 描述对象里按页面分组的部分 */
export type MaaFWFlavorPart = keyof MaaFWFlavorPartSlotContextMap

/** 用户页的插入点（MaaFWFlavorSlot 目前只放在用户页） */
export type MaaFWFlavorSlotContextMap = MaaFWFlavorPartSlotContextMap['userPage']

export type MaaFWFlavorSlotName = keyof MaaFWFlavorSlotContextMap

/**
 * 用户页插入点的上下文。组件以 `context` 一个 prop 接收，改动直接写进 formData
 * （与 BasicInfoSection 等分节一样，草稿归页面所有），落盘通过 `save` 事件交回页面。
 */
export interface MaaFWUserSlotContext {
  formData: MaaFWUserFormData
  /** 页面仍在加载：控件置灰 */
  loading: boolean
  /** 任务队列里的任务实例数 */
  queuedTaskCount: number
}

/** 插入点里的一个组件：渲染用的异步组件 + 同一个加载函数（页面加载期间预取，首屏不闪） */
export interface MaaFWFlavorSlotComponent {
  component: Component
  load: () => Promise<unknown>
}

/** 声明插入点组件：只有当前特调用到时才会加载对应的 chunk */
export const defineMaaFWFlavorSlotComponent = (
  load: () => Promise<Component | { default: Component }>
): MaaFWFlavorSlotComponent => ({
  component: defineAsyncComponent(load),
  load,
})

/** 某个页面的插入点 → 组件（按数组顺序渲染）；没有独有区块写 {} */
export type MaaFWFlavorSlots<P extends MaaFWFlavorPart> = {
  [N in keyof MaaFWFlavorPartSlotContextMap[P]]?: readonly MaaFWFlavorSlotComponent[]
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

/** 路由 */
export interface MaaFWFlavorRoutes {
  /** 路由后缀：/scripts/:id/edit/<suffix>、/scripts/:id/users/add/<suffix> 等 */
  suffix: string
}

/** 新建流程 */
export interface MaaFWFlavorCreate {
  card: MaaFWFlavorCreateOption
}

/** 脚本页文案（t() 用的 key；为空表示沿用通用写法或不显示） */
export interface MaaFWScriptPageText {
  /** 脚本页标题；为空表示沿用 MaaFW 的「<项目名> 项目配置 / 项目引导」 */
  titleKey: string | null
  /** 项目目录字段：标签 / 问号提示 / 输入框占位（导入后字段锁死，提示换成统一的「已导入」那句） */
  sourceDirectoryKey: string
  sourceHintKey: string
  sourcePlaceholderKey: string
  /** 控制方式一步顶部的一行提示；为空则不显示 */
  controllerHintKey: string | null
  /**
   * 「游戏更新」下拉的问号提示；为空表示这个类型的后端特调没有游戏更新钩子，
   * 下拉整个不显示（游戏包名独占一行，布局与通用 MaaFW 相同）
   */
  gameUpdateHintKey: string | null
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
  slots: MaaFWFlavorSlots<'scriptPage'>
  prepare: MaaFWFlavorPrepare
}

/** 用户页 */
export interface MaaFWUserPagePart {
  text: MaaFWUserPageText
  managed: MaaFWManagedTasks
  slots: MaaFWFlavorSlots<'userPage'>
  /** 用户页加载期间（与读取 interface 并行）调用 */
  prepare: MaaFWFlavorPrepare
}

/**
 * 一个特调 = 一个描述对象。身份平铺在顶层，其余按页面分组。注册表里的描述对象字段全部齐全
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
