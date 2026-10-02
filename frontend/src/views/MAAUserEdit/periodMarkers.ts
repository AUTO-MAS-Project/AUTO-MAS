// 明日方舟各区服的游戏日时区偏移（小时）：服务器当地 04:00 换日，即服务器时区减 4 小时。
// 与后端 app/utils/constants.py 的 ARKNIGHTS_GAME_DAY_TZ 保持一致，改动时两边同步；
// 来源 MAA DateTimeExtension.cs（YoStarEN 为固定 UTC-7，不随夏令时）。
const ARKNIGHTS_GAME_DAY_OFFSET: Record<string, number> = {
  YoStarEN: -11,
  YoStarJP: 5,
  YoStarKR: 5,
}

// 国服 / B服 / 台服与未知区服都按 UTC+4
export const getGameDayOffset = (server?: string | null) =>
  ARKNIGHTS_GAME_DAY_OFFSET[server ?? ''] ?? 4

// 与后端 AutoProxy 的周期标记保持一致：按区服的游戏日时区（默认 UTC+4）计算当前日期。
// 必须每次调用现算：此前是模块加载时求值的常量，界面跨周/跨月开启后徽标会一直
// 拿旧周期比对，剿灭/绿票已完成仍显示未完成，重启软件才恢复。
const toGameDayDate = (now: Date = new Date(), offsetHours = 4) => {
  const shifted = new Date(now.getTime() + offsetHours * 60 * 60 * 1000)
  return new Date(Date.UTC(shifted.getUTCFullYear(), shifted.getUTCMonth(), shifted.getUTCDate()))
}

// 对应 _current_week_marker：取游戏日日期后按 ISO 规则落到本周四，避免时移残留导致周数 +1。
export const currentWeekMarker = (now: Date = new Date(), offsetHours = 4) => {
  const date = toGameDayDate(now, offsetHours)
  const day = date.getUTCDay() || 7
  date.setUTCDate(date.getUTCDate() + 4 - day)
  const yearStart = new Date(Date.UTC(date.getUTCFullYear(), 0, 1))
  const week = Math.ceil(((date.getTime() - yearStart.getTime()) / 86400000 + 1) / 7)
  return `${date.getUTCFullYear()}-W${String(week).padStart(2, '0')}`
}

// 对应 _current_month_marker：游戏日时区下的 %Y-%m
export const currentMonthMarker = (now: Date = new Date(), offsetHours = 4) => {
  const date = toGameDayDate(now, offsetHours)
  return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, '0')}`
}
