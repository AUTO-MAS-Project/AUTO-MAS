import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { currentMonthMarker, currentWeekMarker } from './periodMarkers'

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

describe('periodMarkers call sites', () => {
  // emitSave 的 value 参数是 any，模板里漏掉调用括号类型检查抓不到，用源码文本锁住
  const source = readFileSync(new URL('./TaskPipelineSection.vue', import.meta.url), 'utf8')

  it('invokes the markers at render and save time instead of passing the function itself', () => {
    expect(source).toContain('=== currentWeekMarker()')
    expect(source).toContain('=== currentMonthMarker()')
    expect(source).toContain("emitSave('Data.AnnihilationCompletedWeek', currentWeekMarker())")
    expect(source).toContain("emitSave('Data.GreenTicketStoreMonth', currentMonthMarker())")
  })
})
