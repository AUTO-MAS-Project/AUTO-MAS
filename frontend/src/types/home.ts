export type HomeModuleKey = 'command' | 'quick' | 'satellite' | 'proxy' | 'endfield' | 'arknights'

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

export interface HomeOverviewResponse {
  Stage: StageOverview
  StageByServer: Record<string, StageOverview>
  Proxy: Record<string, ProxyInfo>
  Endfield: EndfieldActivityOverview
}
