/**
 * 时区处理工具 - 所有时间比较都基于Date类型而不是字符串比较
 */

/**
 * 解析字符串日期为UTC Date对象，指定源时区
 * @param {string} dateString 日期字符串，格式为YYYY-MM-DD
 * @param {number} sourceTimezone 源时区偏移量（小时），例如：4表示UTC+4，8表示UTC+8
 * @returns {Date} 返回对应的UTC Date对象
 */
export function parseStringToUTCDate(dateString: string, sourceTimezone: number): Date {
  if (!dateString) {
    throw new Error('日期字符串不能为空')
  }

  // 解析日期字符串 YYYY-MM-DD
  const dateParts = dateString.split('-')
  if (dateParts.length !== 3) {
    throw new Error('日期格式必须为 YYYY-MM-DD')
  }

  const year = parseInt(dateParts[0], 10)
  const month = parseInt(dateParts[1], 10) - 1 // Date构造函数的月份从0开始
  const day = parseInt(dateParts[2], 10)

  // 直接创建UTC时间，避免本地时区影响
  // 将指定时区的日期转换为UTC时间：UTC时间 = 本地时间 - 时区偏移
  const utcDate = new Date(Date.UTC(year, month, day))
  const timezoneOffsetMs = sourceTimezone * 60 * 60 * 1000

  return new Date(utcDate.getTime() - timezoneOffsetMs)
}

/**
 * 获取指定时区的当前时间Date对象
 * @param {number} timezoneOffset 时区偏移量（小时），例如：4表示UTC+4，8表示UTC+8
 * @returns {Date} 返回指定时区的当前时间Date对象
 */
export function getCurrentTimeInTimezone(timezoneOffset: number): Date {
  const now = new Date()
  // 加上时区偏移量
  const timezoneTime = now.getTime() + (timezoneOffset * 60 * 60 * 1000)
  return new Date(timezoneTime)
}

/**
 * 将Date对象转换为指定时区的日期字符串（YYYY-MM-DD格式）
 * @param {Date} date UTC Date对象
 * @param {number} timezoneOffset 目标时区偏移量（小时）
 * @returns {string} 返回格式为YYYY-MM-DD的日期字符串
 */
export function formatDateToTimezoneString(date: Date, timezoneOffset: number): string {
  const timezoneTime = date.getTime() + (timezoneOffset * 60 * 60 * 1000)
  const timezoneDate = new Date(timezoneTime)

  const year = timezoneDate.getUTCFullYear()
  const month = String(timezoneDate.getUTCMonth() + 1).padStart(2, '0')
  const day = String(timezoneDate.getUTCDate()).padStart(2, '0')

  return `${year}-${month}-${day}`
}

/**
 * 获取指定时区今天的Date对象（仅包含日期，时间为00:00:00 UTC）
 * @param {number} timezoneOffset 时区偏移量（小时）
 * @returns {Date} 返回今天的UTC Date对象
 */
export function getTodayInTimezone(timezoneOffset: number): Date {
  const now = new Date()
  const timezoneTime = now.getTime() + (timezoneOffset * 60 * 60 * 1000)
  const timezoneDate = new Date(timezoneTime)

  // 获取时区日期的年月日（使用UTC方法避免本地时区影响）
  const year = timezoneDate.getUTCFullYear()
  const month = timezoneDate.getUTCMonth()
  const day = timezoneDate.getUTCDate()

  // 创建该日期在指定时区的00:00:00时刻，然后转换为UTC
  const timezoneStartOfDay = Date.UTC(year, month, day)
  const utcStartOfDay = timezoneStartOfDay - (timezoneOffset * 60 * 60 * 1000)

  return new Date(utcStartOfDay)
}

/**
 * 获取指定时区本周一的Date对象（仅包含日期，时间为00:00:00 UTC）
 * @param {number} timezoneOffset 时区偏移量（小时）
 * @returns {Date} 返回本周一的UTC Date对象
 */
export function getWeekStartInTimezone(timezoneOffset: number): Date {
  const now = new Date()
  const timezoneTime = now.getTime() + (timezoneOffset * 60 * 60 * 1000)
  const timezoneDate = new Date(timezoneTime)

  // 获取时区中的当前日期（使用UTC方法避免本地时区影响）
  const year = timezoneDate.getUTCFullYear()
  const month = timezoneDate.getUTCMonth()
  const day = timezoneDate.getUTCDate()
  const weekday = timezoneDate.getUTCDay()

  // 计算到周一的天数差
  const diff = weekday === 0 ? -6 : 1 - weekday // 如果是周日，调整为上周一

  // 创建本周一的UTC日期，然后转换为指定时区的起始时刻
  const mondayUTC = Date.UTC(year, month, day + diff)
  const mondayInTimezone = mondayUTC - (timezoneOffset * 60 * 60 * 1000)

  return new Date(mondayInTimezone)
}/**
 * 获取指定时区今天是星期几
 * @param {number} timezoneOffset 时区偏移量（小时）
 * @returns {number} 返回数字的星期几 (0-6, 0表示星期日)
 */
export function getWeekdayInTimezone(timezoneOffset: number): number {
  const timezoneTime = getCurrentTimeInTimezone(timezoneOffset)
  return timezoneTime.getUTCDay()
}

/**
 * 检查日期是否在指定的时间范围内（包含边界）
 * @param {string} dateString 要检查的日期字符串 YYYY-MM-DD
 * @param {Date} startDate 开始日期（UTC Date对象）
 * @param {Date} endDate 结束日期（UTC Date对象）
 * @param {number} dateTimezone 日期字符串的时区
 * @returns {boolean} 是否在范围内
 */
export function isDateInRange(
  dateString: string,
  startDate: Date,
  endDate: Date,
  dateTimezone: number
): boolean {
  if (!dateString) return false

  try {
    const targetDate = parseStringToUTCDate(dateString, dateTimezone)
    return targetDate >= startDate && targetDate <= endDate
  } catch {
    return false
  }
}

/**
 * 检查日期是否等于指定日期
 * @param {string} dateString 要检查的日期字符串 YYYY-MM-DD
 * @param {Date} targetDate 目标日期（UTC Date对象）
 * @param {number} dateTimezone 日期字符串的时区
 * @returns {boolean} 是否相等
 */
export function isDateEqual(
  dateString: string,
  targetDate: Date,
  dateTimezone: number
): boolean {
  if (!dateString) return false

  try {
    const date = parseStringToUTCDate(dateString, dateTimezone)
    return date.getTime() === targetDate.getTime()
  } catch {
    return false
  }
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
