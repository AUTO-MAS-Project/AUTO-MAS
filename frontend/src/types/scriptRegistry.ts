import type { SchemaDefinition } from './schemaForm'

export interface ScriptTypeDescriptor {
  type_key: string
  display_name: string
  icon?: string | null
  docs_url?: string | null
  editor_kind: string
  supported_modes: string[]
  script_schema: SchemaDefinition
  user_schema: SchemaDefinition
  legacy_config_class_name?: string | null
  legacy_user_config_class_name?: string | null
  is_builtin: boolean
}

export interface ScriptTypeGetOut {
  code: number
  status: string
  message: string
  data: ScriptTypeDescriptor[]
}

export interface ScriptRecord {
  id: string
  type: string
  name: string
  config: Record<string, any>
  schema: SchemaDefinition
  editor_kind: string
  supported_modes: string[]
  icon?: string | null
  docs_url?: string | null
  user_count: number
}

export interface ScriptRecordGetOut {
  code: number
  status: string
  message: string
  records: ScriptRecord[]
}

export interface ScriptRecordCreateOut {
  code: number
  status: string
  message: string
  record: ScriptRecord
}

export interface ScriptUserRecord {
  id: string
  script_id: string
  type: string
  name: string
  config: Record<string, any>
  schema: SchemaDefinition
}

export interface ScriptUserRecordGetOut {
  code: number
  status: string
  message: string
  records: ScriptUserRecord[]
}

export interface ScriptUserRecordCreateOut {
  code: number
  status: string
  message: string
  record: ScriptUserRecord
}
