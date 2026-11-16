import dayjs, { type Dayjs } from 'dayjs'
import utc from 'dayjs/plugin/utc'

dayjs.extend(utc)

// 配置状态保留完整带时区 ISO；控件用 UTC 承载显示钟点，避免浏览器 DST 修改钟点。
// 控件值不是配置时刻，须经 serializeConfigTime 按显示偏移还原，不能直接 toISOString。
// TODO(DST): 当前使用固定偏移；跨夏令时日期及页面打开期间偏移变化的策略留待统一处理。
export const parseConfigTime = (
  value: string,
  offsetMinutes = dayjs().utcOffset()
): Dayjs | undefined => {
  if (!value) return undefined
  const parsed = /^\d{2}:\d{2}$/.test(value)
    ? dayjs.utc(`2000-01-01T${value}:00`)
    : dayjs.utc(value)
  if (!parsed.isValid()) return undefined
  // 无偏移的日期/钟点来自界面输入；已有偏移的载荷先按真实时刻转为显示钟点。
  return /(?:Z|[+-]\d{2}:?\d{2})$/.test(value) ? parsed.add(offsetMinutes, 'minute') : parsed
}

export const formatConfigDate = (
  value: string | null | undefined,
  offsetMinutes = dayjs().utcOffset()
): string => {
  if (!value || /^\d{4}-\d{2}-\d{2}$/.test(value)) return value ?? ''
  return parseConfigTime(value, offsetMinutes)?.format('YYYY-MM-DD') ?? value
}

export const serializeConfigTime = (
  value: Dayjs | string,
  original = '',
  offsetMinutes = dayjs().utcOffset()
): string => {
  const parsed = dayjs.isDayjs(value) ? value : parseConfigTime(value, offsetMinutes)
  if (!parsed?.isValid()) throw new Error('Invalid configuration datetime')
  // Dayjs 只能保留毫秒；时分选择器不编辑的小数位从原载荷原样带回。
  const fraction =
    original.match(/(\.\d+)(?:Z|[+-]\d{2}:?\d{2})?$/)?.[1] ??
    (parsed.millisecond() ? parsed.format('.SSS') : '')
  const sign = offsetMinutes < 0 ? '-' : '+'
  const hours = String(Math.floor(Math.abs(offsetMinutes) / 60)).padStart(2, '0')
  const minutes = String(Math.abs(offsetMinutes) % 60).padStart(2, '0')
  return `${parsed.format('YYYY-MM-DDTHH:mm:ss')}${fraction}${sign}${hours}:${minutes}`
}
