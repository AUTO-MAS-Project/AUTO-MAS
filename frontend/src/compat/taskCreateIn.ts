/* oxlint-disable no-redeclare */
/**
 * Legacy UI mode constants kept while the scheduler page is being migrated.
 * New API calls use the generated TaskMode enum directly.
 */
export enum LegacyTaskMode {
  AUTO_PROXY = 'AutoProxy',
  CYCLE_RUN = 'CycleRun',
  SCRIPT_CONFIG = 'ScriptConfig',
  UPDATE = 'Update',
}

export const TaskCreateIn = { mode: LegacyTaskMode } as const
export namespace TaskCreateIn {
  export type mode = LegacyTaskMode
}
/* eslint-disable no-redeclare */
