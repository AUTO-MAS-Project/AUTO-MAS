import { OpenAPI } from '@/api'
import type { EndfieldActivityOverview, HomeModuleKey, SraActivityOverview } from '@/types/home'

/** 各游戏 banner 的主题色，无封面时用来生成底纹；与原卡片上的 accent 保持一致 */
export const HOME_ACTIVITY_ACCENTS: Record<string, string> = {
  endfield: '#ffb45a',
  starrail: '#62c4e7',
  genshin: '#8fe3b0',
  zenless: '#ffd24a',
  wutheringwaves: '#7aa2ff',
  nte: '#c9a7ff',
  reverse1999: '#f2a0c0',
  bluearchive: '#3ba9ee',
  stellasora: '#2b9fff',
  arknights: '#9fb4cc',
}

export const getActivityAccent = (key: HomeModuleKey): string => {
  return HOME_ACTIVITY_ACCENTS[key] ?? '#7aa2ff'
}

/** 从各游戏数据源里抽出 banner 需要的几项，屏蔽字段命名差异 */
export interface ActivityBannerSource {
  cover: string
  /** 主封面 404 时依次尝试的备用图（见 ActivityBannerItem.coverCandidates） */
  coverCandidates?: string[]
  /** 版本号，徽章用；取不到时轮播退回游戏名 */
  version?: string
  subtitle: string
  /** 开始时间：轮播据此区分「还没开始」与「进行中」，取不到时为空串 */
  startTime: string
  endTime: string
  available: boolean
  stale: boolean
  /** 展示的是刚结束的那场活动；轮播据此补一句「后续活动即将开始」 */
  ended?: boolean
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

export const endfieldActivityBanner = (
  overview: EndfieldActivityOverview,
  /** 官网当期宣传图（已由数据源换成后端缩放地址），有就用它当封面 */
  versionArt = '',
  /** 版本名（如「雪凇幽梦」），有就用它当标题 */
  versionName = ''
): ActivityBannerSource => {
  // 标题、时间与背景图都跟着「当前那场活动」走；卡池只是附带的，取不到活动时才用它兜底
  const now = Date.now()
  const activities = [...overview.Activities].sort(
    (left, right) => toTimestamp(left.StartTime) - toTimestamp(right.StartTime)
  )
  const activity =
    activities.find(
      item => toTimestamp(item.StartTime) <= now && toTimestamp(item.EndTime) > now
    ) ??
    activities.find(item => toTimestamp(item.StartTime) > now) ??
    activities[0]

  // 封面优先用版本图（官网当期宣传图）；没有才退回当前活动的背景大图，
  // 两者都取不到就留空，由轮播用主题色底纹——不拿卡池头像那种小图去凑
  const cover =
    versionArt ||
    (activity?.CoverUrl
      ? `${OpenAPI.BASE}/api/info/endfield/image?url=${encodeURIComponent(activity.CoverUrl)}`
      : '')

  // 横幅报的是「这个版本」：标题是版本名，倒计时也应当数到本期内容整体结束，
  // 而不是随便挑一场活动。所以取当前活动与卡池里最晚的结束时间当终点。
  // 起点同理只算还在进行或将要开始的：已结束条目的开始时间会把时间条拉到几周前
  const pending = [...overview.Activities, ...overview.Pools].filter(
    item => toTimestamp(item.EndTime) > now
  )
  const ends = pending.map(item => toTimestamp(item.EndTime)).filter(value => value > 0)
  const starts = pending.map(item => toTimestamp(item.StartTime)).filter(value => value > 0)

  return {
    cover,
    // 徽章里只要版本号本身，「1.5.3@10506507-7」这种热更后缀太长
    version: (overview.Version || '').split('@')[0],
    subtitle: versionName || activity?.Name || overview.Version || '',
    startTime: starts.length ? new Date(Math.min(...starts)).toISOString() : '',
    endTime: ends.length ? new Date(Math.max(...ends)).toISOString() : (activity?.EndTime ?? ''),
    available: overview.Available,
    stale: overview.Stale,
  }
}

/**
 * 星塔旅人的横幅只报「版本活动」。
 *
 * 那是会开限时活动关的版本大活动（「遥远的塔」这种），招募与拼图、经营之类的小玩法
 * 只留在下面的活动卡里；一期版本活动都没有时横幅空着，由轮播显示「暂无进行中的活动」。
 */
const STELLA_BANNER_KIND = '版本活动'

export const stellaActivityBanner = (overview: SraActivityOverview): ActivityBannerSource => {
  const now = Date.now()
  const versions = overview.activities.filter(item =>
    (item.kind ?? '').includes(STELLA_BANNER_KIND)
  )
  const activity =
    versions.find(item => toTimestamp(item.startTime) <= now && toTimestamp(item.endTime) > now) ??
    versions.find(item => toTimestamp(item.startTime) > now)

  return {
    cover: activity?.cover ?? '',
    subtitle: activity?.name ?? '',
    startTime: activity?.startTime ?? '',
    endTime: activity?.endTime ?? '',
    available: overview.Available,
    stale: overview.Stale,
  }
}
