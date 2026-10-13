import type { Setting_Input, Setting_Output, UiHintsMap } from '@/api'

/**
 * Settings used by the renderer. The backend contract remains snake_case;
 * this view model keeps the existing settings components readable while the
 * adapter below is the only place that translates the wire format.
 */
export interface SettingsViewModel {
  /** Backend-declared component hints, grouped by persisted config group. */
  uiHints?: UiHintsMap
  UI?: {
    IfShowTray?: boolean
    IfToTray?: boolean
    IfHideCloseButton?: boolean
  }
  Start?: {
    IfSelfStart?: boolean
    IfMinimizeDirectly?: boolean
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
  Voice?: {
    Enabled?: boolean
    Type?: 'simple' | 'noisy'
  }
  Display?: {
    IfEnableVirtualDisplay?: boolean
    VirtualDisplayMode?: '1920x1080@60' | '1920x1080@30'
  }
  Notify?: Record<string, unknown> & {
    SendTaskResultTime?: string
    IfSendStatistic?: boolean
    IfSendSixStar?: boolean
    IfPushPlyer?: boolean
    IfSendMail?: boolean
    IfKoishiSupport?: boolean
    KoishiServerAddress?: string
    KoishiToken?: string
    IfOpenClawQQ?: boolean
    OpenClawQQAppId?: string
    OpenClawQQClientSecret?: string
    OpenClawQQTargetOpenId?: string
    SmtpServerAddress?: string
    AuthorizationCode?: string
    FromAddress?: string
    ToAddress?: string
    IfServerChan?: boolean
    ServerChanKey?: string
    Test?: boolean
  }
  Update?: {
    IfAutoUpdate?: boolean
    Source?: 'GitHub' | 'MirrorChyan' | 'AutoSite' | 'CNB'
    Channel?: 'stable' | 'beta'
    ProxyAddress?: string
    MirrorChyanCDK?: string
    GithubToken?: string
    /** Persisted by the new updates group for the update checker. */
    PauseUntil?: string
    /** Kept for old local UI consumers; it is not sent to the new API. */
    GitHubMirror?: string
  }
  Language?: { Locale?: string }
  [key: string]: unknown
}

export type SettingsCategory =
  | 'UI'
  | 'Start'
  | 'Function'
  | 'Voice'
  | 'Display'
  | 'Notify'
  | 'Update'
  | 'Language'

export type SettingsPatch = Partial<SettingsViewModel>
type UpdateView = NonNullable<SettingsViewModel['Update']>

const groupCategoryMap: Record<string, SettingsCategory> = {
  appearance: 'UI',
  updates: 'Update',
}

export function settingsCategoryForGroup(group: string): SettingsCategory | undefined {
  return groupCategoryMap[group] ?? (group ? (group[0].toUpperCase() + group.slice(1) as SettingsCategory) : undefined)
}

const readGroup = (data: Setting_Output | Record<string, unknown>, key: string) => {
  const value = data[key]
  return value && typeof value === 'object' ? (value as Record<string, unknown>) : {}
}

const pick = (group: Record<string, unknown>, key: string) => group[key]

export function fromBackendSettings(data: Setting_Output | Record<string, unknown>): SettingsViewModel {
  const uiHintsGroup = readGroup(data, 'ui')
  const appearance = readGroup(data, 'appearance')
  const start = readGroup(data, 'start')
  const fn = readGroup(data, 'function')
  const voice = readGroup(data, 'voice')
  const display = readGroup(data, 'display')
  const notify = readGroup(data, 'notify')
  const updates = readGroup(data, 'updates')
  const language = readGroup(data, 'language')

  return {
    uiHints: (uiHintsGroup.hints as UiHintsMap | undefined) ?? undefined,
    UI: {
      IfShowTray: pick(appearance, 'if_show_tray') as boolean | undefined,
      IfToTray: pick(appearance, 'if_to_tray') as boolean | undefined,
      IfHideCloseButton: pick(appearance, 'if_hide_close_button') as boolean | undefined,
    },
    Start: {
      IfSelfStart: pick(start, 'if_self_start') as boolean | undefined,
      IfMinimizeDirectly: pick(start, 'if_minimize_directly') as boolean | undefined,
    },
    Function: {
      HistoryRetentionTime: pick(fn, 'history_retention_time') as number | undefined,
      IfSilence: pick(fn, 'if_silence') as boolean | undefined,
      IfAllowSleep: pick(fn, 'if_allow_sleep') as boolean | undefined,
      IfAgreeBilibili: pick(fn, 'if_agree_bilibili') as boolean | undefined,
      IfBlockAd: pick(fn, 'if_block_ad') as boolean | undefined,
    },
    Voice: {
      Enabled: pick(voice, 'enabled') as boolean | undefined,
      Type: pick(voice, 'type') as 'simple' | 'noisy' | undefined,
    },
    Display: {
      IfEnableVirtualDisplay: pick(display, 'if_enable_virtual_display') as boolean | undefined,
      VirtualDisplayMode: pick(display, 'virtual_display_mode') as
        | '1920x1080@60'
        | '1920x1080@30'
        | undefined,
    },
    Notify: Object.fromEntries(
      Object.entries(notify).map(([key, value]) => [notifyViewKey(key), value])
    ) as SettingsViewModel['Notify'],
    Update: {
      IfAutoUpdate: pick(updates, 'if_auto_update') as boolean | undefined,
      Source: pick(updates, 'source') as UpdateView['Source'],
      Channel: pick(updates, 'channel') as UpdateView['Channel'],
      ProxyAddress: pick(updates, 'proxy_address') as string | undefined,
      MirrorChyanCDK: pick(updates, 'mirror_chyan_cdk') as string | undefined,
      GithubToken: pick(updates, 'github_token') as string | undefined,
      PauseUntil: pick(updates, 'pause_until') as string | undefined,
    },
    Language: { Locale: pick(language, 'locale') as string | undefined },
  }
}

const fieldMap: Record<string, Record<string, string>> = {
  UI: {
    IfShowTray: 'if_show_tray',
    IfToTray: 'if_to_tray',
    IfHideCloseButton: 'if_hide_close_button',
  },
  Start: { IfSelfStart: 'if_self_start', IfMinimizeDirectly: 'if_minimize_directly' },
  Function: {
    HistoryRetentionTime: 'history_retention_time',
    IfSilence: 'if_silence',
    IfAllowSleep: 'if_allow_sleep',
    IfAgreeBilibili: 'if_agree_bilibili',
    IfBlockAd: 'if_block_ad',
  },
  Voice: { Enabled: 'enabled', Type: 'type' },
  Display: { IfEnableVirtualDisplay: 'if_enable_virtual_display', VirtualDisplayMode: 'virtual_display_mode' },
  Notify: {
    SendTaskResultTime: 'send_task_result_time',
    IfSendStatistic: 'if_send_statistic',
    IfSendSixStar: 'if_send_six_star',
    IfPushPlyer: 'if_push_plyer',
    IfSendMail: 'if_send_mail',
    IfKoishiSupport: 'if_koishi_support',
    KoishiServerAddress: 'koishi_server_address',
    KoishiToken: 'koishi_token',
    IfOpenClawQQ: 'if_openclaw_qq',
    OpenClawQQAppId: 'openclaw_qq_app_id',
    OpenClawQQClientSecret: 'openclaw_qq_client_secret',
    OpenClawQQTargetOpenId: 'openclaw_qq_target_open_id',
    SmtpServerAddress: 'smtp_server_address',
    AuthorizationCode: 'authorization_code',
    FromAddress: 'from_address',
    ToAddress: 'to_address',
    IfServerChan: 'if_server_chan',
    ServerChanKey: 'server_chan_key',
    Test: 'test',
  },
  Update: {
    IfAutoUpdate: 'if_auto_update',
    Source: 'source',
    Channel: 'channel',
    ProxyAddress: 'proxy_address',
    MirrorChyanCDK: 'mirror_chyan_cdk',
    GithubToken: 'github_token',
    PauseUntil: 'pause_until',
  },
  Language: { Locale: 'locale' },
}

const notifyViewKey = (key: string): string => {
  const acronymKeys: Record<string, string> = {
    if_openclaw_qq: 'IfOpenClawQQ',
    openclaw_qq_app_id: 'OpenClawQQAppId',
    openclaw_qq_client_secret: 'OpenClawQQClientSecret',
    openclaw_qq_target_open_id: 'OpenClawQQTargetOpenId',
  }
  return acronymKeys[key] ?? key.replace(/(^|_)([a-z])/g, (_, _prefix: string, letter: string) => letter.toUpperCase())
}

export function settingsViewKey(group: string, field: string): string {
  // 读写使用同一张字段表，保留 CDK、QQ 等缩写的视图键名。
  const category = settingsCategoryForGroup(group)
  const mapped = Object.entries(category ? fieldMap[category] ?? {} : {})
    .find(([, backendField]) => backendField === field)?.[0]
  if (mapped) return mapped
  if (group === 'notify') return notifyViewKey(field)
  return field.replace(/(^|_)([a-z])/g, (_, _prefix: string, letter: string) => letter.toUpperCase())
}

export function toBackendPatch(category: SettingsCategory, changes: Record<string, unknown>): Setting_Input {
  const targetGroup =
    category === 'UI' ? 'appearance' : category === 'Update' ? 'updates' : category.toLowerCase()
  const mapped = Object.fromEntries(
    Object.entries(changes)
      .map(([key, value]) => [fieldMap[category]?.[key], value] as const)
      .filter(([key]) => Boolean(key))
  )
  return { [targetGroup]: mapped } as Setting_Input
}
