export const INVENTORY_CATEGORIES = [
  { key: 'experience', label: 'core.edit.maaEndImsExperience' },
  { key: 'promotion', label: 'core.edit.maaEndImsPromotion' },
  { key: 'skill', label: 'core.edit.maaEndImsSkill' },
  { key: 'currency', label: 'core.edit.maaEndImsCurrency' },
  { key: 'other', label: 'core.edit.maaEndImsOther' },
] as const

type InventoryCategory = (typeof INVENTORY_CATEGORIES)[number]['key']

// 按上游公开输入的完整字段名分组；本地化标签中的材料简称不用于匹配。
const MATERIAL_CATEGORIES: Record<string, InventoryCategory> = {
  SupplyPlanLimit_COMBAT_RECORD_EXP: 'experience',
  SupplyPlanLimit_COGNITIVE_CARRIER_EXP: 'experience',
  SupplyPlanLimit_WEAPON_EXP: 'experience',
  SupplyPlanLimit_PROTODISK: 'promotion',
  SupplyPlanLimit_PROTOSET: 'promotion',
  SupplyPlanLimit_CAST_DIE: 'promotion',
  SupplyPlanLimit_HEAVY_CAST_DIE: 'promotion',
  SupplyPlanLimit_PROTOPRISM: 'skill',
  SupplyPlanLimit_PROTOHEDRON: 'skill',
  SupplyPlanLimit_METADIASTIMA_PHOTOEMISSION_TUBE: 'skill',
  SupplyPlanLimit_D96_STEEL_SAMPLE_4: 'skill',
  SupplyPlanLimit_TACHYON_SCREENING_LATTICE: 'skill',
  SupplyPlanLimit_QUADRANT_FITTING_FLUID: 'skill',
  SupplyPlanLimit_TRIPHASIC_NANOFLAKE: 'skill',
  SupplyPlanLimit_WARP_PLASMA_COATED_SLIDE: 'skill',
  SupplyPlanLimit_T_CREDS: 'currency',
}

export const inventoryCategoryFor = (key: string): InventoryCategory =>
  MATERIAL_CATEGORIES[key] ?? 'other'
