// MaaFW 页面的 flavor 文案表。
// M9A / MSS 是 MaaFW 引擎的特调类型：脚本页 / 用户页 / 创建流程都是 MaaFW 的组件，
// 它们在界面上的差别只剩这里列出的几处文案与身份（图标、类型标签、帮助链接）。
// 逻辑一律不分叉：这张表只给 t() 用的 key、静态资源与计划表消费方，不携带任何布尔开关。
// flavor 以脚本当前类型为准（导入后后端会按项目内容原地换类型），不以路由 meta 为准。

import { computed, toValue, type MaybeRefOrGetter } from 'vue'
import { PlanComboxIn } from '@/api'
import type { ScriptType } from '@/types/script'
import { MAS_DOC_URLS } from '@/utils/openExternal'
import { SCRIPT_LOGOS } from '@/utils/scriptLogos'

export type MaaFWFlavorType = 'MaaFW' | 'M9A' | 'MSS'

export interface MaaFWFlavor {
  type: MaaFWFlavorType
  /** 脚本页卡片右上角的类型标签文字与颜色 */
  typeTagLabel: string
  typeTagColor: string
  logo: string
  /** 脚本页帮助链接 */
  docUrl: string
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
  /** 用户页任务队列区顶部的一行提示；为空则不显示 */
  queueHintKey: string | null
  /** 用户页计划表下拉的消费方（后端 Info.PlanMode）；为空表示这个类型的用户没有计划表 */
  planConsumer: PlanComboxIn.consumer | null
  /** 计划表下拉下方的说明（计划表改写了哪些任务选项）；为空则不显示 */
  planHintKey: string | null
}

const MAAFW_FLAVOR: MaaFWFlavor = {
  type: 'MaaFW',
  typeTagLabel: 'MFW',
  typeTagColor: 'geekblue',
  logo: SCRIPT_LOGOS.MaaFW,
  docUrl: MAS_DOC_URLS.scripts,
  scriptTitleKey: null,
  sourceDirectoryKey: 'edit.localProjectDirectory',
  sourceHintKey: 'edit.pickMfwProjectDirectory',
  sourcePlaceholderKey: 'edit.pickActualMfwProject',
  controllerHintKey: null,
  accountPlaceholderKey: 'edit.localNoteOnly',
  accountTooltipKey: 'edit.maafwAccountRecordTooltip',
  queueHintKey: null,
  planConsumer: null,
  planHintKey: null,
}

const M9A_FLAVOR: MaaFWFlavor = {
  type: 'M9A',
  typeTagLabel: 'M9A',
  typeTagColor: 'cyan',
  logo: SCRIPT_LOGOS.M9A,
  docUrl: MAS_DOC_URLS.scriptTypes.M9A,
  scriptTitleKey: 'edit.m9aFlavorScriptTitle',
  sourceDirectoryKey: 'edit.m9aFlavorSourceDirectory',
  sourceHintKey: 'edit.m9aFlavorSourceHint',
  sourcePlaceholderKey: 'edit.m9aFlavorSourcePlaceholder',
  controllerHintKey: null,
  accountPlaceholderKey: 'edit.m9aFlavorAccountPlaceholder',
  accountTooltipKey: 'edit.m9aFlavorAccountTooltip',
  queueHintKey: 'edit.m9aFlavorQueueHint',
  planConsumer: null,
  planHintKey: null,
}

const MSS_FLAVOR: MaaFWFlavor = {
  type: 'MSS',
  typeTagLabel: 'MSS',
  typeTagColor: 'orange',
  logo: SCRIPT_LOGOS.MSS,
  docUrl: MAS_DOC_URLS.scripts,
  scriptTitleKey: 'edit.mssFlavorScriptTitle',
  sourceDirectoryKey: 'edit.mssFlavorSourceDirectory',
  sourceHintKey: 'edit.mssFlavorSourceHint',
  sourcePlaceholderKey: 'edit.mssFlavorSourcePlaceholder',
  controllerHintKey: 'edit.mssFlavorControllerHint',
  accountPlaceholderKey: 'edit.localNoteOnly',
  accountTooltipKey: 'edit.maafwAccountRecordTooltip',
  queueHintKey: 'edit.mssFlavorQueueHint',
  planConsumer: PlanComboxIn.consumer.MSS,
  planHintKey: 'edit.mssFlavorPlanHint',
}

const FLAVOR_BY_TYPE: Partial<Record<string, MaaFWFlavor>> = {
  M9A: M9A_FLAVOR,
  MSS: MSS_FLAVOR,
}

/** 按脚本类型取 flavor 表；未知 / 空类型按通用 MaaFW 处理。 */
export const resolveMaaFWFlavor = (type: ScriptType | string | null | undefined): MaaFWFlavor =>
  (type && FLAVOR_BY_TYPE[type]) || MAAFW_FLAVOR

/** 响应式版本：类型变了（导入后后端按项目换了类型）文案跟着变。 */
export const useMaaFWFlavor = (type: MaybeRefOrGetter<ScriptType | string | null | undefined>) =>
  computed(() => resolveMaaFWFlavor(toValue(type)))
