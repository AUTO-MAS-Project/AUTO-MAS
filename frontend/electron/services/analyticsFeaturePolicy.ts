/** 固定类别同时约束调用方类型与主进程校验；不接受业务对象或原始文本。 */
const duration = ['<1s', '1-5s', '5-30s', '30-120s', '>120s'] as const
const outcomes = [
  'success',
  'failure',
  'unknown',
  'accepted',
  'rejected',
  'cancelled',
  'partial',
  'blocked',
  'skipped',
  'not_found',
  'current',
  'updated',
  'unsupported',
] as const
const count = ['0', '1', '2-5', '6-20', '20+'] as const
const script = [
  'MAA',
  'SRC',
  'MaaEnd',
  'HSR',
  'General',
  'BAAH',
  'MaaFW',
  'M9A',
  'MSS',
  'BetterGI',
  'Okww',
  'OkNte',
  'ZzzOd',
  'Whimbox',
  'unknown',
  'multi',
  'none',
] as const
const family = ['mumu', 'leidian', 'bluestacks', 'avd', 'multi', 'unknown'] as const
const plan = [
  'MaaPlanConfig',
  'MaaEndPlanConfig',
  'BAAHPlanConfig',
  'MSSPlanConfig',
  'multi',
  'unknown',
] as const
const finished = <T extends Record<string, readonly string[]>>(fields: T) => ({
  ...fields,
  outcome: outcomes,
  duration_bucket: duration,
})

