export type HomeModuleKey =
  | 'command'
  | 'quick'
  | 'satellite'
  | 'proxy'
  | 'endfield'
  | 'starrail'
  | 'genshin'
  | 'zenless'
  | 'wutheringwaves'
  | 'nte'
  | 'reverse1999'
  | 'arknights'

export interface HomeLayoutConfig {
  moduleOrder: HomeModuleKey[]
  hiddenModules: HomeModuleKey[]
}

export interface HomeModuleDescriptor {
  key: HomeModuleKey
  title: string
  visible: boolean
}

export interface ActivityInfo {
  Tip: string
  StageName: string
  UtcStartTime: string
  UtcExpireTime: string
  TimeZone: number
}

export interface ActivityItem {
  Display: string
  Value: string
  Drop: string
  DropName: string
  Activity: ActivityInfo
}

export interface ResourceItem {
  Display: string
  Value: string
  Drop: string
  DropName: string
  Activity: Pick<ActivityInfo, 'Tip' | 'StageName'>
}

export interface StageOption {
  label: string
  value: string | null
}

export interface StageOverview {
  Activity: ActivityItem[]
  Resource: ResourceItem[]
  Options: StageOption[]
}

export interface ProxyInfo {
  LastProxyDate: string
  ProxyTimes: number
  ErrorTimes: number
  ErrorInfo: Record<string, unknown>
}

export interface EndfieldActivityItem {
  Id: string
  Name: string
  StartTime: string
  EndTime: string
  ImageUrl: string
  Tags: string[]
}

export interface EndfieldPoolItem {
  Id: string
  Name: string
  Type: string
  StartTime: string
  EndTime: string
  ImageUrl: string
  UpCharacters: string[]
}

export interface EndfieldActivityOverview {
  Available: boolean
  Stale: boolean
  Message: string
  Version: string
  UpdatedAt: string
  SourceName: string
  SourceUrl: string
  Pools: EndfieldPoolItem[]
  Activities: EndfieldActivityItem[]
}

export const createEmptyEndfieldActivityOverview = (): EndfieldActivityOverview => ({
  Available: false,
  Stale: false,
  Message: '',
  Version: '',
  UpdatedAt: '',
  SourceName: 'AKEData',
  SourceUrl: 'https://www.akedata.wiki',
  Pools: [],
  Activities: [],
})

export interface SraActivityItem {
  name: string
  description: string
  startTime: string
  endTime: string
  cover?: string
}

export interface SraActivityOverview {
  Available: boolean
  Stale: boolean
  Message: string
  version: string
  versionName: string
  cover?: string
  startTime: string
  endTime: string
  activities: SraActivityItem[]
}

export type StarRailActivityOverview = SraActivityOverview
export type GenshinActivityOverview = SraActivityOverview
export type ZenlessZoneZeroActivityOverview = SraActivityOverview
export type WutheringWavesActivityOverview = SraActivityOverview
export type NevernessToEvernessActivityOverview = SraActivityOverview
export type Reverse1999ActivityOverview = SraActivityOverview

export const createEmptySraActivityOverview = (): SraActivityOverview => ({
  Available: false,
  Stale: false,
  Message: '',
  version: '',
  versionName: '',
  cover: '',
  startTime: '',
  endTime: '',
  activities: [],
})

/** @deprecated 请改用 createEmptySraActivityOverview */
export const createEmptyStarRailActivityOverview = createEmptySraActivityOverview

export interface HomeOverviewResponse {
  Stage: StageOverview
  StageByServer: Record<string, StageOverview>
  Proxy: Record<string, ProxyInfo>
  Endfield: EndfieldActivityOverview
  StarRail: StarRailActivityOverview
  Genshin: GenshinActivityOverview
  ZenlessZoneZero: ZenlessZoneZeroActivityOverview
  WutheringWaves: WutheringWavesActivityOverview
  NevernessToEverness: NevernessToEvernessActivityOverview
  Reverse1999: Reverse1999ActivityOverview
}
