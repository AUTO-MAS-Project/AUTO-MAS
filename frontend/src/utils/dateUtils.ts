/**
 * 获取今天是星期几
 * @returns {number} 返回数字的星期几 (0-6, 0表示星期日)
 */
export function getTodayWeekday(): number {
  const today = new Date()
  return today.getDay()
}

/**
 * 获取指定UTC偏移量的当前时间
 * @param {number} utcOffset UTC偏移量（小时），例如：-4表示UTC-4，8表示UTC+8，0表示UTC时间
 * @returns {Date} 返回指定时区的当前时间Date对象
 */
export function getTimeByUTCOffset(utcOffset: number): Date {
  const now = new Date()
  // UTC偏移量转换为分钟
  const offsetMinutes = utcOffset * 60
  return new Date(now.getTime() + (now.getTimezoneOffset() + offsetMinutes) * 60 * 1000)
}

/**
 * 获取指定UTC偏移量的当前日期字符串（YYYY-MM-DD格式）
 * @param {number} utcOffset UTC偏移量（小时）
 * @returns {string} 返回格式为YYYY-MM-DD的日期字符串
 */
export function getDateStringByUTCOffset(utcOffset: number): string {
  const time = getTimeByUTCOffset(utcOffset)
  return time.toISOString().split('T')[0]
}

/**
 * 获取指定UTC偏移量的本周一日期字符串（YYYY-MM-DD格式）
 * @param {number} utcOffset UTC偏移量（小时）
 * @returns {string} 返回格式为YYYY-MM-DD的本周一日期字符串
 */
export function getWeekStartByUTCOffset(utcOffset: number): string {
  const time = getTimeByUTCOffset(utcOffset)
  const startOfWeek = new Date(time)
  const day = startOfWeek.getDay()
  const diff = startOfWeek.getDate() - day + (day === 0 ? -6 : 1) // 如果是周日，调整为上周一
  startOfWeek.setDate(diff)
  return startOfWeek.toISOString().split('T')[0]
}

/**
 * 获取指定UTC偏移量的今天是星期几
 * @param {number} utcOffset UTC偏移量（小时）
 * @returns {number} 返回数字的星期几 (0-6, 0表示星期日)
 */
export function getWeekdayByUTCOffset(utcOffset: number): number {
  const time = getTimeByUTCOffset(utcOffset)
  return time.getDay()
}

/**
 * 将数字的星期几转换为中文
 * @param {number} weekday 数字的星期几 (0-6, 0表示星期日)
 * @returns {string} 返回中文的星期几
 */
export function getChineseDateString(weekday: number): string {
  const weekdays = ['星期日', '星期一', '星期二', '星期三', '星期四', '星期五', '星期六']
  if (weekday < 0 || weekday > 6) {
    throw new Error('weekday must be between 0 and 6')
  }
  return weekdays[weekday]
}
