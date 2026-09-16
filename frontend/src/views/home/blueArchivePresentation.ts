import type { BlueArchiveActivityOverview } from '@/types/home'

/** 标题、封面和时间必须来自同一活动，也兼容旧缓存里的服务器占位标题。 */
export const blueArchivePresentation = (
  overview: BlueArchiveActivityOverview,
  now = Date.now()
): BlueArchiveActivityOverview => {
  const time = (value: string) => new Date(value).getTime()
  const activities = overview.activities
  const running = activities
    .filter(item => time(item.startTime) <= now && time(item.endTime) > now)
    .sort((a, b) => time(a.endTime) - time(b.endTime))
  const ended = activities
    .filter(item => time(item.endTime) <= now)
    .sort((a, b) => time(b.endTime) - time(a.endTime))
  const upcoming = activities
    .filter(item => time(item.startTime) > now)
    .sort((a, b) => time(a.startTime) - time(b.startTime))
  const current = running[0] ?? ended[0] ?? upcoming[0]
  return {
    ...overview,
    versionName: current?.name ?? '',
    cover: current?.cover ?? '',
    startTime: current?.startTime ?? '',
    endTime: current?.endTime ?? '',
  }
}
