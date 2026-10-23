export type AnalyticsDurationBucket = '<1s' | '1-5s' | '5-30s' | '30-120s' | '>120s'

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
export interface AnalyticsEventProps {
  app_started: Record<string, never>
  renderer_ready: { duration_bucket: AnalyticsDurationBucket }
  backend_start_finished: {
    outcome: 'success' | 'failure'
    runtime_mode: AnalyticsRuntimeMode
    duration_bucket: AnalyticsDurationBucket
  }
  initialization_finished: {
    outcome: 'success' | 'failure' | 'skipped' | 'unconfirmed'
    flow_kind: 'first-run' | 'update' | 'startup' | 'skip'
    runtime_mode: AnalyticsRuntimeMode
    failed_stage:
      | 'none'
      | 'python'
      | 'pip'
      | 'git'
      | 'repository'
      | 'dependency'
      | 'backend'
      | 'unknown'
    duration_bucket: AnalyticsDurationBucket
  }
  screen_view: { screen: AnalyticsScreen; script_type: AnalyticsScriptType }
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
  update_download_finished: {
    source: 'cnb' | 'github' | 'mirrorchyan' | 'autosite' | 'unknown'
    outcome: 'completed' | 'failed' | 'cancelled' | 'observation_unknown'
    duration_bucket: AnalyticsDurationBucket
  }
  connection_incident_finished: {
    outcome: 'recovered' | 'recovery_stopped'
    recovery_kind: 'reconnect' | 'manual' | 'backend_restart'
    duration_bucket: AnalyticsDurationBucket
  }
}

export type AnalyticsEventName = keyof AnalyticsEventProps
export type RendererAnalyticsEventName = Exclude<
  AnalyticsEventName,
  'app_started' | 'backend_start_finished'
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
