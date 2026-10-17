import { HistoryIndexItem } from '@/api'

export type HistoryStatusClass = 'success' | 'skip' | 'error'

/** 历史记录状态归类：停服维护这类跳过（SKIP）单独一类，显示灰色、不算失败 */
export const statusClass = (status: string): HistoryStatusClass => {
  if (status === HistoryIndexItem.status.DONE) return 'success'
  if (status === HistoryIndexItem.status.SKIP) return 'skip'
  return 'error'
}

const TAG_COLORS: Record<HistoryStatusClass, string> = {
  success: 'success',
  skip: 'default',
  error: 'error',
}

const LABEL_KEYS: Record<HistoryStatusClass, string> = {
  success: 'history.done',
  skip: 'history.skipped',
  error: 'history.failed',
}

export const statusTagColor = (status: string) => TAG_COLORS[statusClass(status)]

export const statusLabelKey = (status: string) => LABEL_KEYS[statusClass(status)]
