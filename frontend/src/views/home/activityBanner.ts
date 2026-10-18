import type { SraActivityOverview } from '@/types/home'

/** 从各游戏数据源里抽出 banner 需要的几项，屏蔽字段命名差异 */
export interface ActivityBannerSource {
  cover: string
  /** 版本号，徽章用；取不到时轮播退回游戏名 */
  version?: string
  subtitle: string
  /** 开始时间：轮播据此区分「还没开始」与「进行中」，取不到时为空串 */
  startTime: string
  endTime: string
  available: boolean
  stale: boolean
}

const toTimestamp = (value: string) => {
  const timestamp = new Date(value).getTime()
  return Number.isNaN(timestamp) ? 0 : timestamp
}

/** 与卡片里的 activeActivities 同口径：只认进行中的，最早结束的排前面 */
const pickFallbackActivity = (overview: SraActivityOverview) => {
  const now = Date.now()
  const ongoing = overview.activities
    .filter(item => toTimestamp(item.startTime) <= now && toTimestamp(item.endTime) > now)
    .sort((left, right) => toTimestamp(left.endTime) - toTimestamp(right.endTime))
  return ongoing[0] ?? overview.activities[0]
}

export const sraActivityBanner = (overview: SraActivityOverview): ActivityBannerSource => {
  // 名字与倒计时必须出自同一条记录，否则缺版本名时会拼出「A 活动 + B 的倒计时」
  const activity = pickFallbackActivity(overview)
  const useVersion = Boolean(overview.versionName && overview.endTime)
  return {
    // 版本封面优先；部分游戏没有版本封面，退回第一张有图的活动
    cover: overview.cover || overview.activities.find(item => item.cover)?.cover || '',
    subtitle: useVersion ? overview.versionName : (activity?.name ?? ''),
    version: overview.version,
    startTime: useVersion ? overview.startTime : (activity?.startTime ?? ''),
    endTime: useVersion ? overview.endTime : (activity?.endTime ?? ''),
    available: overview.Available,
    stale: overview.Stale,
  }
}
