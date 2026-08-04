export type HomeModuleKey = 'command' | 'quick' | 'satellite' | 'proxy' | 'arknights'

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

export interface HomeOverviewResponse {
  Stage: StageOverview
  StageByServer: Record<string, StageOverview>
  Proxy: Record<string, ProxyInfo>
}
