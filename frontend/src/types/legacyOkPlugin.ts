/**
 * 已插件化 OK-WW / OK-EF 的旧宿主配置只读兼容形状。
 *
 * 这些类型不属于当前 OpenAPI：生产 API 返回 PluginScriptConfig。保留它们
 * 仅用于升级旧配置、历史快照和游戏中心展示，避免污染生成客户端。
 */
export interface LegacyOkScriptConfig {
  Info?: {
    Name?: string | null
    RootPath?: string | null
    ResourceName?: string | null
    ProjectLabel?: string | null
  } | null
  Script?: Record<string, never> | null
  Game?: {
    Enabled?: boolean | null
    LaunchBeforeTask?: boolean | null
    Path?: string | null
    Arguments?: string | null
    WaitTime?: number | null
  } | null
  Run?: {
    ProxyTimesLimit?: number | null
    RunTimesLimit?: number | null
    RunTimeLimit?: number | null
  } | null
}

export type OkwwConfig = LegacyOkScriptConfig
export type OkefConfig = LegacyOkScriptConfig
