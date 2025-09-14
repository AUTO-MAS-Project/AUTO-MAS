/**
 * 获取今天是星期几
 * @returns {number} 返回数字的星期几 (0-6, 0表示星期日)
 */
export function getTodayWeekday(): number {
  const today = new Date()
  return today.getDay()
}

/**
 * 获取指定日期是星期几
 * @param {Date} utcDate UTC时间
 * @returns {number} 返回数字的星期几 (0-6, 0表示星期日)
 */
export function getWeekday(utcDate: Date): number {
  const today = new Date(utcDate.getTime() + 4 * 3600000)
  return today.getDay()
}

/**
 * 获取东12区当前时间
 * @returns {Date} 返回东12区当前时间的Date对象
 */
export function _getEastTwelveZoneTime(): Date {
  const now = new Date()
  // 获取UTC时间，然后加上12小时
  const utcTime = now.getTime() + now.getTimezoneOffset() * 60000
  return new Date(utcTime + 4 * 3600000)
}

/**
 * 获取东12区今天是星期几
 * @returns {number} 返回数字的星期几 (0-6, 0表示星期日)
 */
export function getTodayWeekdayEast12(): number {
  const east12Time = _getEastTwelveZoneTime()
  return east12Time.getDay()
}

/**
 * 获取东12区指定UTC时间对应的星期几
 * @param {Date} utcDate UTC时间
 * @returns {number} 返回数字的星期几 (0-6, 0表示星期日)
 */
export function getWeekdayEast12(utcDate: Date): number {
  const east12Time = new Date(utcDate.getTime() + 4 * 3600000)
  return east12Time.getDay()
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
