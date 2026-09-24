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
 * 插入点：公共页面上留给特调独有区块的位置。只按现有特调实际用到的位置定义，
 * 需要新位置时在这里加名字、在 MaaFWFlavorSlotContextMap 里写它的上下文，
 * 再在公共页面对应处放一个 <MaaFWFlavorSlot>。
 */
export interface MaaFWFlavorSlotContextMap {
  /** 用户页「任务队列配置」标题与队列提示之下、任务队列两栏之上 */
  userBeforeTaskQueue: MaaFWUserSlotContext
}

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

/** 一个特调 = 一个描述对象。字段全部必填（没有就写 null / {}），组件只按这一组字段取值 */
export interface MaaFWFlavor {
  // ---- 身份 ----
  type: MaaFWFlavorType
  /** 后端脚本配置类名（脚本索引里的 type） */
  scriptConfigType: string
  /** 后端用户配置类名（用户索引里的 type） */
  userConfigType: string
  /** 路由后缀：/scripts/:id/edit/<suffix>、/scripts/:id/users/add/<suffix> 等 */
  routeSuffix: string
  /** 后端新建脚本时给的默认名（配置类的 DEFAULT_SCRIPT_NAME）：还是这个名字时导入后自动改成项目名 */
  defaultScriptName: string
  /** 脚本页卡片右上角、脚本列表的类型标签文字与颜色 */
  typeTagLabel: string
  typeTagColor: string
  logo: string
  /** 脚本页帮助链接 */
  docUrl: string
  createOption: MaaFWFlavorCreateOption

  // ---- 文案（t() 用的 key；为空表示沿用通用写法或不显示） ----
  /** 脚本页标题；为空表示沿用 MaaFW 的「<项目名> 项目配置 / 项目引导」 */
  scriptTitleKey: string | null
  /** 项目目录字段：标签 / 问号提示 / 输入框占位（导入后字段锁死，提示换成统一的「已导入」那句） */
  sourceDirectoryKey: string
  sourceHintKey: string
  sourcePlaceholderKey: string
  /** 脚本页控制方式一步顶部的一行提示；为空则不显示 */
  controllerHintKey: string | null
  /** 用户页账号字段的占位与问号提示（密码字段所有 flavor 都是「仅本地记录」） */
  accountPlaceholderKey: string
  accountTooltipKey: string
  /** 用户页任务队列区顶部的提示（\n 分行，一行一个框）；为空则不显示 */
  queueHintKey: string | null

  // ---- 独有区块与钩子 ----
  /** 插入点 → 组件（按数组顺序渲染）；没有独有区块写 {} */
  slots: Partial<Record<MaaFWFlavorSlotName, MaaFWFlavorSlotComponent[]>>
  /** 用户页加载期间（与读取 interface 并行）调用，给独有区块备数据；失败自行兜底，不要抛 */
  prepareUserPage: (() => Promise<void>) | null
}
