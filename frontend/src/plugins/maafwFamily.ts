import { SCRIPT_METADATA } from '@/utils/scriptMetadata'

const FAMILY = ['MaaFW', 'M9A', 'MSS'] as const
export type MaaFWFamilyType = (typeof FAMILY)[number]

const USER_CONFIG_TYPES: ReadonlySet<string> = new Set(FAMILY.map(type => type + 'UserConfig'))

/** 是否由 MaaFW 引擎运行（MaaFW 本身或 M9A、MSS） */
export const isMaaFWFamily = (type: string | null | undefined): type is MaaFWFamilyType =>
  FAMILY.some(member => member === type)

export const maafwTypeOrDefault = (type: string | null | undefined): MaaFWFamilyType =>
  isMaaFWFamily(type) ? type : 'MaaFW'

/** 后端用户配置类名（M9A / MSS 的用户类都是 MaaFWUserConfig 的子类） */
export const maafwUserConfigTypes = (): ReadonlySet<string> => USER_CONFIG_TYPES

/** 后端脚本配置类名 → 脚本类型（脚本详情里只有配置类名） */
export const maafwScriptTypeByConfigType = (): Record<string, MaaFWFamilyType> =>
  Object.fromEntries(FAMILY.map(type => [type + 'Config', type]))

/** 通用 MFW 使用项目图标，取不到时回退到 MFW 图标。 */
export const maafwUsesProjectIcon = (type: string | null | undefined): boolean =>
  maafwTypeOrDefault(type) === 'MaaFW'

export const maafwLabel = (type: string | null | undefined): string =>
  SCRIPT_METADATA[maafwTypeOrDefault(type)].label

export const maafwLogo = (type: string | null | undefined): string =>
  SCRIPT_METADATA[maafwTypeOrDefault(type)].logo
