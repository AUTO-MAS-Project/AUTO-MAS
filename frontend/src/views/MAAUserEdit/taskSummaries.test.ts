import { describe, expect, it } from 'vitest'
import {
  summarizeActivity,
  summarizeAnnihilation,
  summarizeDepot,
  summarizeFight,
} from './taskSummaries'

describe('annihilation summary', () => {
  it('collapses to 已关闭 when stage is Close', () => {
    expect(summarizeAnnihilation('Close', 'Monday', false)).toBe('已关闭')
  })

  it('shows stage, start weekday and weekly progress', () => {
    expect(summarizeAnnihilation('Annihilation', 'Wednesday', true)).toBe(
      '当期剿灭 · 周三起 · 本周已完成'
    )
  })

  it('falls back to the raw value for an unknown stage', () => {
    expect(summarizeAnnihilation('Future@Annihilation', 'Monday', false)).toBe(
      'Future@Annihilation · 周一起 · 本周未完成'
    )
  })
})

describe('activity summary', () => {
  const base = { enabled: true, loading: false, optionCount: 3, medicine: 0 }

  it('reports the loading state before options arrive', () => {
    expect(summarizeActivity({ ...base, loading: true })).toBe('加载中…')
  })

  it('reports when the server has no activity stage', () => {
    expect(summarizeActivity({ ...base, optionCount: 0 })).toBe('当前无可刷活动关')
  })

  it('shows the selected stage and medicine count', () => {
    expect(summarizeActivity({ ...base, stageLabel: '2. 墟 · AT-7', medicine: 4 })).toBe(
      '2. 墟 · AT-7 · 理智药 4'
    )
  })
})

describe('depot summary', () => {
  it('explains that plan mode disables inventory maintenance', () => {
    expect(summarizeDepot(true, true, '[{"Stage":"CE-6"}]')).toBe('计划模式下不可用')
  })

  it('counts configured plans', () => {
    expect(summarizeDepot(false, true, '[{"a":1},{"b":2}]')).toBe('2 项计划')
  })

  it('treats malformed or empty plan JSON as no plans', () => {
    expect(summarizeDepot(false, true, 'not json')).toBe('尚未添加计划')
    expect(summarizeDepot(false, true, '')).toBe('尚未添加计划')
  })
})

describe('fight summary', () => {
  const base = { enabled: true, stage: '1-7', series: '0', medicine: 0, remain: '' }

  it('maps AUTO and 不切换 series codes', () => {
    expect(summarizeFight(base)).toBe('1-7 · 连战 AUTO · 理智药 0')
    expect(summarizeFight({ ...base, series: '-1' })).toBe('1-7 · 连战 不切换 · 理智药 0')
  })

  it('omits the remaining-sanity stage when unset', () => {
    expect(summarizeFight({ ...base, remain: '-' })).not.toContain('剩余理智')
    expect(summarizeFight({ ...base, remain: '1-7' })).toContain('剩余理智 1-7')
  })

  it('prefixes the plan name in plan mode', () => {
    expect(summarizeFight({ ...base, planLabel: '周计划' })).toBe(
      '周计划 · 1-7 · 连战 AUTO · 理智药 0'
    )
  })

  it('renders 当前/上次 for the sentinel stage value', () => {
    expect(summarizeFight({ ...base, stage: '-' })).toContain('当前/上次')
  })
})
