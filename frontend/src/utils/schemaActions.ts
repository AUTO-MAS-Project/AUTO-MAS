import type {
  GroupedSchemaDefinition,
  SchemaActionDefinition,
  SchemaDefinition,
  SchemaFieldDefinition,
} from '@/types/schemaForm'

export interface HeaderSchemaAction {
  key: string
  field: SchemaFieldDefinition
  label: string
  icon?: string
}

const getFieldPath = (field: SchemaFieldDefinition) => field.key || field.name || ''

const getFieldAction = (field: SchemaFieldDefinition): SchemaActionDefinition | undefined =>
  field.action || field.button

const isHeaderSchemaAction = (field: SchemaFieldDefinition) => {
  const fieldPath = getFieldPath(field)
  return Boolean(
    getFieldAction(field)
    && (field.group === 'Action' || fieldPath.startsWith('Action.'))
  )
}

export const collectHeaderSchemaActions = (
  schema: SchemaDefinition | null | undefined,
): HeaderSchemaAction[] => {
  if (!schema) {
    return []
  }

  const fields = ('groups' in schema && Array.isArray((schema as GroupedSchemaDefinition).groups))
    ? (schema as GroupedSchemaDefinition).groups.flatMap(group => group.fields || [])
    : Object.entries(schema as Record<string, SchemaFieldDefinition>).map(([key, field]) => ({
      ...field,
      key: field.key || key,
    }))

  return fields
    .filter(isHeaderSchemaAction)
    .reverse()
    .map(field => {
      const key = getFieldPath(field)
      const action = getFieldAction(field)
      return {
        key,
        field,
        label: action?.label || field.label || field.title || key,
        icon: field.icon || action?.icon,
      }
    })
}
