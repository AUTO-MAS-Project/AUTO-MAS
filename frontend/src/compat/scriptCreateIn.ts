/* oxlint-disable no-redeclare */
/** Legacy script type constants used by the not-yet-migrated script editor. */
export enum LegacyScriptType {
  MAA = 'MaaScript',
  SRC = 'SrcScript',
  MAA_END = 'MaaEndScript',
  M9A = 'M9AScript',
  MAA_FW = 'MaaFWScript',
  OKWW = 'OkwwScript',
  OK_NTE = 'OkNteScript',
  HSR = 'HSRScript',
  BETTER_GI = 'BetterGIScript',
  ZZZ_OD = 'ZzzOdScript',
  BAAH = 'BAAHScript',
  WHIMBOX = 'WhimboxScript',
  MSS = 'MSSScript',
  GENERAL = 'GeneralScript',
}

export const ScriptCreateIn = { type: LegacyScriptType } as const
export namespace ScriptCreateIn {
  export type type = LegacyScriptType
}
/* oxlint-disable no-redeclare */
