import type { AnalyticsEvent, AnalyticsEventName } from '../../src/types/analytics'
import { featureAnalyticsSchemas, mainOnlyFeatureEvents } from './analyticsFeaturePolicy'

const duration = ['<1s', '1-5s', '5-30s', '30-120s', '>120s']
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
]
const runtime = ['off', 'managed', 'development', 'unknown']
const updateSource = ['cnb', 'github', 'mirrorchyan', 'autosite', 'unknown']
const mode = ['AutoProxy', 'ScriptConfig', 'Update', 'CycleRun', 'unknown']
const screens = [
  'initialization',
  'home',
  'scripts',
  'script_edit',
  'script_setup',
  'user_add',
  'user_edit',
  'plans',
  'emulators',
  'queue',
  'scheduler',
  'history',
  'gamesign',
  'community_sign',
  'community_activity',
  'theme_store',
  'settings',
  'taskboard',
]
const schemas: Record<AnalyticsEventName, Record<string, readonly string[]>> = {
  ...featureAnalyticsSchemas,
  app_started: {
    launch_kind: ['manual', 'auto_start', 'unknown'],
    runtime_mode: runtime,
    release_channel: ['stable', 'beta', 'unknown'],
  },
  renderer_ready: { duration_bucket: duration, visibility: ['visible', 'hidden'] },
  initialization_decided: {
    decision: ['skip-home', 'full-init', 'force-backend-update'],
    runtime_mode: runtime,
    duration_bucket: duration,
  },
  initialization_stage_finished_v2: {
    stage: [
      'runtime_binary',
      'bootstrap',
      'python',
      'pip',
      'git',
      'repository',
      'dependency',
      'unknown',
    ],
    runtime_mode: runtime,
    outcome: ['success', 'failure', 'cancelled'],
    known_code: [
      'none',
      'unknown',
      'RUNTIME_NOT_FOUND',
      'RUNTIME_BINARY_ALIGN_ERROR',
      'OPERATION_CANCELLED',
      'NETWORK_UNAVAILABLE',
      'DEPENDENCY_SYNC_FAILED',
      'ENVIRONMENT_BROKEN',
      'PYTHON_VERSION_MISMATCH',
      'LOCKFILE_MISSING',
      'LOCKFILE_OUTDATED',
      'WORKSPACE_RESTORE_FAILED',
      'INTERNAL_ERROR',
    ],
    failed_stage: [
      'none',
      'runtime_binary',
      'bootstrap',
      'python',
      'pip',
      'git',
      'repository',
      'dependency',
      'unknown',
    ],
    duration_bucket: duration,
  },
  initialization_recovery_selected: {
    action: [
      'restore-workspace',
      'retry',
      'retry-other-mirror',
      'rebuild-environment',
      'open-log',
      'run-doctor',
      'skip',
      'select-mirror',
    ],
    stage: ['python', 'pip', 'git', 'repository', 'dependency', 'backend'],
    mirror_kind: ['default', 'official', 'mirror', 'unknown'],
    duration_bucket: duration,
  },
  notification_channel_changed: {
    channel_kind: ['system', 'mail', 'serverchan', 'cmcc', 'koishi', 'openclaw_qq'],
    action: ['enable', 'disable'],
    outcome: ['success', 'failure'],
    duration_bucket: duration,
  },
  notification_binding_finished: {
    channel_kind: ['openclaw_qq'],
    action: ['bind', 'rebind', 'unbind', 'manual_bind'],
    outcome: [
      'connected',
      'saved',
      'unbound',
      'failure',
      'expired',
      'cancelled',
      'replaced',
      'unmounted',
    ],
    duration_bucket: duration,
  },
  webhook_test_finished: {
    scope_kind: ['global', 'script'],
    outcome: ['success', 'failure', 'unknown'],
    duration_bucket: duration,
  },
  backend_start_finished: {
    outcome: ['success', 'failure'],
    runtime_mode: runtime,
    duration_bucket: duration,
  },
  initialization_finished_v2: {
    outcome: ['success', 'failure', 'cancelled', 'skipped', 'unconfirmed'],
    flow_kind: ['first-run', 'update', 'startup', 'skip'],
    runtime_mode: runtime,
    failed_stage: [
      'none',
      'runtime_binary',
      'python',
      'pip',
      'git',
      'repository',
      'dependency',
      'backend',
      'unknown',
    ],
    duration_bucket: duration,
  },
  screen_view: {
    screen: screens,
    script_type: script,
    entry_source: [...screens, 'initial', 'other'],
  },
  script_create_finished: {
    create_kind: ['new', 'template', 'reuse', 'copy'],
    script_type: script,
    outcome: ['success', 'failure', 'partial'],
    duration_bucket: duration,
  },
  user_create_finished: {
    script_type: script,
    outcome: ['success', 'failure', 'blocked'],
    duration_bucket: duration,
  },
  config_write_finished: {
    owner_kind: ['script', 'user', 'settings'],
    section_kind: ['info', 'function', 'notify', 'script', 'user', 'ui', 'multiple', 'other'],
    script_type: script,
    outcome: ['success', 'failure', 'blocked'],
    duration_bucket: duration,
  },
  task_start_result: {
    source: ['home', 'scheduler', 'tray', 'mascot', 'script_config', 'script_update', 'unknown'],
    mode,
    target_kind: ['script', 'queue', 'user', 'unknown'],
    outcome: ['accepted', 'failure'],
    duration_bucket: duration,
  },
  task_observed_finished: {
    mode,
    script_type: script,
    outcome: ['success', 'error', 'cancelled'],
    duration_bucket: duration,
  },
  task_stop_result: {
    source: ['home', 'scheduler', 'tray', 'mascot', 'script_config', 'script_update', 'unknown'],
    mode,
    request_outcome: ['accepted', 'failure'],
    duration_bucket: duration,
  },
  task_resume_requested: {
    source: ['home', 'scheduler', 'tray', 'mascot', 'script_config', 'script_update', 'unknown'],
    resume_kind: ['from_script', 'scoped_users', 'from_script_scoped_users'],
    scope_kind: ['all', 'script_users', 'queue_users'],
    request_outcome: ['accepted', 'failure'],
    duration_bucket: duration,
  },
  queue_manage_finished: {
    action: [
      'create',
      'delete',
      'update',
      'item_add',
      'item_remove',
      'item_update',
      'item_reorder',
    ],
    queue_kind: ['normal', 'cycle', 'unknown'],
    count_bucket: ['0', '1', '2-5', '6-20', '20+'],
    outcome: ['success', 'failure'],
    duration_bucket: duration,
  },
  queue_schedule_changed: {
    schedule_kind: ['fixed_time', 'interval', 'queue_time', 'cycle', 'startup', 'unknown'],
    action: ['enable', 'disable', 'mode', 'interval', 'time', 'days', 'run_once', 'configure'],
    outcome: ['success', 'failure'],
    duration_bucket: duration,
  },
  plan_manage_finished: {
    action: ['create', 'delete', 'rename', 'reorder'],
    plan_type: [
      'MaaPlanConfig',
      'MaaEndPlanConfig',
      'BAAHPlanConfig',
      'MSSPlanConfig',
      'multi',
      'unknown',
    ],
    count_bucket: ['0', '1', '2-5', '6-20', '20+'],
    outcome: ['success', 'failure'],
    duration_bucket: duration,
  },
  script_run_started: {
    mode: ['AutoProxy', 'CycleRun'],
    script_type: script,
  },
  script_run_finished: {
    mode: ['AutoProxy', 'CycleRun'],
    script_type: script,
    outcome: ['success', 'failed', 'skipped', 'no_user', 'incomplete', 'error', 'cancelled'],
    partial_failure: ['yes', 'no', 'unknown'],
    duration_bucket: duration,
  },
  native_config_action_finished: {
    script_type: script,
    operation: ['open', 'view', 'save', 'close', 'timeout', 'discard'],
    outcome: ['accepted', 'failure', 'discarded'],
    duration_bucket: duration,
  },
  config_restore_finished: {
    script_type: script,
    target_kind: ['mas', 'native', 'unknown'],
    forced: ['yes', 'no'],
    outcome: ['success', 'failure', 'confirmation_required'],
    duration_bucket: duration,
  },
  community_login_finished: {
    provider: ['miyoushe', 'skland'],
    stage: ['create', 'scan', 'save'],
    outcome: [
      'saved',
      'confirmed_unsaved',
      'failure',
      'expired',
      'cancelled',
      'replaced',
      'unmounted',
    ],
    duration_bucket: duration,
  },
  notification_test_finished: {
    test_kind: ['configured'],
    request_outcome: ['accepted', 'rejected', 'unknown'],
    duration_bucket: duration,
  },
  update_download_finished: {
    source: updateSource,
    outcome: ['completed', 'failed', 'cancelled', 'observation_unknown'],
    duration_bucket: duration,
  },
  update_check_finished: {
    trigger_kind: ['manual', 'automatic'],
    outcome: ['success', 'failure'],
    update_available: ['yes', 'no', 'unknown'],
    duration_bucket: duration,
  },
  update_download_started: {
    source_kind: updateSource,
    release_channel: ['stable', 'beta', 'unknown'],
    duration_bucket: duration,
  },
  update_source_changed: {
    from_kind: updateSource,
    to_kind: ['cnb'],
    trigger_kind: ['manual', 'low_speed'],
    outcome: ['success', 'failure', 'unknown'],
    duration_bucket: duration,
  },
  update_install_requested: {
    choice: ['install_now', 'later'],
    request_outcome: ['accepted', 'rejected', 'unknown', 'not_requested'],
    duration_bucket: duration,
  },
  connection_incident_finished: {
    reason_kind: ['normal', 'abnormal', 'policy', 'server', 'other'],
    outcome: ['recovered', 'recovery_stopped'],
    recovery_kind: ['reconnect', 'manual', 'backend_restart'],
    duration_bucket: duration,
  },
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/** 运行时再校验一次；不允许把类型断言、额外字段或原始文本带过 IPC 边界。 */
export function validateAnalyticsEvent(value: unknown, renderer: boolean): AnalyticsEvent | null {
  if (!isRecord(value) || Object.keys(value).length !== 2 || typeof value.name !== 'string')
    return null
  if (!Object.prototype.hasOwnProperty.call(schemas, value.name) || !isRecord(value.props))
    return null
  if (
    renderer &&
    [
      'app_started',
      'backend_start_finished',
      'initialization_stage_finished_v2',
      ...mainOnlyFeatureEvents,
    ].includes(value.name)
  )
    return null
  const schema = schemas[value.name as AnalyticsEventName]
  if (Object.keys(value.props).length !== Object.keys(schema).length) return null
  const props: Record<string, string> = {}
  for (const [key, allowed] of Object.entries(schema)) {
    const field = value.props[key]
    if (typeof field !== 'string' || !allowed.includes(field)) return null
    props[key] = field
  }
  return { name: value.name, props } as AnalyticsEvent
}

export function analyticsDuration(
  durationMs: number
): '<1s' | '1-5s' | '5-30s' | '30-120s' | '>120s' {
  return durationMs < 1_000
    ? '<1s'
    : durationMs < 5_000
      ? '1-5s'
      : durationMs < 30_000
        ? '5-30s'
        : durationMs < 120_000
          ? '30-120s'
          : '>120s'
}
