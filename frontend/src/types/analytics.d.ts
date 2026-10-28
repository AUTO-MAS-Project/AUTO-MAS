import type {
  FeatureAnalyticsEventProps,
  mainOnlyFeatureEvents,
} from '../../electron/services/analyticsFeaturePolicy'

export type AnalyticsDurationBucket = '<1s' | '1-5s' | '5-30s' | '30-120s' | '>120s'
export type AnalyticsCountBucket = '0' | '1' | '2-5' | '6-20' | '20+'
export type AnalyticsQueueKind = 'normal' | 'cycle' | 'unknown'
export type AnalyticsPlanType =
  | 'MaaPlanConfig'
  | 'MaaEndPlanConfig'
  | 'BAAHPlanConfig'
  | 'MSSPlanConfig'
  | 'multi'
  | 'unknown'

/** 只开放已声明的事件；对象标识和自由文本不进入采集入口。 */
export type AnalyticsScriptType =
  | 'MAA'
  | 'SRC'
  | 'MaaEnd'
  | 'HSR'
  | 'General'
  | 'BAAH'
  | 'MaaFW'
  | 'M9A'
  | 'MSS'
  | 'BetterGI'
  | 'Okww'
  | 'OkNte'
  | 'ZzzOd'
  | 'Whimbox'
  | 'unknown'
  | 'multi'
  | 'none'
export type AnalyticsRuntimeMode = 'off' | 'managed' | 'development' | 'unknown'
export type AnalyticsUpdateSource = 'cnb' | 'github' | 'mirrorchyan' | 'autosite' | 'unknown'
export type AnalyticsInitializationStage =
  | 'runtime_binary'
  | 'bootstrap'
  | 'python'
  | 'pip'
  | 'git'
  | 'repository'
  | 'dependency'
  | 'unknown'
export type AnalyticsInitializationCode =
  | 'none'
  | 'unknown'
  | 'RUNTIME_NOT_FOUND'
  | 'RUNTIME_BINARY_ALIGN_ERROR'
  | 'OPERATION_CANCELLED'
  | 'NETWORK_UNAVAILABLE'
  | 'DEPENDENCY_SYNC_FAILED'
  | 'ENVIRONMENT_BROKEN'
  | 'PYTHON_VERSION_MISMATCH'
  | 'LOCKFILE_MISSING'
  | 'LOCKFILE_OUTDATED'
  | 'WORKSPACE_RESTORE_FAILED'
  | 'INTERNAL_ERROR'
export type AnalyticsNotificationChannel =
  | 'system'
  | 'mail'
  | 'serverchan'
  | 'cmcc'
  | 'koishi'
  | 'openclaw_qq'
export type AnalyticsTaskMode = 'AutoProxy' | 'ScriptConfig' | 'Update' | 'CycleRun' | 'unknown'
export type AnalyticsTaskSource =
  | 'home'
  | 'scheduler'
  | 'tray'
  | 'mascot'
  | 'script_config'
  | 'script_update'
  | 'unknown'
export type AnalyticsScreen =
  | 'initialization'
  | 'home'
  | 'scripts'
  | 'script_edit'
  | 'script_setup'
  | 'user_add'
  | 'user_edit'
  | 'plans'
  | 'emulators'
  | 'queue'
  | 'scheduler'
  | 'history'
  | 'gamesign'
  | 'community_sign'
  | 'community_activity'
  | 'theme_store'
  | 'settings'
  | 'taskboard'
