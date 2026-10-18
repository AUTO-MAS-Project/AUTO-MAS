import type { BlueArchiveActivityOverview } from '@/types/home'

/** 都归在「活动」分类里、但不是限时活动的那几类，不上横幅 */
const BANNER_EXCLUDED_KEYWORDS = ['战斗通行证', '网页活动']

/** 上面的大横幅只留这一类，其余分类都归下面的列表 */
const BANNER_KIND = '活动'

/** 标题、封面和时间必须来自同一活动，也兼容旧缓存里的服务器占位标题。 */
export const blueArchivePresentation = (
  overview: BlueArchiveActivityOverview,
  now = Date.now()
): BlueArchiveActivityOverview => {
  const time = (value: string) => new Date(value).getTime()
  // 开始与结束同一时刻的条目（如「常驻化」公告）不是一段活动，挑出来也没法展示
  const activities = overview.activities.filter(item => time(item.endTime) > time(item.startTime))
  // 上面的大横幅只留给「活动」这一类；总力大决、爬塔、多倍活动这些归下面的列表。
  // 其它游戏没有 kind 字段，一律按活动处理
  const bannerCandidates = activities.filter(
    item =>
      (!item.kind || item.kind === BANNER_KIND) &&
      !BANNER_EXCLUDED_KEYWORDS.some(keyword => item.name.includes(keyword))
  )
  const running = bannerCandidates
    .filter(item => time(item.startTime) <= now && time(item.endTime) > now)
    .sort((a, b) => time(a.endTime) - time(b.endTime))
  const upcoming = bannerCandidates
    .filter(item => time(item.startTime) > now)
    .sort((a, b) => time(a.startTime) - time(b.startTime))
  const ended = bannerCandidates
    .filter(item => time(item.endTime) <= now)
    .sort((a, b) => time(b.endTime) - time(a.endTime))
  // 进行中的活动优先；活动间隙先让位给已排期的下一场，两者都没有才退回最近结束的那一场，
  // 免得卡片在活动间隙整个空掉
  const current = running[0] ?? upcoming[0] ?? ended[0]
  return {
    ...overview,
    // 一并回传过滤后的列表：组件按 activities.length 判断有没有活动可展示，
    // 留着零时长条目会让它在没有真活动时误判为非空、渲染出空白的卡片
    activities,
    versionName: current?.name ?? '',
    cover: current?.cover ?? '',
    startTime: current?.startTime ?? '',
    endTime: current?.endTime ?? '',
  }
}
