// 与后端 AutoProxy 的周期标记保持一致：都按 UTC+4（游戏 04:00 换日）计算当前日期。
const currentUtc4Date = () => {
  const shifted = new Date(Date.now() + 4 * 60 * 60 * 1000)
  return new Date(
    Date.UTC(shifted.getUTCFullYear(), shifted.getUTCMonth(), shifted.getUTCDate())
  )
}

// 对应 _current_week_marker：取 UTC+4 的日期后按 ISO 规则落到本周四，避免时移残留导致周数 +1。
export const currentWeekMarker = (() => {
  const date = currentUtc4Date()
  const day = date.getUTCDay() || 7
  date.setUTCDate(date.getUTCDate() + 4 - day)
  const yearStart = new Date(Date.UTC(date.getUTCFullYear(), 0, 1))
  const week = Math.ceil(((date.getTime() - yearStart.getTime()) / 86400000 + 1) / 7)
  return `${date.getUTCFullYear()}-W${String(week).padStart(2, '0')}`
})()

// 对应 _current_month_marker：UTC+4 下的 %Y-%m
export const currentMonthMarker = (() => {
  const date = currentUtc4Date()
  return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, '0')}`
})()
