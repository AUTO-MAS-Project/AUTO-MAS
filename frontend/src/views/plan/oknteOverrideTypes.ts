import type { OkNtePlanField } from '@/api'
export type OverrideField = OkNtePlanField
export interface OverrideRow {
  id: string
  field: OverrideField
  path: string[]
  routineId?: string
}
export type OverrideConfigs = Record<string, Record<string, unknown>>
