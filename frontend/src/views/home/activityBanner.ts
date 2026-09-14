import type {
  ActivityItem,
  EndfieldActivityOverview,
  HomeModuleKey,
  SraActivityOverview,
} from '@/types/home'

/** 各游戏 banner 的主题色，无封面时用来生成底纹；与原卡片上的 accent 保持一致 */
export const HOME_ACTIVITY_ACCENTS: Record<string, string> = {
  endfield: '#ffb45a',
  starrail: '#62c4e7',
  genshin: '#8fe3b0',
  zenless: '#ffd24a',
  wutheringwaves: '#7aa2ff',
  nte: '#c9a7ff',
  reverse1999: '#f2a0c0',
  arknights: '#9fb4cc',
}

export const getActivityAccent = (key: HomeModuleKey): string => {
  return HOME_ACTIVITY_ACCENTS[key] ?? '#7aa2ff'
}

/** 从各游戏数据源里抽出 banner 需要的四项，屏蔽字段命名差异 */
export interface ActivityBannerSource {
  cover: string
  subtitle: string
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
    endTime: useVersion ? overview.endTime : (activity?.endTime ?? ''),
    available: overview.Available,
    stale: overview.Stale,
  }
}

export const endfieldActivityBanner = (
  overview: EndfieldActivityOverview
): ActivityBannerSource => {
  // 标题与倒计时取自同一条记录，避免拼出一条对不上的信息
  const record =
    overview.Pools.find(item => item.ImageUrl) ?? overview.Pools[0] ?? overview.Activities[0]
  return {
    cover: record?.ImageUrl || '',
    subtitle: record?.Name || overview.Version || '',
    endTime: record?.EndTime || '',
    available: overview.Available,
    stale: overview.Stale,
  }
}

export const arknightsActivityBanner = (activityData: ActivityItem[]): ActivityBannerSource => {
  const activity = activityData[0]?.Activity
  return {
    // 明日方舟的数据源里没有活动图，靠主题色底纹兜底
    cover: '',
    subtitle: activity?.Tip ?? '',
    endTime: activity?.UtcExpireTime ?? '',
    available: activityData.length > 0,
    stale: false,
  }
}
