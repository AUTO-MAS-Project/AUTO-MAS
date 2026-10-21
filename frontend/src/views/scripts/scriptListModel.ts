import { UserIndexItem } from '@/api'
import type { MaaUserConfig_Info, UserGetOut, ZzzOdUserConfig_Game } from '@/api'
import type { ScriptDetail, ScriptType } from '@/types/script'
import { isMaaFWFamily, maafwUserConfigTypes } from '@/composables/useMaaFWFlavor'

/** 列表只读投影；用户操作用 scriptId / id 定位，不能作为配置整体回写。 */
export interface ScriptListUser {
  id: string
  scriptId: string
  name: string
  Info: Pick<
    MaaUserConfig_Info,
    'Name' | 'Id' | 'Password' | 'Status' | 'Tag' | 'IfQuickConfig'
  > & {
    Base?: string | null
    Server?: string | null
    Resource?: string | null
  }
  Game?: Pick<ZzzOdUserConfig_Game, 'GameRegion' | 'Account' | 'BilibiliAccountName'>
}

export interface ScriptListItem {
  id: string
  type: ScriptType
  name: string
  projectLabel?: string | null
  controllerType?: string | null
  users: ScriptListUser[]
  /** 保留局部读取失败的事实；本批沿用现有空列表呈现。 */
  usersLoadFailed: boolean
}

const ACCOUNT_CONFIG_TYPES = new Set([
  'MaaUserConfig',
  'SrcUserConfig',
  'MaaEndUserConfig',
  'OkwwUserConfig',
  'OkNteUserConfig',
  'HSRUserConfig',
  'BetterGIUserConfig',
])

const PASSWORD_CONFIG_TYPES = new Set(['MaaUserConfig', 'SrcUserConfig', 'MaaEndUserConfig'])

const BASE_DEFAULTS: Partial<Record<UserIndexItem.type, string>> = {
  MaaUserConfig: 'shared',
  SrcUserConfig: 'shared',
  MaaEndUserConfig: 'shared',
  OkwwUserConfig: 'shared',
  OkNteUserConfig: 'shared',
  WhimboxUserConfig: 'shared',
  ZzzOdUserConfig: 'independent',
}

const SERVER_DEFAULTS: Partial<Record<UserIndexItem.type, string>> = {
  MaaUserConfig: 'Official',
  SrcUserConfig: 'CN-Official',
}

const USER_CONFIG_TYPES: ReadonlySet<string> = new Set([
  ...Object.values(UserIndexItem.type),
  ...maafwUserConfigTypes(),
])

// 老列表对普通专项只补 undefined，MaaFW 的名称则把 null / 空串也当作缺省。
const defaultIfMissing = <T>(value: T | undefined, fallback: T): T =>
  value === undefined ? fallback : value

export function toScriptListUser(
  scriptId: string,
  index: UserGetOut['index'][number],
  config: UserGetOut['data'][string] | undefined
): ScriptListUser | null {
  if (!config || !USER_CONFIG_TYPES.has(index.type)) return null
  const info = config.Info
  const fallbackName = `用户${index.uid}`
  const isMaaFW = maafwUserConfigTypes().has(index.type)
  const hasAccount = ACCOUNT_CONFIG_TYPES.has(index.type)
  const baseDefault = BASE_DEFAULTS[index.type]
  const serverDefault = SERVER_DEFAULTS[index.type]
  const quickConfig = info && 'IfQuickConfig' in info ? info.IfQuickConfig : undefined
  const game = index.type === 'ZzzOdUserConfig' && 'Game' in config ? config.Game : undefined

  return {
    id: index.uid,
    scriptId,
    name: info?.Name || fallbackName,
    Info: {
      Name: isMaaFW ? info?.Name || fallbackName : defaultIfMissing(info?.Name, fallbackName),
      Status: isMaaFW ? (info?.Status ?? true) : defaultIfMissing(info?.Status, true),
      Id: hasAccount ? defaultIfMissing(info && 'Id' in info ? info.Id : undefined, '') : undefined,
      Password: PASSWORD_CONFIG_TYPES.has(index.type)
        ? defaultIfMissing(info && 'Password' in info ? info.Password : undefined, '')
        : undefined,
      Base:
        baseDefault === undefined
          ? (info?.Base ?? undefined)
          : defaultIfMissing(info?.Base, baseDefault),
      Server:
        serverDefault === undefined
          ? undefined
          : defaultIfMissing(info && 'Server' in info ? info.Server : undefined, serverDefault),
      Resource:
        index.type === 'MaaEndUserConfig'
          ? defaultIfMissing(info && 'Resource' in info ? info.Resource : undefined, '')
          : undefined,
      IfQuickConfig:
        typeof quickConfig === 'boolean'
          ? quickConfig
          : quickConfig === undefined && index.type === 'OkwwUserConfig'
            ? true
            : undefined,
      Tag: defaultIfMissing(info?.Tag, null),
    },
    ...(index.type === 'ZzzOdUserConfig'
      ? {
          Game: {
            GameRegion: defaultIfMissing(game?.GameRegion, 'cn'),
            Account: defaultIfMissing(game?.Account, ''),
            BilibiliAccountName: defaultIfMissing(game?.BilibiliAccountName, ''),
          },
        }
      : {}),
  }
}

export function toScriptListItem(
  script: ScriptDetail,
  users: ScriptListUser[],
  usersLoadFailed = false
): ScriptListItem {
  const config = script.config
  return {
    id: script.uid,
    type: script.type,
    name: script.name,
    projectLabel:
      isMaaFWFamily(script.type) && config?.Info && 'ProjectLabel' in config.Info
        ? config.Info.ProjectLabel
        : undefined,
    controllerType:
      script.type === 'MaaEnd' &&
      config &&
      'Game' in config &&
      config.Game &&
      'ControllerType' in config.Game
        ? config.Game.ControllerType
        : undefined,
    users,
    usersLoadFailed,
  }
}
