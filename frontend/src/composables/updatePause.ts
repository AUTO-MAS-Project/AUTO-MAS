/** 暂停更新：纯逻辑辅助（判停 / 格式化 / 日期选择器禁选范围） */
import type { Dayjs } from 'dayjs'

/** 最短暂停 1 天（截止日期最早为明天） */
export const PAUSE_MIN_DAYS = 1
/** 最长暂停 35 天（截止日期最晚为今天 + 35） */
export const PAUSE_MAX_DAYS = 35

const PAUSE_DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/

/** 本地日期归一为零填充 YYYY-MM-DD（供字符串字典序比较） */
function toLocalDateString(date: Date): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

/** 校验 YYYY-MM-DD 是否为真实存在的本地日期 */
function isValidDateString(value: string): boolean {
  if (!PAUSE_DATE_PATTERN.test(value)) return false
  const [year, month, day] = value.split('-').map(Number)
  const parsed = new Date(year, month - 1, day)
  return (
    parsed.getFullYear() === year && parsed.getMonth() === month - 1 && parsed.getDate() === day
  )
}

/**
 * 是否处于暂停期：today < pauseUntil（零填充日期串字典序比较）。
 * 截止日期当天即恢复；空串/非法值视为未暂停。
 * 每次求值都以当前系统日期为准，时钟越过截止日的下次求值自动恢复。
 */
export function isUpdatePaused(pauseUntil?: string | null, today: Date = new Date()): boolean {
  if (!pauseUntil || !isValidDateString(pauseUntil)) return false
  return toLocalDateString(today) < pauseUntil
}

/** 截止日期展示格式：YYYY-MM-DD → YYYY/MM/DD（状态文案 "直到xxxx/xx/xx为止"） */
export function formatPauseUntil(pauseUntil: string): string {
  return pauseUntil.replace(/-/g, '/')
}

/** 供 a-date-picker 的 disabledDate：禁用今天及以前（< 明天）与第 36 天以后（> 今天+35） */
export function getPauseDisabledDate(): (date: Dayjs) => boolean {
  return (date: Dayjs): boolean => {
    // 回调内取当前日期，防止跨午夜后仍按旧边界放行
    const now = new Date()
    const start = new Date(now.getFullYear(), now.getMonth(), now.getDate() + PAUSE_MIN_DAYS)
    const end = new Date(now.getFullYear(), now.getMonth(), now.getDate() + PAUSE_MAX_DAYS)
    // ant-design-vue 4 传入 Dayjs 实例，统一转回原生 Date 比较
    const value = date.toDate()
    return value < start || value > end
  }
}
