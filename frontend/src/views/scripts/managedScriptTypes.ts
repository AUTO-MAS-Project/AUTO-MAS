import type { ComponentHint } from '@/api'

export type ConfigData = Record<string, unknown>
export type ConfigHints = { hints?: Record<string, ComponentHint[]> }
export type ManagedUser = ConfigData & {
  uid: string
  type: string
  info: ConfigData
  ui: ConfigHints
}
export type ManagedScript = ConfigData & {
  uid: string
  type: string
  info: ConfigData
  ui: ConfigHints
  users: ManagedUser[]
}
