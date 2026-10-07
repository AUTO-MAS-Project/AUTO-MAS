/** 编辑页字段保存的统一状态机结果。 */
export type SaveState =
  | 'idle'
  | 'dirty'
  | 'saving'
  | 'saved'
  | 'failed_draft_kept'
  | 'failed_reverted'
  | 'rejected'
  | 'discarded'
  | 'unknown'

const LABEL_KEYS: Record<SaveState, string> = {
  idle: 'saveState.idle',
  dirty: 'saveState.dirty',
  saving: 'saveState.saving',
  saved: 'saveState.saved',
  failed_draft_kept: 'saveState.failedDraftKept',
  failed_reverted: 'saveState.failedReverted',
  rejected: 'saveState.rejected',
  discarded: 'saveState.discarded',
  unknown: 'saveState.unknown',
}

/** 状态 → i18n key；未知取值回落到 saveState.unknown，避免页面渲染出 key 或空白。 */
export function saveStateLabelKey(state: SaveState): string {
  return LABEL_KEYS[state] ?? LABEL_KEYS.unknown
}
