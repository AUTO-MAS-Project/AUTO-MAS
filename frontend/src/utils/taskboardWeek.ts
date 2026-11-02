const HOUR = 3_600_000
const DAY = 86_400_000
/** 每周任务在北京时间周一 04:00 换周。 */
const RESET_HOUR = 4
const BEIJING_OFFSET = 8 * HOUR

/**
 * 当前周键，与后端 `weekly_key()` 同一规则：北京时间周一 04:00 换周，返回换周后周一的日期。
 * 前端用它判断勾选状态，避免长期开着的窗口跨周后仍显示上周的完成记录。
 */
export const weekKeyOf = (now: number = Date.now()): string => {
  const shifted = new Date(now + BEIJING_OFFSET - RESET_HOUR * HOUR)
  const weekday = (shifted.getUTCDay() + 6) % 7
  shifted.setUTCDate(shifted.getUTCDate() - weekday)
  return shifted.toISOString().slice(0, 10)
}

/** 下一次换周的时间戳，用于安排一次性的到期刷新。 */
export const nextWeekResetAt = (now: number = Date.now()): number =>
  Date.parse(`${weekKeyOf(now)}T04:00:00+08:00`) + 7 * DAY
