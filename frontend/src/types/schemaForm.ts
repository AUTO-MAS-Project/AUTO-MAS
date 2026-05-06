export interface SchemaActionDefinition {
  label?: string
  path?: string
  method?: string
  payload?: unknown
  refresh?: boolean
}

export interface SchemaOptionDefinition {
  label: string
  value: unknown
}

export type SchemaFieldSize = 'small' | 'half' | 'medium' | 'large'
export type SchemaPathKind = 'file' | 'folder'
export type SchemaFileFilter = {
  name: string
  extensions: string[]
}

export interface SchemaFieldDefinition {
  key?: string
  group?: string
  name?: string
  label?: string
  type: string
  title?: string
  format?: string
  default?: unknown
  required?: boolean
  readonly?: boolean
  sensitive?: boolean
  description?: string
  placeholder?: string
  help?: string
  rows?: number
  ui_type?: string
  item_type?: string
  enum?: unknown[]
  options?: Array<SchemaOptionDefinition | string | number | boolean>
  examples?: unknown[]
  constraints?: Record<string, unknown>
  action?: SchemaActionDefinition
  button?: SchemaActionDefinition
  configurable?: boolean
  min?: number
  max?: number
  step?: number
  path_kind?: SchemaPathKind
  filters?: SchemaFileFilter[]
  json_type?: string
  size?: SchemaFieldSize
}

export interface SchemaGroupDefinition {
  key: string
  label?: string
  fields: SchemaFieldDefinition[]
}

export interface GroupedSchemaDefinition {
  groups: SchemaGroupDefinition[]
}

export type SchemaDefinition = GroupedSchemaDefinition | Record<string, SchemaFieldDefinition>

export interface SchemaValidationErrorMap {
  [field: string]: string
}
