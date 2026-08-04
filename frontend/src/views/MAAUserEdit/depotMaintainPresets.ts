export type DepotMaintainPlan = {
  Stage: string
  DropId: string
  DropCount: number
}

export const DEPOT_MAINTAIN_PRESETS = [
  { key: 'chip', label: '芯片' },
  { key: 'chip-pack', label: '芯片组' },
  { key: 'lmd', label: '龙门币' },
  { key: 'purchase-certificate', label: '采购凭证' },
  { key: 'skill-summary', label: '技巧概要' },
] as const

export type DepotMaintainPresetKey = 'all' | (typeof DEPOT_MAINTAIN_PRESETS)[number]['key']

const PRESET_PLANS: Record<Exclude<DepotMaintainPresetKey, 'all'>, DepotMaintainPlan[]> = {
  chip: [
    { Stage: 'PR-A-1', DropId: '3261', DropCount: 20 },
    { Stage: 'PR-A-1', DropId: '3231', DropCount: 20 },
    { Stage: 'PR-B-1', DropId: '3251', DropCount: 20 },
    { Stage: 'PR-B-1', DropId: '3241', DropCount: 20 },
    { Stage: 'PR-C-1', DropId: '3211', DropCount: 20 },
    { Stage: 'PR-C-1', DropId: '3271', DropCount: 20 },
    { Stage: 'PR-D-1', DropId: '3221', DropCount: 20 },
    { Stage: 'PR-D-1', DropId: '3281', DropCount: 20 },
  ],
  'chip-pack': [
    { Stage: 'PR-A-2', DropId: '3262', DropCount: 20 },
    { Stage: 'PR-A-2', DropId: '3232', DropCount: 20 },
    { Stage: 'PR-B-2', DropId: '3252', DropCount: 20 },
    { Stage: 'PR-B-2', DropId: '3242', DropCount: 20 },
    { Stage: 'PR-C-2', DropId: '3212', DropCount: 20 },
    { Stage: 'PR-C-2', DropId: '3272', DropCount: 20 },
    { Stage: 'PR-D-2', DropId: '3222', DropCount: 20 },
    { Stage: 'PR-D-2', DropId: '3282', DropCount: 20 },
  ],
  lmd: [{ Stage: 'CE-6', DropId: '4001', DropCount: 2_000_000 }],
  'purchase-certificate': [{ Stage: 'AP-5', DropId: '4006', DropCount: 5_000 }],
  'skill-summary': [{ Stage: 'CA-5', DropId: '3303', DropCount: 200 }],
}

export const importDepotMaintainPreset = (
  plans: DepotMaintainPlan[],
  preset: DepotMaintainPresetKey
) => [
  ...plans,
  ...(preset === 'all'
    ? DEPOT_MAINTAIN_PRESETS.flatMap(({ key }) => PRESET_PLANS[key])
    : PRESET_PLANS[preset]
  ).map(plan => ({ ...plan })),
]