export const featureAnalyticsSchemas = {
  backend_restart_finished: finished({ reason_kind: ['manual', 'recovery', 'update'] as const }),
  runtime_alignment_finished: finished({
    operation: ['align', 'manual_update'] as const,
    release_channel: ['stable', 'beta', 'unknown'] as const,
  }),
  backend_update_finished: finished({
    trigger_kind: ['start', 'retry', 'restart'] as const,
    phase: ['shutdown', 'bootstrap', 'restart', 'complete', 'unknown'] as const,
  }),
  renderer_recovery_decided: finished({
    reason_kind: ['crashed', 'oom', 'killed', 'launch_failed', 'other'] as const,
    recovery_action: ['reload', 'give_up'] as const,
    count_bucket: count,
  }),
  renderer_responsiveness_changed: finished({ state: ['unresponsive', 'responsive'] as const }),
  app_close_finished: finished({ close_kind: ['user', 'backend', 'force'] as const }),
  tray_action_requested: finished({
    action_kind: ['show', 'hide', 'stopAll', 'startTask', 'restartApp', 'quit', 'unknown'] as const,
  }),
  stop_all_requested: finished({
    source: ['shortcut', 'tray', 'scheduler', 'home', 'mascot', 'unknown'] as const,
  }),
  virtual_display_action_finished: finished({ action: ['check', 'remove'] as const }),
  virtual_display_prompt_answered: finished({ choice: ['remove', 'cancel', 'keep'] as const }),
  system_resume_recovery_finished: finished({
    recovery_kind: ['reconnect', 'backend_restart', 'skipped'] as const,
  }),
  script_manage_finished: finished({
    action: ['delete', 'reorder'] as const,
    script_type: script,
    count_bucket: count,
  }),
  user_manage_finished: finished({
    action: [
      'delete',
      'reorder',
      'enable',
      'disable',
      'batch_enable',
      'batch_disable',
      'batch_delete',
    ] as const,
    script_type: script,
    count_bucket: count,
  }),
  config_mode_changed: finished({
    script_type: script,
    mode: ['script', 'user', 'native', 'view', 'direct', 'unknown'] as const,
  }),
  queue_time_set_changed: finished({
    action: ['create', 'delete', 'update', 'reorder'] as const,
    count_bucket: count,
  }),
  plan_edit_finished: finished({
    plan_type: plan,
    view_kind: ['simple', 'complex', 'unknown'] as const,
    operation_kind: ['save', 'import', 'reset'] as const,
  }),
  emulator_discovery_finished: finished({
    emulator_family: family,
    action: ['search', 'import', 'create', 'update', 'delete', 'reorder'] as const,
    count_bucket: count,
  }),
  emulator_operation_result: finished({
    emulator_family: family,
    operation: ['open', 'close', 'show', 'hide', 'store', 'unknown'] as const,
  }),
  emulator_operation_observed_finished: finished({
    emulator_family: family,
    operation: ['open', 'close', 'show', 'hide', 'unknown'] as const,
  }),
  emulator_instance_manage_finished: finished({
    emulator_family: family,
    action: ['create', 'delete', 'settings', 'batch_settings'] as const,
    scope: ['single', 'batch'] as const,
    count_bucket: count,
  }),
  emulator_guard_changed: finished({
    guard_kind: ['stable', 'config'] as const,
    action: ['enable', 'disable', 'capture', 'apply'] as const,
  }),
  avd_root_added: finished({ reason_kind: ['validated', 'invalid', 'unknown'] as const }),
  game_sign_requested: finished({ trigger_kind: ['manual'] as const }),
  community_account_manage_finished: finished({
    action: ['create', 'save', 'delete', 'enable', 'disable', 'reorder'] as const,
  }),
  community_activity_requested: finished({
    operation_kind: ['refresh', 'sign', 'reward', 'action'] as const,
  }),
  settings_change_finished: finished({
    setting_key: [
      'auto_start',
      'start_minimized',
      'show_tray',
      'close_to_tray',
      'hide_close',
      'close_confirmation',
      'history_retention',
      'allow_sleep',
      'block_ads',
      'silent',
      'mss_personal',
      'virtual_display',
      'virtual_display_mode',
      'replay_enabled',
      'replay_retention',
      'replay_connection',
      'voice',
      'auto_update',
      'update_channel',
      'update_source',
      'mirror',
      'update_pause',
      'proxy',
      'performance_effects',
      'other',
    ] as const,
    value_kind: ['enabled', 'disabled', 'default', 'custom'] as const,
    setting_kind: [
      'startup',
      'close',
      'scheduler',
      'emulator',
      'notification',
      'replay',
      'performance',
      'update',
      'network',
      'other',
    ] as const,
  }),
  appearance_preference_changed: finished({
    preference_kind: ['theme', 'language', 'performance'] as const,
    preset_value: [
      'light',
      'dark',
      'auto',
      'zh-CN',
      'en-US',
      'ja-JP',
      'low',
      'normal',
      'custom',
      'unknown',
    ] as const,
  }),
  appearance_package_finished: finished({
    package_kind: ['theme', 'background', 'sound', 'mascot', 'unknown'] as const,
    action: ['import', 'enable', 'delete', 'export'] as const,
  }),
  appearance_store_install_finished: finished({
    category_kind: ['theme', 'background', 'sound', 'mascot', 'unknown'] as const,
  }),
  appearance_share_finished: finished({
    category_kind: ['theme', 'background', 'sound', 'mascot', 'unknown'] as const,
  }),
  mascot_preference_changed: finished({
    action: ['enable', 'disable', 'fps', 'scale', 'behavior', 'configure'] as const,
    fps_preset: ['low', 'normal', 'high', 'custom', 'unknown'] as const,
  }),
  home_activity_load_finished: finished({
    trigger_kind: ['initial', 'manual'] as const,
    source_kind: [
      'arknights',
      'endfield',
      'starrail',
      'bluearchive',
      'reverse1999',
      'stellasora',
      'sra',
      'multi',
      'unknown',
    ] as const,
    cache_kind: ['cache', 'network', 'mixed', 'unknown'] as const,
  }),
  home_layout_changed: finished({
    action: ['preset', 'visibility', 'reorder', 'quick_task', 'reset', 'save'] as const,
    layout_preset: ['default', 'custom', 'unknown'] as const,
  }),
  history_query_finished: finished({
    filter_kind: ['default', 'filtered'] as const,
    count_bucket: count,
  }),
  diagnostic_export_finished: finished({
    bundle_kind: ['issue', 'logs'] as const,
    script_type: script,
    incomplete: ['yes', 'no', 'unknown'] as const,
  }),
  data_backup_export_finished: finished({}),
  replay_tool_finished: finished({
    action: ['connect', 'save', 'play', 'open', 'configure'] as const,
  }),
  help_link_requested: finished({
    link_kind: ['docs', 'support', 'repository', 'community'] as const,
    entry_source: ['initialization', 'settings', 'script', 'home', 'other'] as const,
  }),
  adapter_setup_finished: finished({
    script_type: script,
    operation_kind: [
      'save',
      'import',
      'discover_path',
      'environment',
      'launcher',
      'update',
      'update_check',
      'login',
      'template',
      'debug',
      'instance_add',
      'instance_delete',
      'preview',
    ] as const,
    engine_kind: ['M7A', 'SRA', 'embedded', 'shell', 'hotkey', 'unknown'] as const,
  }),
} as const

export type FeatureAnalyticsEventName = keyof typeof featureAnalyticsSchemas
export type FeatureAnalyticsOutcome = (typeof outcomes)[number]
export type FeatureAnalyticsEventProps = {
  [K in FeatureAnalyticsEventName]: {
    [
      P in keyof (typeof featureAnalyticsSchemas)[K]
    ]: (typeof featureAnalyticsSchemas)[K][P] extends readonly string[]
      ? (typeof featureAnalyticsSchemas)[K][P][number]
      : never
  }
}
export const mainOnlyFeatureEvents = [
  'backend_restart_finished',
  'app_close_finished',
  'runtime_alignment_finished',
  'renderer_recovery_decided',
  'renderer_responsiveness_changed',
  'tray_action_requested',
  'virtual_display_prompt_answered',
  'diagnostic_export_finished',
  'data_backup_export_finished',
] as const
