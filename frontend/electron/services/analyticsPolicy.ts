import type { AnalyticsEvent, AnalyticsEventName } from '../../src/types/analytics'

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
const mode = ['AutoProxy', 'ScriptConfig', 'Update', 'CycleRun', 'unknown']
const schemas: Record<AnalyticsEventName, Record<string, readonly string[]>> = {
  app_started: {},
  renderer_ready: { duration_bucket: duration },
  backend_start_finished: {
    outcome: ['success', 'failure'],
    runtime_mode: runtime,
    duration_bucket: duration,
  },
  initialization_finished: {
    outcome: ['success', 'failure', 'skipped', 'unconfirmed'],
    flow_kind: ['first-run', 'update', 'startup', 'skip'],
    runtime_mode: runtime,
    failed_stage: [
      'none',
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
    screen: [
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
    ],
    script_type: script,
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
  script_run_started: {
    mode: ['AutoProxy', 'CycleRun'],
    script_type: script,
  },
  script_run_finished: {
    mode: ['AutoProxy', 'CycleRun'],
    script_type: script,
    outcome: ['success', 'failed', 'skipped', 'no_user', 'incomplete', 'error', 'cancelled'],
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
    source: ['cnb', 'github', 'mirrorchyan', 'autosite', 'unknown'],
    outcome: ['completed', 'failed', 'cancelled', 'observation_unknown'],
    duration_bucket: duration,
  },
  connection_incident_finished: {
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
  if (renderer && (value.name === 'app_started' || value.name === 'backend_start_finished'))
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
