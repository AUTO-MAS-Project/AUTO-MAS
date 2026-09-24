// 活动关跳过簿共享纯逻辑的测试：闸门判定与「活动是否仍在进行」的过滤口径，
// 脚本页徽标与计划表指派表都依赖这两条，两边必须一致。
import { describe, expect, it } from 'vitest'
import { activeSkipEntry, activityToday, ongoingSkipBook } from './activitySkipBook'

describe('ongoingSkipBook', () => {
  const book = {
    本期活动: { days: 2, date: '2026-09-10', detail: '倒1 → SR-8' },
    上期活动: { days: 2, date: '2026-08-01', detail: '倒2 → AT-7' },
  }

  it('drops entries whose activity is no longer ongoing', () => {
    const kept = ongoingSkipBook(book, new Set(['本期活动']))
    expect(Object.keys(kept)).toEqual(['本期活动'])
  })

  it('treats missing server data as no ongoing activity', () => {
    // 取不到该服当期关卡（未加载或拉取失败）时不显示徽标，与计划表页同口径
    expect(ongoingSkipBook(book, undefined)).toEqual({})
    expect(ongoingSkipBook(book, new Set())).toEqual({})
  })
})

describe('activeSkipEntry', () => {
  const today = activityToday()
  // 非当日用远早固定日期，避免测试恰在那天跑时把旧条目也算命中
  const oldDay = '2020-01-01'
  const book = {
    今日出错: { days: 1, date: today, detail: '倒1 → SR-8' },
    昨日出错: { days: 2, date: oldDay, detail: '倒2 → SR-7' },
  }

  it('hits only the entry recorded today', () => {
    // 闸门只看到当日为止：次日自动重试，不需要人工解锁
    expect(activeSkipEntry({ 今日出错: book.今日出错 }, today)?.name).toBe('今日出错')
    expect(activeSkipEntry({ 昨日出错: book.昨日出错 }, today)).toBeNull()
  })

  it('reports the entry with the most consecutive errors when several hit today', () => {
    const sameDay = { ...book.今日出错, days: 3 }
    const hit = activeSkipEntry({ 今日出错: book.今日出错, 连错三天: sameDay }, today)
    expect(hit?.name).toBe('连错三天')
  })
})
