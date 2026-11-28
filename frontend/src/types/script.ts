// 脚本类型定义
import type {
  HSRConfig,
  HSRConfig_TaskMapping,
  MaaConfig,
  GeneralConfig,
  ScriptCreateIn,
  PluginProvidedScriptType,
  ScriptGetOut,
  ScriptIndexItem as ApiScriptIndexItem,
} from '@/api'

export type BuiltinScriptType = `${ScriptCreateIn['type']}`
export type ScriptType = PluginProvidedScriptType['scriptKey']

export const PLUGIN_EDITOR_SCRIPT_TYPES = [
  'SRC',
  'MAA',
  'Whimbox',
  'BetterGI',
  'MaaFW',
  'M9A',
  'MSS',
  'MaaEnd',
  'ZzzOd',
  'BAAH',
] as const satisfies readonly BuiltinScriptType[]
export type PluginEditorScriptType = (typeof PLUGIN_EDITOR_SCRIPT_TYPES)[number]

// 草稿由显式默认值初始化；路径保留 null，其余可编辑字段要求有值。
type DraftGroup<T, Nullable extends keyof T = never> = {
  [K in keyof T]-?: K extends Nullable ? Exclude<T[K], undefined> : NonNullable<T[K]>
}

export interface MAAScriptConfig {
  Info: DraftGroup<NonNullable<MaaConfig['Info']>, 'Path'>
  Run: DraftGroup<NonNullable<MaaConfig['Run']>>
  Update: DraftGroup<
    Pick<
      NonNullable<MaaConfig['Update']>,
      'TakeoverEnabled' | 'MirrorChyanCDK' | 'Channel' | 'PackageMode'
    >
  >
}

export interface GeneralScriptConfig {
  Game: DraftGroup<NonNullable<GeneralConfig['Game']>, 'Path'>
  Info: DraftGroup<NonNullable<GeneralConfig['Info']>, 'RootPath'>
  Run: DraftGroup<NonNullable<GeneralConfig['Run']>>
  Script: DraftGroup<NonNullable<GeneralConfig['Script']>, 'ConfigPath' | 'LogPath' | 'ScriptPath'>
}

// HSR 脚本配置（后端已通过 HSRConfig OpenAPI 暴露类型）
export type HSRScriptConfig = HSRConfig

// HSR TaskMapping 默认值（Daily / ReceiveRewards / DivergentUniverse / CurrencyWars 默认走 SRA）
export const DEFAULT_HSR_TASK_MAPPING: HSRConfig_TaskMapping = {
  Daily: 'SRA',
  ReceiveRewards: 'SRA',
  DivergentUniverse: 'SRA',
  CurrencyWars: 'SRA',
}

/**
 * 解析 HSR 单个模块的执行脚本。
 * current 可用且在 available 中时优先保留，否则回退到仍可用的脚本。
 */
export function resolveTaskMappingValue(
  current: string | undefined,
  available: Set<'M7A' | 'SRA'>
): 'M7A' | 'SRA' | undefined {
  if (current && available.has(current as 'M7A' | 'SRA')) {
    return current as 'M7A' | 'SRA'
  }
  if (available.has('M7A')) return 'M7A'
  if (available.has('SRA')) return 'SRA'
  return undefined
}

// API 读取用于展示，不充当已初始化草稿或更新 Payload。
export interface ScriptDetail extends Pick<ApiScriptIndexItem, 'uid' | 'activityGame'> {
  type: ScriptType
  scriptConfigType: string
  name: string
  config: ScriptGetOut['data'][string]
}
