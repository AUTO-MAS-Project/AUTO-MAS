import { createEmptyEndfieldActivityOverview, type EndfieldActivityOverview } from '@/types/home'

const text = (value: unknown) => (typeof value === 'string' ? value.trim() : '')

/** SRA 中文档使用国服时间；无时区字符串按 UTC+8，而非用户电脑的时区。 */
const time = (value: unknown) => {
  const raw = text(value)
  const parts = raw.match(
    /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2})(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?$/
  )
  if (!parts) return ''
  const [, year, month, day, hour, minute, second, fraction, zone] = parts
  const y = Number(year)
  const m = Number(month)
  const leapYear = y % 4 === 0 && (y % 100 !== 0 || y % 400 === 0)
  const days = [31, leapYear ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
  if (
    m < 1 ||
    m > 12 ||
    Number(day) < 1 ||
    Number(day) > days[m - 1] ||
    Number(hour) > 23 ||
    Number(minute) > 59 ||
    Number(second ?? '0') > 59
  )
    return ''
  const normalized = `${year}-${month}-${day}T${hour}:${minute}:${second ?? '00'}${fraction ?? ''}${zone ?? '+08:00'}`
  if (!Number.isFinite(Date.parse(normalized))) return ''
  // 明确带时区的来源字符串保留原样；其余只接受上述可确认的日期时间格式。
  return zone ? raw : normalized
}

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
  const start = time(raw.startTime)
  const end = time(raw.endTime)
  const versionValid = Boolean(
    text(raw.versionName) && start && end && Date.parse(end) > Date.parse(start)
  )
  if (!versionValid && activities.length === 0 && raw.activities.length > 0) {
    throw new Error('SRA 活动时间无效')
  }
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
