import type {
  GlobalConfig_Replay,
  ObsReplayCheckOut,
  ObsReplaySaveOut,
  ReplayListOut,
  ReplayRecord as ApiReplayRecord,
} from '@/api'

export type ReplayRecord = ApiReplayRecord
export type ReplaySettings = GlobalConfig_Replay
export type ObsReplayCheckResult = ObsReplayCheckOut
export type ObsReplaySaveResult = ObsReplaySaveOut
export type ReplayListResult = ReplayListOut
