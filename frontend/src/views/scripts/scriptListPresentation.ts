import { translate as t } from '@/i18n'
import { SCRIPT_LOGOS, SCRIPT_LABELS } from '@/utils/scriptLogos'
import type { ScriptListItem, ScriptListUser } from './scriptListModel'
import {
  isMaaFWFamily,
  resolveMaaFWFlavor,
  usesMaaFWProjectIcon,
  type MaaFWFlavorType,
} from '@/composables/useMaaFWFlavor'
import { buildMaaFWScriptIconUrl } from '@/utils/maafwProjectIcon'
export const getScriptLogo = (type: ScriptListItem['type']) => SCRIPT_LOGOS[type]

/** MaaFW 家族的头像：特调用注册表里声明的图标；通用 MaaFW 用项目自己的图标，取不到由调用方回退 */
export const getMaaFWScriptLogo = (script: Pick<ScriptListItem, 'id' | 'type'>) => {
  const flavor = resolveMaaFWFlavor(script.type)
  return usesMaaFWProjectIcon(flavor) ? buildMaaFWScriptIconUrl(script.id) : flavor.logo
}

export const getScriptLogoAlt = (type: ScriptListItem['type']) =>
  type === 'OkNte' ? 'ok-nte' : SCRIPT_LABELS[type]

const CONFIG_SOURCE_KEYS: Record<string, string> = {
  shared: 'core.comp.configSourceShared',
  independent: 'core.comp.configSourceIndependent',
  native: 'core.comp.configSourceNative',
}

const OVERLAY_SCRIPT_TYPES = new Set([
  'MAA',
  'SRC',
  'MaaEnd',
  'Okww',
  'OkNte',
  'BetterGI',
  'Whimbox',
])

export const isMaaEndPresetSupported = (script: ScriptListItem) => {
  const controllerType = script.type === 'MaaEnd' ? script.controllerType : null
  return script.type === 'MaaEnd' && controllerType === 'Win32-Front'
}

export const getConfigSource = (script: ScriptListItem, user: ScriptListUser): string => {
  let mode = user.Info.Base
  // MaaFW 始终使用账号配置；BAAH 始终使用账号绑定的脚本原生配置。
  if (isMaaFWFamily(script.type)) mode = 'independent'
  else if (script.type === 'BAAH') mode = 'native'
  // 这些专项没有共享配置来源，共享来源一律按账号配置运行。
  else if (['General', 'ZzzOd', 'Whimbox'].includes(script.type) && mode === 'shared')
    mode = 'independent'
  const sourceKey = mode ? CONFIG_SOURCE_KEYS[mode] : undefined
  return sourceKey ? t(sourceKey) : ''
}

// null 表示该专项没有覆写层或状态未知，此时不显示覆写段。
export const getOverlayState = (script: ScriptListItem, user: ScriptListUser): boolean | null =>
  OVERLAY_SCRIPT_TYPES.has(script.type) && user.Info.IfQuickConfig !== undefined
    ? user.Info.IfQuickConfig
    : null

export const getScriptTypeLabel = (script: ScriptListItem) => {
  const type = script.type
  if (type === 'Okww') return 'ok-ww'
  if (type === 'OkNte') return 'ok-nte'
  // MFW 家族显示项目实际的名字（引导页读到 interface 时记进 Info.ProjectLabel），没记过才显示
  // 类型标签（MFW / M9A …，不是内部类型名 MaaFW）
  if (isMaaFWFamily(type)) {
    return script.projectLabel?.trim() || resolveMaaFWFlavor(type).typeTagLabel
  }
  return type
}

// MaaFW 与各特调的标签颜色取自特调注册表
const SCRIPT_TYPE_TAG_COLORS: Record<Exclude<ScriptListItem['type'], MaaFWFlavorType>, string> = {
  MAA: 'blue',
  SRC: 'purple',
  MaaEnd: 'blue',
  Okww: 'blue',
  OkNte: 'blue',
  HSR: 'purple',
  BetterGI: 'gold',
  ZzzOd: 'volcano',
  BAAH: 'magenta',
  Whimbox: 'pink',
  General: 'green',
}