export interface AnalyticsEventProps extends FeatureAnalyticsEventProps {
  app_started: {
    launch_kind: 'manual' | 'auto_start' | 'unknown'
    runtime_mode: AnalyticsRuntimeMode
    release_channel: 'stable' | 'beta' | 'unknown'
  }
  renderer_ready: { duration_bucket: AnalyticsDurationBucket; visibility: 'visible' | 'hidden' }
  backend_start_finished: {
    outcome: 'success' | 'failure'
    runtime_mode: AnalyticsRuntimeMode
    duration_bucket: AnalyticsDurationBucket
  }
  initialization_decided: {
    decision: 'skip-home' | 'full-init' | 'force-backend-update'
    runtime_mode: AnalyticsRuntimeMode
    duration_bucket: AnalyticsDurationBucket
  }
  initialization_stage_finished_v2: {
    stage: AnalyticsInitializationStage
    runtime_mode: AnalyticsRuntimeMode
    outcome: 'success' | 'failure' | 'cancelled'
    known_code: AnalyticsInitializationCode
    failed_stage: AnalyticsInitializationStage | 'none'
    duration_bucket: AnalyticsDurationBucket
  }
  initialization_recovery_selected: {
    action:
      | 'restore-workspace'
      | 'retry'
      | 'retry-other-mirror'
      | 'rebuild-environment'
      | 'open-log'
      | 'run-doctor'
      | 'skip'
      | 'select-mirror'
    stage: 'python' | 'pip' | 'git' | 'repository' | 'dependency' | 'backend'
    mirror_kind: 'default' | 'official' | 'mirror' | 'unknown'
    duration_bucket: AnalyticsDurationBucket
  }
  notification_channel_changed: {
    channel_kind: AnalyticsNotificationChannel
    action: 'enable' | 'disable'
    outcome: 'success' | 'failure'
    duration_bucket: AnalyticsDurationBucket
  }
  notification_binding_finished: {
    channel_kind: 'openclaw_qq'
    action: 'bind' | 'rebind' | 'unbind'
    outcome:
      | 'connected'
      | 'unbound'
      | 'failure'
      | 'expired'
      | 'cancelled'
      | 'replaced'
      | 'unmounted'
    duration_bucket: AnalyticsDurationBucket
  }
  webhook_test_finished: {
    scope_kind: 'global' | 'script'
    outcome: 'success' | 'failure' | 'unknown'
    duration_bucket: AnalyticsDurationBucket
  }
  initialization_finished_v2: {
    outcome: 'success' | 'failure' | 'cancelled' | 'skipped' | 'unconfirmed'
    flow_kind: 'first-run' | 'update' | 'startup' | 'skip'
    runtime_mode: AnalyticsRuntimeMode
    failed_stage:
      | 'none'
      | 'runtime_binary'
      | 'python'
      | 'pip'
      | 'git'
      | 'repository'
      | 'dependency'
      | 'backend'
      | 'unknown'
    duration_bucket: AnalyticsDurationBucket
  }
  screen_view: {
    screen: AnalyticsScreen
    script_type: AnalyticsScriptType
    entry_source: AnalyticsScreen | 'initial' | 'other'
  }
  script_create_finished: {
    create_kind: 'new' | 'template' | 'reuse' | 'copy'
    script_type: AnalyticsScriptType
    outcome: 'success' | 'failure' | 'partial'
    duration_bucket: AnalyticsDurationBucket
  }
  user_create_finished: {
    script_type: AnalyticsScriptType
    outcome: 'success' | 'failure' | 'blocked'
    duration_bucket: AnalyticsDurationBucket
  }
  config_write_finished: {
    owner_kind: 'script' | 'user' | 'settings'
    section_kind: 'info' | 'function' | 'notify' | 'script' | 'user' | 'ui' | 'multiple' | 'other'
    script_type: AnalyticsScriptType
    outcome: 'success' | 'failure' | 'blocked'
    duration_bucket: AnalyticsDurationBucket
  }
  task_start_result: {
    source: AnalyticsTaskSource
    mode: AnalyticsTaskMode
    target_kind: 'script' | 'queue' | 'user' | 'unknown'
    outcome: 'accepted' | 'failure'
    duration_bucket: AnalyticsDurationBucket
  }
  task_observed_finished: {
    mode: AnalyticsTaskMode
    script_type: AnalyticsScriptType
    outcome: 'success' | 'error' | 'cancelled'
    duration_bucket: AnalyticsDurationBucket
  }
  task_stop_result: {
    source: AnalyticsTaskSource
    mode: AnalyticsTaskMode
    request_outcome: 'accepted' | 'failure'
    duration_bucket: AnalyticsDurationBucket
  }
  task_resume_requested: {
    source: AnalyticsTaskSource
    resume_kind: 'from_script' | 'scoped_users' | 'from_script_scoped_users'
    scope_kind: 'all' | 'script_users' | 'queue_users'
    request_outcome: 'accepted' | 'failure'
    duration_bucket: AnalyticsDurationBucket
  }
  queue_manage_finished: {
    action:
      | 'create'
      | 'delete'
      | 'update'
      | 'item_add'
      | 'item_remove'
      | 'item_update'
      | 'item_reorder'
    queue_kind: AnalyticsQueueKind
    count_bucket: AnalyticsCountBucket
    outcome: 'success' | 'failure'
    duration_bucket: AnalyticsDurationBucket
  }
  queue_schedule_changed: {
    schedule_kind: 'fixed_time' | 'interval' | 'queue_time' | 'cycle' | 'startup' | 'unknown'
    action: 'enable' | 'disable' | 'mode' | 'interval' | 'time' | 'days' | 'run_once' | 'configure'
    outcome: 'success' | 'failure'
    duration_bucket: AnalyticsDurationBucket
  }
  plan_manage_finished: {
    action: 'create' | 'delete' | 'rename' | 'reorder'
    plan_type: AnalyticsPlanType
    count_bucket: AnalyticsCountBucket
    outcome: 'success' | 'failure'
    duration_bucket: AnalyticsDurationBucket
  }
  script_run_started: {
    mode: 'AutoProxy' | 'CycleRun'
    script_type: AnalyticsScriptType
  }
  script_run_finished: {
    mode: 'AutoProxy' | 'CycleRun'
    script_type: AnalyticsScriptType
    outcome: 'success' | 'failed' | 'skipped' | 'no_user' | 'incomplete' | 'error' | 'cancelled'
    duration_bucket: AnalyticsDurationBucket
  }
  native_config_action_finished: {
    script_type: AnalyticsScriptType
    operation: 'open' | 'view' | 'save' | 'close' | 'timeout' | 'discard'
    outcome: 'accepted' | 'failure' | 'discarded'
    duration_bucket: AnalyticsDurationBucket
  }
  config_restore_finished: {
    script_type: AnalyticsScriptType
    target_kind: 'mas' | 'native' | 'unknown'
    forced: 'yes' | 'no'
    outcome: 'success' | 'failure' | 'confirmation_required'
    duration_bucket: AnalyticsDurationBucket
  }
  community_login_finished: {
    provider: 'miyoushe' | 'skland'
    stage: 'create' | 'scan' | 'save'
    outcome:
      | 'saved'
      | 'confirmed_unsaved'
      | 'failure'
      | 'expired'
      | 'cancelled'
      | 'replaced'
      | 'unmounted'
    duration_bucket: AnalyticsDurationBucket
  }
  notification_test_finished: {
    test_kind: 'configured'
    request_outcome: 'accepted' | 'rejected' | 'unknown'
    duration_bucket: AnalyticsDurationBucket
  }
  update_download_finished: {
    source: AnalyticsUpdateSource
    outcome: 'completed' | 'failed' | 'cancelled' | 'observation_unknown'
    duration_bucket: AnalyticsDurationBucket
  }
  update_check_finished: {
    trigger_kind: 'manual' | 'automatic'
    outcome: 'success' | 'failure'
    update_available: 'yes' | 'no' | 'unknown'
    duration_bucket: AnalyticsDurationBucket
  }
  update_download_started: {
    source_kind: AnalyticsUpdateSource
    release_channel: 'stable' | 'beta' | 'unknown'
    duration_bucket: AnalyticsDurationBucket
  }
  update_source_changed: {
    from_kind: AnalyticsUpdateSource
    to_kind: 'cnb'
    trigger_kind: 'manual' | 'low_speed'
    outcome: 'success' | 'failure' | 'unknown'
    duration_bucket: AnalyticsDurationBucket
  }
  update_install_requested: {
    choice: 'install_now' | 'later'
    request_outcome: 'accepted' | 'rejected' | 'unknown' | 'not_requested'
    duration_bucket: AnalyticsDurationBucket
  }
  connection_incident_finished: {
    reason_kind: 'normal' | 'abnormal' | 'policy' | 'server' | 'other'
    outcome: 'recovered' | 'recovery_stopped'
    recovery_kind: 'reconnect' | 'manual' | 'backend_restart'
    duration_bucket: AnalyticsDurationBucket
  }
}

export type AnalyticsEventName = keyof AnalyticsEventProps
export type RendererAnalyticsEventName = Exclude<
  AnalyticsEventName,
  | 'app_started'
  | 'backend_start_finished'
  | 'initialization_stage_finished_v2'
  | (typeof mainOnlyFeatureEvents)[number]
>
export type AnalyticsEvent = {
  [K in AnalyticsEventName]: { name: K; props: AnalyticsEventProps[K] }
}[AnalyticsEventName]
export type RendererAnalyticsEvent = Extract<AnalyticsEvent, { name: RendererAnalyticsEventName }>
export type AnalyticsOperationName = Exclude<
  RendererAnalyticsEventName,
  'renderer_ready' | 'screen_view' | 'script_run_started'
>

/** 操作开始前取得代次，关闭再开启后旧操作不能补报。 */
export type AnalyticsContext = number | null
