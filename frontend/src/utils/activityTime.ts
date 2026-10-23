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
