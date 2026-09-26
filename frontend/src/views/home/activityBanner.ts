import type {
  ActivityItem,
  EndfieldActivityOverview,
  HomeModuleKey,
  SraActivityOverview,
  StellaActivityOverview,
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
    startTime: useVersion ? overview.startTime : (activity?.startTime ?? ''),
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
    startTime: record?.StartTime || '',
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
    startTime: activity?.UtcStartTime ?? '',
    endTime: activity?.UtcExpireTime ?? '',
    available: activityData.length > 0,
    stale: false,
  }
}

/** 星塔旅人的活动封面在资源域下，站点给的是 `/stella/assets/...` 这样的相对路径 */
const STELLA_ASSET_BASE = 'https://api.ennead.cc'

export const stellaActivityBanner = (overview: StellaActivityOverview): ActivityBannerSource => {
  // 站点已按状态分组：进行中的有多条时取最早结束的那条（与其它卡片同口径）；
  // 一场都没进行时退回「最近结束的那场」，让卡片照碧蓝档案的样子显示已结束
  const ongoing = [...(overview.current ?? [])].sort(
    (left, right) => toTimestamp(left.endTime ?? '') - toTimestamp(right.endTime ?? '')
  )
  const lastEnded = [...(overview.ended ?? [])].sort(
    (left, right) => toTimestamp(right.endTime ?? '') - toTimestamp(left.endTime ?? '')
  )[0]
  const activity = ongoing[0] ?? lastEnded
  // 封面按「越大越优先」排一串候选，由轮播在 onerror 时逐个降级：
  //   1. 站点 background 1644×900 —— 能铺满，但常 404
  //   2. 官网横幅 795×510 —— 标题与当前活动对上号的那条（后端标记 matched），
  //      没对上才退到最新一条
  //   3. 站点 banner 310×138 —— 只能当右侧贴片
  const art = (path?: string) =>
    path ? (path.startsWith('http') ? path : STELLA_ASSET_BASE + path) : ''
  const officialList = overview.official ?? []
  const officialTop =
    officialList.find(item => item.matched && item.banner) ?? officialList.find(item => item.banner)
  const candidates = [
    art(activity?.textures?.background),
    art(officialTop?.banner),
    art(activity?.textures?.banner),
  ].filter(Boolean)

  // 没有进行中的活动：标题与封面都留着刚结束的那场，但不显示已经走完的倒计时，
  // 只留一句「后续活动即将开始」
  const hasOngoing = ongoing.length > 0
  return {
    cover: candidates[0] ?? '',
    coverCandidates: candidates.slice(1),
    subtitle: activity?.title ?? '',
    startTime: hasOngoing ? (activity?.startTime ?? '') : '',
    endTime: hasOngoing ? (activity?.endTime ?? '') : '',
    // 取到排期就算可用；没有进行中的活动时文案由轮播换「暂无进行中的活动」
    available: overview.Available,
    stale: overview.Stale ?? false,
    ended: !hasOngoing && Boolean(activity),
  }
}
