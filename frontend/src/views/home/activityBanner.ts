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
  infinitynikki: '#f2a0c0',
  arknights: '#9fb4cc',
}

export const getActivityAccent = (key: HomeModuleKey): string => {
  return HOME_ACTIVITY_ACCENTS[key] ?? '#7aa2ff'
}

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

export const endfieldActivityBanner = (
  overview: EndfieldActivityOverview
): ActivityBannerSource => {
  const now = Date.now()
  const versionValid = Boolean(
    overview.VersionName &&
    toTimestamp(overview.VersionStartTime ?? '') > 0 &&
    toTimestamp(overview.VersionEndTime ?? '') > now
  )
  // 无有效版本时仅使用同一活动的标题、封面和时间，不拿卡池伪造版本周期。
  const activities = [...overview.Activities]
    .filter(item => toTimestamp(item.EndTime) > now)
    .sort((left, right) => toTimestamp(left.StartTime) - toTimestamp(right.StartTime))
  const activity = activities.find(item => toTimestamp(item.StartTime) <= now) ?? activities[0]
  return {
    // AKE 原生活动图可能数十 MB；兜底只显示文字，不直接加载这些大图。
    cover: versionValid
      ? (overview.VersionCover ?? '')
      : overview.SourceName === 'SRA'
        ? (activity?.CoverUrl ?? '')
        : '',
    version: versionValid ? overview.Version : '',
    subtitle: versionValid ? (overview.VersionName ?? '') : (activity?.Name ?? ''),
    startTime: versionValid ? (overview.VersionStartTime ?? '') : (activity?.StartTime ?? ''),
    endTime: versionValid ? (overview.VersionEndTime ?? '') : (activity?.EndTime ?? ''),
    available: overview.Available,
    stale: versionValid ? (overview.VersionStale ?? overview.Stale) : overview.Stale,
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
