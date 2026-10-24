import type { GlobalConfig } from '@/api'
import type { AnalyticsEventProps } from '@/types/analytics'
import { beginAnalyticsOperation } from './analytics'

type Setting = AnalyticsEventProps['settings_change_finished']
const entries = [
  ['Start', 'IfSelfStart', 'startup', 'auto_start'],
  ['Start', 'IfMinimizeDirectly', 'startup', 'start_minimized'],
  ['UI', 'IfShowTray', 'close', 'show_tray'],
  ['UI', 'IfToTray', 'close', 'close_to_tray'],
  ['UI', 'IfHideCloseButton', 'close', 'hide_close'],
  ['Function', 'HistoryRetentionTime', 'other', 'history_retention'],
  ['Function', 'IfAllowSleep', 'scheduler', 'allow_sleep'],
  ['Function', 'IfBlockAd', 'emulator', 'block_ads'],
  ['Function', 'IfSilence', 'notification', 'silent'],
  ['Function', 'IfPersonalMss', 'scheduler', 'mss_personal'],
  ['Display', 'IfEnableVirtualDisplay', 'emulator', 'virtual_display'],
  ['Display', 'VirtualDisplayMode', 'emulator', 'virtual_display_mode'],
  ['Replay', 'Enabled', 'replay', 'replay_enabled'],
  ['Replay', 'MaxReplayCount', 'replay', 'replay_retention'],
  ['Replay', 'Port', 'replay', 'replay_connection'],
  ['Voice', 'Type', 'notification', 'voice'],
  ['Voice', 'Enabled', 'notification', 'voice'],
  ['Update', 'IfAutoUpdate', 'update', 'auto_update'],
  ['Update', 'Channel', 'update', 'update_channel'],
  ['Update', 'Source', 'update', 'update_source'],
  ['Update', 'GitHubMirror', 'network', 'mirror'],
  ['Update', 'PauseUntil', 'update', 'update_pause'],
  ['Update', 'ProxyAddress', 'network', 'proxy'],
] as const

/** 显式字段映射不采集凭据、地址、日期、音量等原值，也不观察遥测开关本身。 */
export function beginSettingsChanges(patch: GlobalConfig) {
  if (patch.Function && Object.prototype.hasOwnProperty.call(patch.Function, 'IfEnableTelemetry'))
    return []
  return entries.flatMap(([group, key, setting_kind, setting_key]) => {
    const values = patch[group] as Record<string, unknown> | null | undefined
    if (!values || !Object.prototype.hasOwnProperty.call(values, key)) return []
    const value = values[key]
    const operation = beginAnalyticsOperation('settings_change_finished')
    const value_kind: Setting['value_kind'] =
      value === true
        ? 'enabled'
        : value === false
          ? 'disabled'
          : value == null
            ? 'default'
            : 'custom'
    return [
      (outcome: Setting['outcome']) =>
        operation.finish({ setting_kind, setting_key, value_kind, outcome }),
    ]
  })
}
