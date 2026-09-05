/**
 * 时区处理工具 - 所有时间比较都基于Date类型而不是字符串比较
 */

/**
 * 获取指定时区的当前时间Date对象
 * @param {number} timezoneOffset 时区偏移量（小时），例如：4表示UTC+4，8表示UTC+8
 * @returns {Date} 返回指定时区的当前时间Date对象
 */
export function getCurrentTimeInTimezone(timezoneOffset: number): Date {
  const now = new Date()
  // 加上时区偏移量
  const timezoneTime = now.getTime() + timezoneOffset * 60 * 60 * 1000
  return new Date(timezoneTime)
}

/**
 * 获取指定时区今天是星期几
 * @param {number} timezoneOffset 时区偏移量（小时）
 * @returns {number} 返回数字的星期几 (0-6, 0表示星期日)
 */
export function getWeekdayInTimezone(timezoneOffset: number): number {
  const timezoneTime = getCurrentTimeInTimezone(timezoneOffset)
  return timezoneTime.getUTCDay()
}
