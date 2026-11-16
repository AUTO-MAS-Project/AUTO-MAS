/** SRA 无时区时间按 UTC+8 解释，供各游戏的数据入口和缓存恢复共用。 */
export const normalizeSraActivityTime = (value: unknown): string => {
  const raw = typeof value === 'string' ? value.trim() : ''
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
