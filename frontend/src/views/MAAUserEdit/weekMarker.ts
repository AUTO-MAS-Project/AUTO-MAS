// 与后端 AutoProxy._current_week_marker（UTC+4 ISO 周）保持一致。
// 先取 UTC+4 的日期（丢弃时分秒），再按 ISO 规则落到本周四，避免时移残留导致周数 +1。
export const currentWeekMarker = (() => {
  const shifted = new Date(Date.now() + 4 * 60 * 60 * 1000)
  const date = new Date(
    Date.UTC(shifted.getUTCFullYear(), shifted.getUTCMonth(), shifted.getUTCDate())
  )
  const day = date.getUTCDay() || 7
  date.setUTCDate(date.getUTCDate() + 4 - day)
  const yearStart = new Date(Date.UTC(date.getUTCFullYear(), 0, 1))
  const week = Math.ceil(((date.getTime() - yearStart.getTime()) / 86400000 + 1) / 7)
  return `${date.getUTCFullYear()}-W${String(week).padStart(2, '0')}`
})()
