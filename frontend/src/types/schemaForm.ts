export interface SchemaActionSessionDefinition {
  response_task_id_key?: string
  stop_path?: string
  stop_method?: string
  stop_payload?: unknown
  overlay_title?: string
  overlay_description?: string
  stop_label?: string
  start_message?: string
  success_message?: string
  stop_message?: string
  timeout_ms?: number
  timeout_auto_stop?: boolean
  timeout_message?: string
  completion_type?: string
  completion_field?: string
  error_field?: string
}

export interface SchemaActionDefinition {
  label?: string
  path?: string
  method?: string
  payload?: unknown
  refresh?: boolean
  session?: SchemaActionSessionDefinition | null
}

export interface SchemaOptionDefinition {
  label: string
  value: unknown
}

export type SchemaFieldSize =
  | '1/1'
  | '1/2'
  | '1/3'
  | '2/3'
  | '1/4'
  | '3/4'
  | 'small'
  | 'half'
  | 'medium'
  | 'large'
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
  hidden?: boolean
  rows?: number
  ui_type?: string
  item_type?: string
  enum?: unknown[]
  options?: Array<SchemaOptionDefinition | string | number | boolean>
  allow_custom?: boolean
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
