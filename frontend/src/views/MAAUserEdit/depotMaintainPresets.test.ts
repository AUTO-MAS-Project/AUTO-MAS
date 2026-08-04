import { describe, expect, it } from 'vitest'
import { importDepotMaintainPreset } from './depotMaintainPresets'

describe('inventory maintenance presets', () => {
  it('appends one MAA preset without replacing existing plans', () => {
    const existing = [{ Stage: '1-7', DropId: '30012', DropCount: 100 }]
    const plans = importDepotMaintainPreset(existing, 'lmd')

    expect(existing).toHaveLength(1)
    expect(plans).toEqual([...existing, { Stage: 'CE-6', DropId: '4001', DropCount: 2_000_000 }])
  })

  it('imports all 19 plans in menu order', () => {
    const plans = importDepotMaintainPreset([], 'all')

    expect(plans).toHaveLength(19)
    expect(plans.slice(0, 2)).toEqual([
      { Stage: 'PR-A-1', DropId: '3261', DropCount: 20 },
      { Stage: 'PR-A-1', DropId: '3231', DropCount: 20 },
    ])
    expect(plans.slice(-3)).toEqual([
      { Stage: 'CE-6', DropId: '4001', DropCount: 2_000_000 },
      { Stage: 'AP-5', DropId: '4006', DropCount: 5_000 },
      { Stage: 'CA-5', DropId: '3303', DropCount: 200 },
    ])
  })
})
