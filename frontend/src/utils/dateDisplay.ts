const ISO_DATE_RE = /^\d{4}-\d{2}-\d{2}$/
const ISO_MONTH_RE = /^\d{4}-\d{2}$/
const ISO_WEEK_RE = /^(\d{4})-W(\d{2})$/
const ISO_DATETIME_RE =
  /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?(?:\.(\d+))?(?:Z|[+-]\d{2}:?\d{2})?$/
const CN_DATETIME_RE =
  /^(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日\s*(\d{1,2}):(\d{2})(?::(\d{2}))?$/

const pad2 = (value: number) => String(value).padStart(2, '0')

const toLocalDate = (
  year: number,
  month: number,
  day: number,
  hour = 0,
  minute = 0,
  second = 0,
  millisecond = 0
) => new Date(year, month - 1, day, hour, minute, second, millisecond)

export const parseBackendDateTime = (value: string): Date | null => {
  if (!value) return null

  // 优先解析旧中文格式，避免依赖浏览器对本地化日期字符串的支持。
  const cnMatch = value.trim().match(CN_DATETIME_RE)
  if (cnMatch) {
    const [, y, mo, d, h, mi, s = '0'] = cnMatch
    return toLocalDate(Number(y), Number(mo), Number(d), Number(h), Number(mi), Number(s))
  }

  const normalized = value.includes(' ') ? value.replace(' ', 'T') : value
  const parsed = new Date(normalized)
  if (!Number.isNaN(parsed.getTime())) return parsed

  const isoMatch = value.trim().match(ISO_DATETIME_RE)
  if (isoMatch) {
    const [, y, mo, d, h, mi, s = '0', ms = '0'] = isoMatch
    return toLocalDate(
      Number(y),
      Number(mo),
      Number(d),
      Number(h),
      Number(mi),
      Number(s),
      Number(ms.slice(0, 3).padEnd(3, '0'))
    )
  }

  return null
}

export const formatBackendDateTime = (value: string): string => {
  const date = parseBackendDateTime(value)
  if (!date) return value

  return `${date.getFullYear()}年${pad2(date.getMonth() + 1)}月${pad2(date.getDate())}日 ${pad2(
    date.getHours()
  )}:${pad2(date.getMinutes())}:${pad2(date.getSeconds())}`
}

export const formatHistoryGroupLabel = (value: string): string => {
  if (!value) return value

  if (ISO_DATE_RE.test(value)) {
    const [year, month, day] = value.split('-')
    return `${year}年${month}月${day}日`
  }

  if (ISO_MONTH_RE.test(value)) {
    const [year, month] = value.split('-')
    return `${year}年${month}月`
  }

  const weekMatch = value.match(ISO_WEEK_RE)
  if (weekMatch) {
    const [, year, week] = weekMatch
    return `${year}年 第${week}周`
  }

  return value
}
