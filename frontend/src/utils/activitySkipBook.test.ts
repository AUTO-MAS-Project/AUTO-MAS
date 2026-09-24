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
  // 非当日用远早固定日期，避免测试恰在 09-10 那天跑时把「昨日出错」也算命中
  const oldDay = '2020-01-01'
  const book = {
    今日出错: { days: 1, date: today, detail: '倒1 → SR-8' },
    连错: { days: 2, date: oldDay, detail: '倒2 → SR-7' },
    旧错当日: { days: 1, date: oldDay, detail: '倒3 → SR-6' },
  }

  it('hits today-first-error and period-skip entries only', () => {
    expect(activeSkipEntry({ 今日出错: book.今日出错 }, today)?.name).toBe('今日出错')
    expect(activeSkipEntry({ 连错: book.连错 }, today)?.name).toBe('连错')
    expect(activeSkipEntry({ 旧错当日: book.旧错当日 }, today)).toBeNull()
  })

  it('reports the entry with the most consecutive errors when several hit', () => {
    const hit = activeSkipEntry({ 今日出错: book.今日出错, 连错: book.连错 }, today)
    expect(hit?.name).toBe('连错')
  })
})
