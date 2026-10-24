export type HistoryStatusClass = 'success' | 'skip' | 'cancelled' | 'error'

/** 历史记录状态归类：跳过与取消显示灰色，不算失败 */
export const statusClass = (status: string): HistoryStatusClass => {
  if (status === 'success') return 'success'
  if (status === 'skipped') return 'skip'
  if (status === 'cancelled') return 'cancelled'
  return 'error'
}

const TAG_COLORS: Record<HistoryStatusClass, string> = {
  success: 'success',
  skip: 'default',
  cancelled: 'default',
  error: 'error',
}

const LABEL_KEYS: Record<HistoryStatusClass, string> = {
  success: 'history.done',
  skip: 'history.skipped',
  cancelled: 'history.cancelled',
  error: 'history.failed',
}

export const statusTagColor = (status: string) => TAG_COLORS[statusClass(status)]

export const statusLabelKey = (status: string) => LABEL_KEYS[statusClass(status)]
