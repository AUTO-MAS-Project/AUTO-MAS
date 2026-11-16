import type { HistoryBucket, HistoryDetail } from '@/api'
import type { PullCountStatistics } from '@/types/history'

type Statistics = HistoryBucket['data'] | HistoryDetail['data'] | undefined

const valueOf = <T>(data: Statistics, key: string): T | null =>
  (data?.[key]?.value as T | null | undefined) ?? null

/** 只解包服务端已聚合的值，页面不重新聚合或解析日志。 */
export const historyStatistics = (data: Statistics) => ({
  recruit: valueOf<Record<string, number>>(data, 'recruit_statistics'),
  drops: valueOf<Record<string, Record<string, number>>>(data, 'drop_statistics'),
  matrix: valueOf<Record<string, string>>(data, 'matrix_statistics'),
  pulls: valueOf<PullCountStatistics>(data, 'pull_count_statistics'),
})
