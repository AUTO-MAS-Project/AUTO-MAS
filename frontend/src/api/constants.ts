import type {
  GetStageIn,
  HistorySearchIn,
  PowerIn,
  ScriptCreateIn,
  TaskCreateIn,
} from './generated/types.gen'

export type StageQueryType = GetStageIn['type']
export type HistorySearchMode = HistorySearchIn['mode']
export type ScriptCreateType = ScriptCreateIn['type']
export type TaskCreateMode = TaskCreateIn['mode']
export type PowerSignal = PowerIn['signal']

export const STAGE_QUERY_TYPE = {
  USER: 'User',
  TODAY: 'Today',
  ALL: 'ALL',
  MONDAY: 'Monday',
  TUESDAY: 'Tuesday',
  WEDNESDAY: 'Wednesday',
  THURSDAY: 'Thursday',
  FRIDAY: 'Friday',
  SATURDAY: 'Saturday',
  SUNDAY: 'Sunday',
} as const satisfies Record<string, StageQueryType>

export const HISTORY_SEARCH_MODE = {
  DAILY: 'DAILY',
  WEEKLY: 'WEEKLY',
  MONTHLY: 'MONTHLY',
} as const satisfies Record<string, HistorySearchMode>

export const SCRIPT_CREATE_TYPE = {
  MAA: 'MAA',
  SRC: 'SRC',
  GENERAL: 'General',
  MAA_END: 'MaaEnd',
} as const satisfies Record<string, ScriptCreateType>

export const TASK_CREATE_MODE = {
  AUTO_PROXY: 'AutoProxy',
  MANUAL_REVIEW: 'ManualReview',
  SCRIPT_CONFIG: 'ScriptConfig',
} as const satisfies Record<string, TaskCreateMode>

export const POWER_SIGNAL = {
  NO_ACTION: 'NoAction',
  SHUTDOWN: 'Shutdown',
  SHUTDOWN_FORCE: 'ShutdownForce',
  REBOOT: 'Reboot',
  HIBERNATE: 'Hibernate',
  SLEEP: 'Sleep',
  KILL_SELF: 'KillSelf',
} as const satisfies Record<string, PowerSignal>
