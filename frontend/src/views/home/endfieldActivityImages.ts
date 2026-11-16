import type { EndfieldActivityOverview } from '@/types/home'
import type { EndfieldSourceData } from './endfieldActivityTransform'

/** 仅去掉排版差异与引号外的活动类别，不做模糊子串匹配。 */
const normalizeName = (value: string): string => {
  const normalized = value.normalize('NFKC').trim()
  const quoted = normalized.match(
    /^[「『“"](.+)[」』”"](?:\s*(?:限时挑战|趣味活动|签到活动|引入活动|拍照活动|限时活动|挑战活动|叙事活动))?$/
  )
  return (quoted?.[1] ?? normalized).replace(/[\s「」『』“”"]/g, '').toLowerCase()
}

const activityKey = (name: string, start: number, end: number): string => {
  const normalized = normalizeName(name)
  if (!normalized || !Number.isFinite(start) || !Number.isFinite(end) || end <= start) return ''
  return JSON.stringify([normalized, start])
}

/**
 * 名称和开始时间必须相同；结束时间只容许闭区间/开区间造成的 1 秒边界差。
 * 两侧都唯一时才取 tabImg，完整 AKE 表包含未来活动与恢复快照。
 */
export const withEndfieldActivityImages = (
  activities: EndfieldActivityOverview['Activities'],
  akeActivities: EndfieldSourceData['activities']
): EndfieldActivityOverview['Activities'] => {
  const candidates = new Map<string, { index: number; end: number; image: string }[]>()
  akeActivities.forEach((activity, index) => {
    const start = activity.startTime?.getTime() ?? NaN
    const end = activity.endTime?.getTime() ?? NaN
    const key = activityKey(activity.name, start, end)
    if (!key) return
    const entries = candidates.get(key) ?? []
    entries.push({ index, end, image: activity.imageUrl })
    candidates.set(key, entries)
  })
  const counts = new Map<number, number>()
  const matches = activities.map(activity => {
    const end = Date.parse(activity.EndTime)
    const key = activityKey(activity.Name, Date.parse(activity.StartTime), end)
    const entries = (candidates.get(key) ?? []).filter(item => Math.abs(item.end - end) <= 1000)
    entries.forEach(item => counts.set(item.index, (counts.get(item.index) ?? 0) + 1))
    return entries
  })
  return activities.map((activity, index) => {
    const entries = matches[index]
    const match = entries.length === 1 && counts.get(entries[0].index) === 1 ? entries[0] : null
    return {
      ...activity,
      // 重名/重期/不确定时保留文字；不用 SRA 公告大图冒充活动小图。
      ImageUrl: match?.image ?? '',
    }
  })
}
