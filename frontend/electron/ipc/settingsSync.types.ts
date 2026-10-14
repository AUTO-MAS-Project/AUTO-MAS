/** 设置页、preload 和主进程共用的配置同步 IPC 参数。 */
export interface SettingsSyncPayload {
  UI?: {
    IfShowTray?: boolean
    IfToTray?: boolean
    IfHideCloseButton?: boolean
  }
  Start?: {
    IfSelfStart?: boolean
    IfMinimizeDirectly?: boolean
  }
  Update?: {
    IfAutoUpdate?: boolean
    Source?: 'GitHub' | 'MirrorChyan' | 'AutoSite' | 'CNB'
    Channel?: 'stable' | 'beta'
    ProxyAddress?: string
    MirrorChyanCDK?: string
    GithubToken?: string
    PauseUntil?: string
    GitHubMirror?: string
  }
  Function?: {
    HistoryRetentionTime?: number
    IfSilence?: boolean
    IfAllowSleep?: boolean
    IfAgreeBilibili?: boolean
    IfBlockAd?: boolean
    IfEnableTelemetry?: boolean
    IfPersonalMss?: boolean
  }
}
