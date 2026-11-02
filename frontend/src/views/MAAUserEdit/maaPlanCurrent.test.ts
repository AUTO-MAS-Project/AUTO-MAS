import { describe, expect, it } from 'vitest'
import { getCurrentMaaPlan } from './maaPlanCurrent'

describe('MAA plan day selection', () => {
  const beforeReset = Date.parse('2026-11-01T19:59:00Z')
  const afterReset = Date.parse('2026-11-01T20:00:00Z')
  const group = (Stage: string) => ({
    MedicineNumb: 0,
    SeriesNumb: '0' as const,
    Stage,
    Stage_1: '-',
    Stage_2: '-',
    Stage_3: '-',
  })

  it('selects the weekly plan using the account game day', () => {
    const plan = {
      Info: { Mode: 'Weekly' as const },
      Sunday: group('AP-5'),
      Monday: group('1-7'),
    }
    expect(getCurrentMaaPlan(plan, 'Official', beforeReset)?.Stage).toBe('AP-5')
    expect(getCurrentMaaPlan(plan, 'Official', afterReset)?.Stage).toBe('1-7')
    expect(getCurrentMaaPlan(plan, 'YoStarEN', afterReset)?.Stage).toBe('AP-5')
  })

  it('uses the same ordinal-based rotation as the backend', () => {
    const plan = {
      Info: { Mode: 'Rotate' as const, RotateDays: 3 },
      Day1: group('1-7'),
      Day2: group('AP-5'),
      Day3: group('CA-5'),
    }
    // 2026-11-01 and 2026-11-02 have Python ordinals 739921 and 739922.
    expect(getCurrentMaaPlan(plan, 'Official', beforeReset)?.Stage).toBe('AP-5')
    expect(getCurrentMaaPlan(plan, 'Official', afterReset)?.Stage).toBe('CA-5')
  })

  it('does not use fixed values when the selected plan group is incomplete', () => {
    expect(getCurrentMaaPlan({ ALL: { Stage: '1-7' } }, 'Official', afterReset)).toBeNull()
  })
})
