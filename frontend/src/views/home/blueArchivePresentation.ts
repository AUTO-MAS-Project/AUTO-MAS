import type { BlueArchiveActivityOverview } from '@/types/home'

/** 标题、封面和时间必须来自同一活动，也兼容旧缓存里的服务器占位标题。 */
export const blueArchivePresentation = (
  overview: BlueArchiveActivityOverview,
  now = Date.now()
): BlueArchiveActivityOverview => {
  const time = (value: string) => new Date(value).getTime()
  // 开始与结束同一时刻的条目（如「常驻化」公告）不是一段活动，挑出来也没法展示
  const activities = overview.activities.filter(item => time(item.endTime) > time(item.startTime))
  const running = activities
    .filter(item => time(item.startTime) <= now && time(item.endTime) > now)
    .sort((a, b) => time(a.endTime) - time(b.endTime))
  const upcoming = activities
    .filter(item => time(item.startTime) > now)
    .sort((a, b) => time(a.startTime) - time(b.startTime))
  const ended = activities
    .filter(item => time(item.endTime) <= now)
    .sort((a, b) => time(b.endTime) - time(a.endTime))
  // 进行中的活动优先；活动间隙先让位给已排期的下一场，两者都没有才退回最近结束的那一场，
  // 免得卡片在活动间隙整个空掉
  const current = running[0] ?? upcoming[0] ?? ended[0]
  return {
    ...overview,
    versionName: current?.name ?? '',
    cover: current?.cover ?? '',
    startTime: current?.startTime ?? '',
    endTime: current?.endTime ?? '',
  }
}
