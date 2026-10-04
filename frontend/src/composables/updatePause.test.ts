import { describe, expect, it } from 'vitest'
import dayjs from 'dayjs'
import { formatPauseUntil, getPauseDisabledDate, isUpdatePaused } from './updatePause'

const localDate = (year: number, month: number, day: number) => new Date(year, month - 1, day)

describe('isUpdatePaused', () => {
  const today = localDate(2026, 9, 30)

  it('空值与非法值不暂停', () => {
    expect(isUpdatePaused('', today)).toBe(false)
    expect(isUpdatePaused(null, today)).toBe(false)
    expect(isUpdatePaused(undefined, today)).toBe(false)
    expect(isUpdatePaused('abc', today)).toBe(false)
    expect(isUpdatePaused('2026-13-01', today)).toBe(false)
    expect(isUpdatePaused('2026-02-30', today)).toBe(false)
  })

  it('截止日当天恢复（今天 = 截止日不暂停）', () => {
    expect(isUpdatePaused('2026-09-30', today)).toBe(false)
  })

  it('明天为截止日时暂停中（最短 1 天）', () => {
    expect(isUpdatePaused('2026-10-01', today)).toBe(true)
  })

  it('未来日期暂停中，已过期日期不暂停', () => {
    expect(isUpdatePaused('2026-10-05', today)).toBe(true) // +5 天
    expect(isUpdatePaused('2026-09-29', today)).toBe(false) // 昨天
  })

  it('越过截止日后自动恢复（系统日期变化自愈）', () => {
    const until = '2026-11-04' // today + 35 天
    expect(isUpdatePaused(until, today)).toBe(true)
    expect(isUpdatePaused(until, localDate(2026, 11, 4))).toBe(false) // 到期当天恢复
    expect(isUpdatePaused(until, localDate(2026, 11, 5))).toBe(false) // 越过截止日
  })
})

describe('formatPauseUntil', () => {
  it('YYYY-MM-DD 转 YYYY/MM/DD', () => {
    expect(formatPauseUntil('2026-10-01')).toBe('2026/10/01')
    expect(formatPauseUntil('2026-12-31')).toBe('2026/12/31')
  })
})

describe('getPauseDisabledDate', () => {
  // disabledDate 回调内取当前日期，测试按运行时的今天计算边界，避免依赖墙钟日期
  // ant-design-vue 4 实际传入 Dayjs 实例，测试保持一致
  const dayOffset = (offset: number) => {
    const now = new Date()
    return dayjs(new Date(now.getFullYear(), now.getMonth(), now.getDate() + offset))
  }

  it('禁用今天及以前，明天起可选', () => {
    const disabled = getPauseDisabledDate()
    expect(disabled(dayOffset(-1))).toBe(true) // 昨天
    expect(disabled(dayOffset(0))).toBe(true) // 今天（最短 1 天）
    expect(disabled(dayOffset(1))).toBe(false) // 明天（最小值）
  })

  it('第 35 天可选，第 36 天禁用（最长 35 天）', () => {
    const disabled = getPauseDisabledDate()
    expect(disabled(dayOffset(30))).toBe(false) // 中间日期
    expect(disabled(dayOffset(35))).toBe(false) // 今天 + 35（最大值边界）
    expect(disabled(dayOffset(36))).toBe(true) // 超出最长暂停期
  })
})
