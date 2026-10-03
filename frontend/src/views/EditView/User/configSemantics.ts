/**
 * base ⊕ overlay（3×2）子态的生效语义文案。
 *
 * 权威语义见开发者文档 developer/config-semantics.html：
 * task_config = base ⊕ overlay，overlay 优先于 base；未启用 overlay 时任务直接使用 base，
 * 启用时按账号读覆盖字段合并后启动任务，任务结束（含失败/取消/异常）恢复基础配置。
 *
 * 六个子态各给一整条用户可读的说明（标题 + 具体运作方式），而不是「A + B」式短语拼接：
 * 用户真正要弄明白的是「这份配置是谁的、任务期间怎么用、结束会不会留下改动」。
 *
 * 单独成模块是为了能脱离组件直接对六种组合做表驱动断言。
 */
export type ConfigBaseKind = 'shared' | 'independent' | 'native'

/**
 * base 取值 → 语义种类。三态卡片的 value 就是后端 wire 值（脚本/用户/直控）；
 * 默认两态卡片用布尔（true = 用户级 = 独立，false = 直控 = 原生）。
 */
const BASE_KINDS: Record<string, ConfigBaseKind> = {
  脚本: 'shared',
  用户: 'independent',
  直控: 'native',
  true: 'independent',
  false: 'native',
}

/** 每个子态的 [标题 key, 说明 key]（off = 未启用覆写常规配置，on = 已启用） */
const SEMANTICS_KEYS: Record<
  ConfigBaseKind,
  { off: readonly [string, string]; on: readonly [string, string] }
> = {
  shared: {
    off: ['edit.configSemanticsSharedOffTitle', 'edit.configSemanticsSharedOffDesc'],
    on: ['edit.configSemanticsSharedOnTitle', 'edit.configSemanticsSharedOnDesc'],
  },
  independent: {
    off: ['edit.configSemanticsIndependentOffTitle', 'edit.configSemanticsIndependentOffDesc'],
    on: ['edit.configSemanticsIndependentOnTitle', 'edit.configSemanticsIndependentOnDesc'],
  },
  native: {
    off: ['edit.configSemanticsNativeOffTitle', 'edit.configSemanticsNativeOffDesc'],
    on: ['edit.configSemanticsNativeOnTitle', 'edit.configSemanticsNativeOnDesc'],
  },
}

/**
 * 每个 base 来源的「界面入口」说明 key：打开脚本自带界面时改的是哪一份配置。
 * 后端 owner 规则决定这一点随来源变化（如 MaaEnd 脚本态写 Default 共享目录、用户态写该账号目录、直控不回写）。
 */
const SEMANTICS_GUI_KEYS: Record<ConfigBaseKind, string> = {
  shared: 'edit.configSemanticsSharedGui',
  independent: 'edit.configSemanticsIndependentGui',
  native: 'edit.configSemanticsNativeGui',
}

export type Translate = (key: string, named?: Record<string, unknown>) => string

export type ConfigSemantics = {
  /** 子态标题，如「共享基础配置 + 本账号的覆盖层」 */
  formula: string
  /** 该子态具体怎么运作：谁拥有配置、覆盖什么、结束怎么恢复、会不会留下改动 */
  note: string
  /** 界面入口说明：打开脚本自带界面时，编辑保存的是哪一份配置（随 base 来源变化） */
  gui: string
}

/**
 * @param modelValue 当前 base 取值（Info.Mode 的 wire 值或默认两态的布尔）
 * @param quickConfig Info.IfQuickConfig；undefined 表示该专项未接入 overlay，没有 3×2 子态，不渲染语义
 */
export const composeConfigSemantics = (
  modelValue: boolean | string,
  quickConfig: boolean | undefined,
  t: Translate
): ConfigSemantics => {
  const kind = BASE_KINDS[String(modelValue)]
  // 未接入 overlay 的专项（General / HSR / BAAH / ZzzOd）没有覆写层：off 文案里的「不覆写常规配置时
  // MAS 仅启动脚本」对它们不成立——这些页面本身就是 MAS 在写配置，于是整块语义面板不渲染。
  if (!kind || quickConfig === undefined) return { formula: '', note: '', gui: '' }

  const [titleKey, descKey] = SEMANTICS_KEYS[kind][quickConfig === true ? 'on' : 'off']
  return { formula: t(titleKey), note: t(descKey), gui: t(SEMANTICS_GUI_KEYS[kind]) }
}
