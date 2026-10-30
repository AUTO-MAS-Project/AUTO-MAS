import { describe, expect, it } from 'vite-plus/test'
import { nextWeekResetAt, weekKeyOf } from './taskboardWeek'

describe('taskboardWeek', () => {
  it('switches the week at Monday 04:00 Beijing time', () => {
    // 2026-10-25T19:59Z = 2026-10-26 03:59 北京时间，仍在上一周
    expect(weekKeyOf(Date.parse('2026-10-25T19:59:00Z'))).toBe('2026-10-19')
    // 2026-10-25T20:00Z = 2026-10-26 04:00 北京时间，换到新一周
    expect(weekKeyOf(Date.parse('2026-10-25T20:00:00Z'))).toBe('2026-10-26')
  })

  it('points the next reset at the following Monday 04:00 Beijing time', () => {
    const now = Date.parse('2026-10-28T00:00:00Z') // 周三 08:00 北京时间
    expect(nextWeekResetAt(now)).toBe(Date.parse('2026-11-02T04:00:00+08:00'))
  })
})
