/**
 * 活动时间统一按界面语言格式化。
 *
 * 各活动卡片原来都把 zh-CN 写死在 `toLocaleString` 里，界面切到英文或日文后日期还是
 * 中文格式；这里收成一处，调用方把当前语言传进来即可。
 */
export const formatActivityTime = (value: string, locale: string): string => {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return ''
  }
  return date.toLocaleString(locale, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}
