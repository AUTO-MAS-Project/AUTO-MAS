import { createEmptyEndfieldActivityOverview, type EndfieldActivityOverview } from '@/types/home'
import { normalizeSraActivityTime as time } from './sraActivityTime'

const text = (value: unknown) => (typeof value === 'string' ? value.trim() : '')

const image = (value: unknown) => {
  const raw = text(value)
  try {
    return new URL(raw).protocol === 'https:' ? raw : ''
  } catch {
    return ''
  }
}

export const parseEndfieldSraData = (value: unknown): EndfieldActivityOverview => {
  if (!value || typeof value !== 'object') throw new Error('SRA 活动数据格式无效')
  const raw = value as Record<string, unknown>
  if (!Array.isArray(raw.activities)) throw new Error('SRA 缺少活动列表')
  const versionCover = image(raw.cover)
  const activities = raw.activities.flatMap(entry => {
    if (!entry || typeof entry !== 'object') return []
    const item = entry as Record<string, unknown>
    const name = text(item.name)
    const start = time(item.startTime)
    const end = time(item.endTime)
    if (!name || !start || !end || Date.parse(end) <= Date.parse(start)) return []
    // 上游可能复用版本公告封面，不将其冒充每个活动的独立图片。
    const cover = image(item.cover)
    const activityCover = cover === versionCover ? '' : cover
    return [
      {
        Id: `sra-${name}-${start}-${end}`,
        Name: name,
        StartTime: start,
        EndTime: end,
        ImageUrl: activityCover,
        CoverUrl: activityCover,
        Tags: text(item.kind) ? [text(item.kind)] : [],
      },
    ]
  })
  if (activities.length !== raw.activities.length) {
    throw new Error('SRA 活动数据不完整')
  }
  const start = time(raw.startTime)
  const end = time(raw.endTime)
  const versionValid = Boolean(
    text(raw.versionName) && start && end && Date.parse(end) > Date.parse(start)
  )
  return {
    ...createEmptyEndfieldActivityOverview(),
    Available: true,
    SourceName: 'SRA',
    SourceUrl: 'https://starrailassistant.top',
    Version: versionValid ? text(raw.version) : '',
    VersionName: versionValid ? text(raw.versionName) : '',
    VersionCover: versionValid ? versionCover : '',
    VersionStartTime: versionValid ? start : '',
    VersionEndTime: versionValid ? end : '',
    VersionStale: false,
    Activities: activities,
  }
}
