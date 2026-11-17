type ChangelogData = Record<string, Record<string, string[]>>

export interface AppUpdateCheck {
  code: number
  message: string
  if_need_update: boolean
  latest_version: string
  update_info: ChangelogData
}
export interface AppUpdateSettings {
  forceCheck?: boolean
  currentVersion: string
  settings: {
    Source?: string | null
    Channel?: string | null
    MirrorChyanCDK?: string | null
    ProxyAddress?: string | null
  }
}
export interface AppUpdateSnapshot {
  status: 'idle' | 'downloading' | 'switchingSource' | 'completed' | 'failed' | 'cancelled'
  version: string | null
  source: string | null
  downloaded_size: number
  file_size: number
  speed: number
  file: string | null
  message: string | null
}
export interface AppUpdateEvent {
  type: 'progress' | 'completed' | 'failed' | 'cancelled'
  snapshot: AppUpdateSnapshot
}
