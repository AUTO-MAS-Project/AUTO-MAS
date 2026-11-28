// MaaFW 家族（通用 MFW 与 M9A、MSS）的判断与查表：一律看适配条目上的 `maafw` 标记
// （plugins/scriptAdapters.ts 的 MAAFW_FAMILY_ADAPTERS），公共代码不写 `type === 'XXX'` 这类分支。
// 脚本类型以实际类型为准（导入后后端会按项目内容原地换类型），未知 / 空类型按通用 MFW 处理。
import type { ScriptType } from '@/types/script'
import {
  MAAFW_FAMILY_ADAPTERS,
  type MaaFWAdapterProfile,
  type MaaFWFamilyType,
  type ScriptFrontendAdapter,
} from './scriptAdapters'

export type { MaaFWFamilyType } from './scriptAdapters'

/** 带家族标记的适配条目 */
export type MaaFWFamilyAdapter = ScriptFrontendAdapter & {
  type: MaaFWFamilyType
  maafw: MaaFWAdapterProfile
}

const FAMILY: readonly MaaFWFamilyAdapter[] = MAAFW_FAMILY_ADAPTERS.filter(
  (adapter): adapter is MaaFWFamilyAdapter => Boolean(adapter.maafw)
)
const ADAPTER_BY_TYPE = new Map<string, MaaFWFamilyAdapter>(
  FAMILY.map(adapter => [adapter.type, adapter])
)
/** 通用 MFW：未知类型的兜底（家族条目里的第一个） */
const GENERIC = FAMILY[0]

const USER_CONFIG_TYPES: ReadonlySet<string> = new Set(
  FAMILY.map(adapter => adapter.maafw.userConfigType)
)
// 含后端默认名从「新 X 脚本」改成「新 X 托管」之前的旧名
const DEFAULT_SCRIPT_NAMES: ReadonlySet<string> = new Set(
  FAMILY.flatMap(adapter => adapter.maafw.defaultScriptNames)
)

/** 是否由 MaaFW 引擎运行（MaaFW 本身或 M9A、MSS） */
export const isMaaFWFamily = (
  type: ScriptType | string | null | undefined
): type is MaaFWFamilyType => Boolean(type) && ADAPTER_BY_TYPE.has(type as string)

/** 按脚本类型取家族的适配条目；未知 / 空类型按通用 MFW */
export const resolveMaaFWAdapter = (
  type: ScriptType | string | null | undefined
): MaaFWFamilyAdapter => (type && ADAPTER_BY_TYPE.get(type)) || GENERIC

/** 家族全部适配条目，顺序固定为 MaaFW、M9A、MSS */
export const maafwFamilyAdapters = (): readonly MaaFWFamilyAdapter[] => FAMILY

/** 后端用户配置类名（M9A / MSS 的用户类都是 MaaFWUserConfig 的子类） */
export const maafwUserConfigTypes = (): ReadonlySet<string> => USER_CONFIG_TYPES

/** 后端脚本配置类名 → 脚本类型（脚本详情里只有配置类名） */
export const maafwScriptTypeByConfigType = (): Record<string, MaaFWFamilyType> =>
  Object.fromEntries(FAMILY.map(adapter => [adapter.maafw.scriptConfigType, adapter.type]))

/** 后端给新建托管起的默认名（含旧名）：脚本名还是其中之一时，读到 interface 后改成项目名 */
export const maafwDefaultScriptNames = (): ReadonlySet<string> => DEFAULT_SCRIPT_NAMES

/**
 * 头像用不用项目自己的图标（interface 顶层 icon）：M9A、MSS 用自己的 logo；通用 MFW
 * 跑的项目各不相同，用项目图标，取不到时回退到 MFW 图标。
 */
export const maafwUsesProjectIcon = (type: ScriptType | string | null | undefined): boolean =>
  Boolean(resolveMaaFWAdapter(type).maafw.usesProjectIcon)

/** 类型标签文字（MFW / M9A / MSS） */
export const maafwLabel = (type: ScriptType | string | null | undefined): string =>
  resolveMaaFWAdapter(type).metadata.label

/** 类型图标 */
export const maafwLogo = (type: ScriptType | string | null | undefined): string =>
  resolveMaaFWAdapter(type).metadata.logo
