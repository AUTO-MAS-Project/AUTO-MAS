/**
 * 活动时间解析：带时区（Z / ±HH:MM / ±HHMM）的 ISO 直接解析，
 * 裸时间按北京时间补 +08:00。任务台的列表、排序、归档共用这一份。
 */
export const parseActivityTime = (value?: string): number => {
  if (!value) return 0
  const raw = value.trim()
  if (/[zZ]$|[+-]\d{2}:?\d{2}$/.test(raw)) {
    const ts = Date.parse(raw)
    return Number.isNaN(ts) ? 0 : ts
  }
  const ts = Date.parse(raw.replace(' ', 'T') + '+08:00')
  return Number.isNaN(ts) ? 0 : ts
}

const pad = (value: number) => String(value).padStart(2, '0')

/** 按北京时间输出 M/D 或完整日期时间；无法解析返回空串。 */
export const formatBeijingDate = (value?: string, withTime = false): string => {
  const timestamp = parseActivityTime(value)
  if (!timestamp) return ''
  const date = new Date(timestamp + 8 * 3_600_000)
  if (!withTime) return `${date.getUTCMonth() + 1}/${date.getUTCDate()}`
  return `${date.getUTCFullYear()}-${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())} ${pad(date.getUTCHours())}:${pad(date.getUTCMinutes())}`
}

/** 当前北京时间，格式与后端任务台完成时间一致。 */
export const beijingNowText = (): string => formatBeijingDate(new Date().toISOString(), true)
