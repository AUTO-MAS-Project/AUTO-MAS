import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { currentMonthMarker, currentWeekMarker, getGameDayOffset } from './periodMarkers'

describe('currentWeekMarker', () => {
  it('stays on the old week before the game-day rollover at Beijing 04:00', () => {
    expect(currentWeekMarker(new Date('2026-09-14T03:59:00+08:00'))).toBe('2026-W37')
  })

  it('flips to the new week after the rollover', () => {
    expect(currentWeekMarker(new Date('2026-09-14T04:01:00+08:00'))).toBe('2026-W38')
  })

  it('labels the week with the ISO year of its Thursday', () => {
    expect(currentWeekMarker(new Date('2025-12-29T12:00:00+08:00'))).toBe('2026-W01')
    expect(currentWeekMarker(new Date('2026-01-01T12:00:00+08:00'))).toBe('2026-W01')
  })

  it('works without an explicit now', () => {
    expect(currentWeekMarker()).toMatch(/^\d{4}-W\d{2}$/)
  })
})

describe('currentMonthMarker', () => {
  it('stays on the old month before the UTC+4 rollover', () => {
    expect(currentMonthMarker(new Date('2026-10-01T03:59:00+08:00'))).toBe('2026-09')
  })

  it('flips to the new month after the rollover', () => {
    expect(currentMonthMarker(new Date('2026-10-01T04:01:00+08:00'))).toBe('2026-10')
  })
})

describe('getGameDayOffset', () => {
  it('matches the backend ARKNIGHTS_GAME_DAY_TZ table', () => {
    expect(getGameDayOffset('Official')).toBe(4)
    expect(getGameDayOffset('Bilibili')).toBe(4)
    expect(getGameDayOffset('txwy')).toBe(4)
    expect(getGameDayOffset('YoStarEN')).toBe(-11)
    expect(getGameDayOffset('YoStarJP')).toBe(5)
    expect(getGameDayOffset('YoStarKR')).toBe(5)
  })

  it('falls back to UTC+4 for unknown or empty servers', () => {
    expect(getGameDayOffset(undefined)).toBe(4)
    expect(getGameDayOffset(null)).toBe(4)
    expect(getGameDayOffset('')).toBe(4)
    expect(getGameDayOffset('Unknown')).toBe(4)
  })
})

describe('server-specific game day', () => {
  // UTC 2026-09-27 21:00 == 北京周一 05:00：国服已换到新一周，美服当地仍是周日 14:00
  const weekBoundary = new Date('2026-09-27T21:00:00Z')

  it('keeps EN on the previous ISO week while CN has rolled over', () => {
    expect(currentWeekMarker(weekBoundary)).toBe('2026-W40')
    expect(currentWeekMarker(weekBoundary, getGameDayOffset('Official'))).toBe('2026-W40')
    expect(currentWeekMarker(weekBoundary, getGameDayOffset('YoStarEN'))).toBe('2026-W39')
  })

  it('rolls JP over one hour before CN', () => {
    // UTC 2026-09-27 19:30 == 北京周一 03:30 / 东京周一 04:30
    const jpFirst = new Date('2026-09-27T19:30:00Z')
    expect(currentWeekMarker(jpFirst, getGameDayOffset('Official'))).toBe('2026-W39')
    expect(currentWeekMarker(jpFirst, getGameDayOffset('YoStarJP'))).toBe('2026-W40')
  })

  it('keeps EN on the previous month while CN has rolled over', () => {
    const monthBoundary = new Date('2026-09-30T21:00:00Z')
    expect(currentMonthMarker(monthBoundary)).toBe('2026-10')
    expect(currentMonthMarker(monthBoundary, getGameDayOffset('YoStarEN'))).toBe('2026-09')
  })
})

describe('periodMarkers call sites', () => {
  // emitSave 的 value 参数是 any，模板里漏掉调用括号类型检查抓不到，用源码文本锁住
  const source = readFileSync(new URL('./TaskPipelineSection.vue', import.meta.url), 'utf8')

  it('invokes the markers at render and save time instead of passing the function itself', () => {
    expect(source).toContain('=== serverWeekMarker()')
    expect(source).toContain('=== serverMonthMarker()')
    expect(source).toContain("emitSave('Data.AnnihilationCompletedWeek', serverWeekMarker())")
    expect(source).toContain("emitSave('Data.GreenTicketStoreMonth', serverMonthMarker())")
  })

  it('derives the markers from the user server game day', () => {
    expect(source).toContain('getGameDayOffset(formData.value.Info.Server)')
    expect(source).toContain('currentWeekMarker(new Date(), gameDayOffset())')
    expect(source).toContain('currentMonthMarker(new Date(), gameDayOffset())')
  })
})