export const getScriptTypeTagColor = (type: ScriptListItem['type']) =>
  isMaaFWFamily(type)
    ? resolveMaaFWFlavor(type).typeTagColor
    : (SCRIPT_TYPE_TAG_COLORS[type] ?? 'green')

export const getMaaEndResourceLabel = (user: ScriptListUser): string => {
  return user.Info?.Resource || '官服'
}

export const getMaaEndResourceTagColor = (user: ScriptListUser): string => {
  switch (getMaaEndResourceLabel(user)) {
    case '官服':
    default:
      return 'blue'
  }
}

// 获取服务器标签颜色
export const getServerTagColor = (server: string | null | undefined): string => {
  switch (server) {
    // MAA服务器
    case 'Official':
      return 'blue'
    case 'Bilibili':
      return 'purple'
    case 'YoStarEN':
      return 'green'
    case 'YoStarJP':
      return 'red'
    case 'YoStarKR':
      return 'orange'
    case 'txwy':
      return 'gold'
    // SRC服务器
    case 'CN-Official':
      return 'blue'
    case 'CN-Bilibili':
      return 'purple'
    case 'VN-Official':
      return 'cyan'
    case 'OVERSEA-America':
      return 'green'
    case 'OVERSEA-Asia':
      return 'orange'
    case 'OVERSEA-Europe':
      return 'geekblue'
    case 'OVERSEA-TWHKMO':
      return 'gold'
    default:
      return 'gray'
  }
}

// 获取服务器显示名称
export const getServerDisplayName = (server: string | null | undefined): string => {
  switch (server) {
    // MAA服务器
    case 'Official':
      return '官服'
    case 'Bilibili':
      return 'B服'
    case 'YoStarEN':
      return '国际服'
    case 'YoStarJP':
      return '日服'
    case 'YoStarKR':
      return '韩服'
    case 'txwy':
      return '繁中服'
    // SRC服务器
    case 'CN-Official':
      return '官服'
    case 'CN-Bilibili':
      return 'B服'
    case 'VN-Official':
      return '越南服'
    case 'OVERSEA-America':
      return '美服'
    case 'OVERSEA-Asia':
      return '亚服'
    case 'OVERSEA-Europe':
      return '欧服'
    case 'OVERSEA-TWHKMO':
      return '港澳台服'
    default:
      return server || '未知'
  }
}

// ZzzOd：配置来源标签（独立模式/原生模式）
export const getZzzOdModeLabel = (user: ScriptListUser): string =>
  user.Info.Base === 'native' ? '原生模式' : '独立模式'

export const getZzzOdModeTagColor = (user: ScriptListUser): string =>
  user.Info.Base === 'native' ? 'gold' : 'blue'

// ZzzOd：字段类标签仅在独立来源展示（原生来源的事实源是一条龙原生配置）
export const isZzzOdUserMode = (user: ScriptListUser): boolean => user.Info.Base !== 'native'

const getZzzOdRegion = (user: ScriptListUser): string => user.Game?.GameRegion || 'cn'

export const getZzzOdRegionLabel = (user: ScriptListUser): string => {
  // 区服文案复用编辑页的 i18n 键，避免英文界面下标签显示中文
  const labels: Record<string, string> = {
    cn: t('core.edit.zzzodRegionCn'),
    cn_b: t('core.edit.zzzodRegionCnB'),
    us: t('core.edit.zzzodRegionUs'),
    eu: t('core.edit.zzzodRegionEu'),
    asia: t('core.edit.zzzodRegionAsia'),
    twhkmo: t('core.edit.zzzodRegionTwHkMo'),
  }
  return labels[getZzzOdRegion(user)] ?? labels.cn
}

// ZzzOd：B服账号名存 BilibiliAccountName，其余区服存 Account
export const getZzzOdAccountValue = (user: ScriptListUser): string =>
  getZzzOdRegion(user) === 'cn_b' ? user.Game?.BilibiliAccountName || '' : user.Game?.Account || ''
