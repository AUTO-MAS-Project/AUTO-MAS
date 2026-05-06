<template>
  <div class="schema-form" :class="`schema-form-${layout}`">
    <div
      v-for="group in normalizedGroups"
      :key="group.key"
      class="schema-group"
    >
      <div v-if="showGroupTitle(group)" class="schema-group-title">{{ group.label || group.key }}</div>

      <a-form
        layout="vertical"
        :class="{ 'schema-form-grid': layout === 'plugin-grid' }"
      >
        <a-form-item
          v-for="field in group.fields"
          :key="getFieldPath(field)"
          :label="getFieldLabel(field)"
          :required="Boolean(field.required)"
          :help="getFieldHelp(field)"
          :validate-status="validationErrors[getFieldPath(field)] ? 'error' : undefined"
          :class="[
            'schema-item',
            `schema-item-${field.type}`,
            layout === 'plugin-grid' ? `schema-item-size-${getFieldLayoutSize(field)}` : '',
          ]"
        >
          <div class="schema-field-head">
            <a-space size="6">
              <a-tag class="type-tag" color="processing">{{ getTypeLabel(field) }}</a-tag>
              <a-tag v-if="field.required" color="error">必填</a-tag>
              <a-tag v-if="isPasswordField(field)" color="gold">敏感</a-tag>
              <a-tag v-if="field.readonly" color="default">只读</a-tag>
            </a-space>
          </div>

          <template v-if="isButtonField(field)">
            <a-button
              type="primary"
              :loading="actionLoadingId === getFieldPath(field)"
              :disabled="readonly"
              @click="emit('trigger-action', { field: getFieldPath(field), fieldSchema: field })"
            >
              {{ getActionLabel(field) }}
            </a-button>
          </template>

          <template v-else-if="isSelectField(field)">
            <a-select
              :value="getFieldValue(getFieldPath(field))"
              style="width: 100%"
              :options="getFieldOptions(field)"
              :disabled="readonly || field.readonly"
              @update:value="(val: unknown) => updateFieldValue(getFieldPath(field), val)"
            />
          </template>

          <template v-else-if="isMultiSelectField(field)">
            <a-select
              mode="multiple"
              :value="getEnumListValue(getFieldPath(field))"
              style="width: 100%"
              :options="getFieldOptions(field)"
              :disabled="readonly || field.readonly"
              @update:value="(val: unknown[]) => updateFieldValue(getFieldPath(field), val)"
            />
          </template>

          <template v-else-if="isBooleanField(field)">
            <a-switch
              :checked="getBooleanValue(getFieldPath(field))"
              checked-children="是"
              un-checked-children="否"
              :disabled="readonly || field.readonly"
              @update:checked="(val: boolean) => updateFieldValue(getFieldPath(field), val)"
            />
          </template>

          <template v-else-if="isStringField(field)">
            <a-input-password
              v-if="isPasswordField(field)"
              :value="String(getFieldValue(getFieldPath(field)) ?? '')"
              :placeholder="getFieldPlaceholder(field)"
              :maxlength="getStringMaxLength(field)"
              :disabled="readonly || field.readonly"
              @update:value="(val: string) => updateFieldValue(getFieldPath(field), val)"
            />
            <a-textarea
              v-else-if="isTextareaField(field)"
              :value="String(getFieldValue(getFieldPath(field)) ?? '')"
              :placeholder="getFieldPlaceholder(field)"
              :maxlength="getStringMaxLength(field)"
              :rows="getTextareaRows(field)"
              :disabled="readonly || field.readonly"
              @update:value="(val: string) => updateFieldValue(getFieldPath(field), val)"
            />
            <a-input
              v-else
              :value="String(getFieldValue(getFieldPath(field)) ?? '')"
              :placeholder="getFieldPlaceholder(field)"
              :maxlength="getStringMaxLength(field)"
              :disabled="readonly || field.readonly"
              @update:value="(val: string) => updateFieldValue(getFieldPath(field), val)"
            />
          </template>

          <template v-else-if="isNumberField(field)">
            <a-input-number
              :value="getNumberValue(getFieldPath(field))"
              style="width: 100%"
              :min="getNumberMin(field)"
              :max="getNumberMax(field)"
              :step="getNumberStep(field)"
              :disabled="readonly || field.readonly"
              @update:value="(val: number | null) => updateFieldValue(getFieldPath(field), val)"
            />
          </template>

          <template v-else-if="isListField(field)">
            <a-space direction="vertical" style="width: 100%">
              <a-button
                size="small"
                :disabled="readonly || field.readonly"
                @click="addListRow(getFieldPath(field), getListItemType(field))"
              >
                新增一行
              </a-button>
              <a-table
                :columns="listColumns"
                :data-source="getListRows(getFieldPath(field))"
                :pagination="false"
                size="small"
                row-key="__rowKey"
              >
                <template #bodyCell="{ column, record, index }">
                  <template v-if="column.key === 'value'">
                    <a-switch
                      v-if="getListItemType(field) === 'boolean'"
                      :checked="Boolean(record.value)"
                      :disabled="readonly || field.readonly"
                      @update:checked="
                        (val: boolean) =>
                          updateListRowValue(getFieldPath(field), index, val, getListItemType(field))
                      "
                    />
                    <a-input-number
                      v-else-if="getListItemType(field) === 'number'"
                      style="width: 100%"
                      :value="
                        typeof record.value === 'number' ? record.value : Number(record.value || 0)
                      "
                      :disabled="readonly || field.readonly"
                      @update:value="
                        (val: number | null) =>
                          updateListRowValue(
                            getFieldPath(field),
                            index,
                            val ?? 0,
                            getListItemType(field)
                          )
                      "
                    />
                    <a-input
                      v-else
                      :value="String(record.value ?? '')"
                      :disabled="readonly || field.readonly"
                      @update:value="
                        (val: string) =>
                          updateListRowValue(
                            getFieldPath(field),
                            index,
                            val,
                            getListItemType(field)
                          )
                      "
                    />
                  </template>
                  <template v-else-if="column.key === 'action'">
                    <a-button
                      danger
                      size="small"
                      :disabled="readonly || field.readonly"
                      @click="removeListRow(getFieldPath(field), index)"
                    >
                      删除
                    </a-button>
                  </template>
                </template>
              </a-table>
            </a-space>
          </template>

          <template v-else-if="field.type === 'key_value'">
            <a-space direction="vertical" style="width: 100%">
              <a-button
                size="small"
                :disabled="readonly || field.readonly"
                @click="addKeyValueRow(getFieldPath(field))"
              >
                新增一行
              </a-button>
              <a-table
                :columns="keyValueColumns"
                :data-source="getKeyValueRows(getFieldPath(field))"
                :pagination="false"
                size="small"
                row-key="__rowKey"
              >
                <template #bodyCell="{ column, record }">
                  <template v-if="column.key === 'key'">
                    <a-input
                      :value="record.key"
                      :disabled="readonly || field.readonly"
                      @blur="
                        (e: FocusEvent) =>
                          updateKeyValueRowKey(
                            getFieldPath(field),
                            record.key,
                            String((e.target as HTMLInputElement).value || '')
                          )
                      "
                    />
                  </template>
                  <template v-else-if="column.key === 'value'">
                    <a-input
                      :value="record.value"
                      :disabled="readonly || field.readonly"
                      @update:value="
                        (val: string) => updateKeyValueRowValue(getFieldPath(field), record.key, val)
                      "
                    />
                  </template>
                  <template v-else-if="column.key === 'action'">
                    <a-button
                      danger
                      size="small"
                      :disabled="readonly || field.readonly"
                      @click="removeKeyValueRow(getFieldPath(field), record.key)"
                    >
                      删除
                    </a-button>
                  </template>
                </template>
              </a-table>
            </a-space>
          </template>

          <template v-else-if="field.type === 'table'">
            <a-space direction="vertical" style="width: 100%">
              <a-space>
                <a-button
                  size="small"
                  :disabled="readonly || field.readonly"
                  @click="addTableRow(getFieldPath(field))"
                >
                  新增行
                </a-button>
                <a-button
                  size="small"
                  :disabled="readonly || field.readonly"
                  @click="addTableColumn(getFieldPath(field))"
                >
                  新增列
                </a-button>
              </a-space>
              <a-table
                :columns="getTableColumns(getFieldPath(field))"
                :data-source="getTableRows(getFieldPath(field))"
                :pagination="false"
                size="small"
                row-key="__rowKey"
              >
                <template #bodyCell="{ column, record, index }">
                  <template v-if="column.key === 'action'">
                    <a-button
                      danger
                      size="small"
                      :disabled="readonly || field.readonly"
                      @click="removeTableRow(getFieldPath(field), index)"
                    >
                      删除
                    </a-button>
                  </template>
                  <template v-else>
                    <a-input
                      :value="String(record[column.key] ?? '')"
                      :disabled="readonly || field.readonly"
                      @update:value="
                        (val: string) =>
                          updateTableCellValue(getFieldPath(field), index, String(column.key), val)
                      "
                    />
                  </template>
                </template>
              </a-table>
            </a-space>
          </template>

          <template v-else-if="isJsonField(field)">
            <a-textarea
              :value="getJsonText(getFieldPath(field))"
              :rows="getTextareaRows(field)"
              :disabled="readonly || field.readonly"
              @blur="handleJsonBlur(getFieldPath(field), $event)"
            />
          </template>

          <template v-else>
            <a-input
              :value="String(getFieldValue(getFieldPath(field)) ?? '')"
              :placeholder="getFieldPlaceholder(field)"
              :disabled="readonly || field.readonly"
              @update:value="(val: string) => updateFieldValue(getFieldPath(field), val)"
            />
          </template>
        </a-form-item>
      </a-form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type {
  GroupedSchemaDefinition,
  SchemaDefinition,
  SchemaFieldDefinition,
  SchemaGroupDefinition,
  SchemaValidationErrorMap,
} from '@/types/schemaForm'

interface ListRow {
  __rowKey: string
  value: unknown
}

interface KeyValueRow {
  __rowKey: string
  key: string
  value: string
}

interface TableRow {
  __rowKey: string
  [key: string]: unknown
}

interface TableColumn {
  title: string
  dataIndex: string
  key: string
}

const props = withDefaults(
  defineProps<{
    modelValue: Record<string, any>
    schema: SchemaDefinition
    readonly?: boolean
    hideFields?: string[]
    actionLoadingId?: string
    layout?: 'single' | 'plugin-grid'
  }>(),
  {
    readonly: false,
    hideFields: () => [],
    actionLoadingId: '',
    layout: 'single',
  }
)

const emit = defineEmits<{
  (e: 'update:modelValue', value: Record<string, any>): void
  (e: 'trigger-action', payload: { field: string; fieldSchema: SchemaFieldDefinition }): void
  (e: 'validation-change', errors: SchemaValidationErrorMap): void
}>()

const validationErrors = ref<SchemaValidationErrorMap>({})

const listColumns = [
  { title: '值', dataIndex: 'value', key: 'value' },
  { title: '操作', dataIndex: 'action', key: 'action' },
]

const keyValueColumns = [
  { title: '键', dataIndex: 'key', key: 'key' },
  { title: '值', dataIndex: 'value', key: 'value' },
  { title: '操作', dataIndex: 'action', key: 'action' },
]

const normalizedGroups = computed<SchemaGroupDefinition[]>(() => {
  if (!props.schema) {
    return []
  }

  if ('groups' in props.schema && Array.isArray((props.schema as GroupedSchemaDefinition).groups)) {
    return (props.schema as GroupedSchemaDefinition).groups.map(group => ({
      ...group,
      fields: (group.fields || []).filter(field => !props.hideFields.includes(getFieldPath(field))),
    }))
  }

  const fields = Object.entries(props.schema as Record<string, SchemaFieldDefinition>)
    .filter(([field]) => !props.hideFields.includes(field))
    .map(([field, fieldSchema]) => ({
      ...fieldSchema,
      key: field,
    }))

  return [
    {
      key: 'default',
      label: '',
      fields,
    },
  ]
})

const cloneModel = () => JSON.parse(JSON.stringify(props.modelValue || {}))

const getFieldPath = (field: SchemaFieldDefinition) => field.key || field.name || ''

const showGroupTitle = (group: SchemaGroupDefinition) =>
  normalizedGroups.value.length > 1 && Boolean(group.label || group.key)

const getFieldLabel = (field: SchemaFieldDefinition) =>
  field.label || field.title || field.description || getFieldPath(field)

const getFieldPlaceholder = (field: SchemaFieldDefinition) =>
  typeof field.placeholder === 'string' ? field.placeholder : undefined

const getFieldOptions = (field: SchemaFieldDefinition) => {
  if (Array.isArray(field.options) && field.options.length > 0) {
    return field.options
  }
  return (field.enum || []).map(item => ({
    label: String(item),
    value: item,
  }))
}

const getActionLabel = (field: SchemaFieldDefinition) => {
  const action = field.action || field.button
  return action?.label || getFieldLabel(field)
}

const schemaFieldSizes = ['small', 'half', 'medium', 'large'] as const

const isSchemaFieldSize = (value: unknown): value is NonNullable<SchemaFieldDefinition['size']> =>
  typeof value === 'string' && schemaFieldSizes.includes(value as NonNullable<SchemaFieldDefinition['size']>)

const getFieldLayoutSize = (field: SchemaFieldDefinition): NonNullable<SchemaFieldDefinition['size']> => {
  if (isSchemaFieldSize(field.size)) {
    return field.size
  }

  if (
    field.type === 'table' ||
    field.type === 'key_value' ||
    isJsonField(field) ||
    isDictionaryField(field) ||
    isListField(field) ||
    isTextareaField(field) ||
    getTextareaRows(field) > 4
  ) {
    return 'large'
  }

  return 'small'
}

const getValueByPath = (source: Record<string, any>, path: string) => {
  if (!path) {
    return undefined
  }
  return path.split('.').reduce<any>((current, key) => {
    if (current == null || typeof current !== 'object') {
      return undefined
    }
    return current[key]
  }, source)
}

const setValueByPath = (source: Record<string, any>, path: string, value: unknown) => {
  const keys = path.split('.')
  let current: Record<string, any> = source

  keys.forEach((key, index) => {
    if (index === keys.length - 1) {
      current[key] = value
      return
    }

    if (!current[key] || typeof current[key] !== 'object' || Array.isArray(current[key])) {
      current[key] = {}
    }
    current = current[key]
  })
}

const getFieldValue = (field: string) => getValueByPath(props.modelValue || {}, field)

const updateFieldValue = (field: string, value: unknown) => {
  const nextValue = cloneModel()
  setValueByPath(nextValue, field, value)
  emit('update:modelValue', nextValue)
}

const toFiniteNumber = (value: unknown) => {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value
  }
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : undefined
  }
  return undefined
}

const getSchemaConstraint = (field: SchemaFieldDefinition, key: string) => field.constraints?.[key]

const isButtonField = (field: SchemaFieldDefinition) => field.type === 'button' || field.type === 'action'
const isSelectField = (field: SchemaFieldDefinition) => field.type === 'select'
const isMultiSelectField = (field: SchemaFieldDefinition) => field.type === 'multiselect'
const isBooleanField = (field: SchemaFieldDefinition) => field.type === 'boolean' || field.type === 'bool'
const isStringField = (field: SchemaFieldDefinition) => ['string', 'str', 'folder', 'file', 'uuid', 'datetime', 'related-id', 'readonly'].includes(field.type)
const isNumberField = (field: SchemaFieldDefinition) =>
  ['number', 'integer', 'int', 'float'].includes(field.type)
const isListField = (field: SchemaFieldDefinition) => field.type === 'list' || field.type.startsWith('list[')
const isJsonField = (field: SchemaFieldDefinition) => field.type === 'json'
const isDictionaryField = (field: SchemaFieldDefinition) =>
  field.type === 'dict' || field.type.startsWith('dict[')
const isPasswordField = (field: SchemaFieldDefinition) =>
  (isStringField(field) && field.format === 'password') || field.type === 'password'
const isTextareaField = (field: SchemaFieldDefinition) =>
  isJsonField(field) || (isStringField(field) && field.format === 'textarea')

const getListItemType = (field: SchemaFieldDefinition) => {
  if (field.item_type) {
    return field.item_type
  }
  const matched = /^list\[(.+)]$/.exec(field.type)
  return matched?.[1] || 'string'
}

const getBooleanValue = (field: string) => Boolean(getFieldValue(field))

const getNumberValue = (field: string) => {
  const value = getFieldValue(field)
  if (typeof value === 'number') {
    return value
  }
  if (typeof value === 'string' && value.trim() !== '') {
    const numberValue = Number(value)
    return Number.isFinite(numberValue) ? numberValue : undefined
  }
  return undefined
}

const getEnumListValue = (field: string) => {
  const value = getFieldValue(field)
  return Array.isArray(value) ? value : []
}

const getStringMaxLength = (field: SchemaFieldDefinition) =>
  toFiniteNumber(getSchemaConstraint(field, 'max_length'))

const getTextareaRows = (field: SchemaFieldDefinition) => {
  const rows = toFiniteNumber(field.rows)
  return rows && rows > 0 ? rows : 4
}

const getNumberMin = (field: SchemaFieldDefinition) => {
  if (typeof field.min === 'number') {
    return field.min
  }
  const ge = toFiniteNumber(getSchemaConstraint(field, 'ge'))
  if (ge !== undefined) {
    return ge
  }
  return toFiniteNumber(getSchemaConstraint(field, 'gt'))
}

const getNumberMax = (field: SchemaFieldDefinition) => {
  if (typeof field.max === 'number') {
    return field.max
  }
  const le = toFiniteNumber(getSchemaConstraint(field, 'le'))
  if (le !== undefined) {
    return le
  }
  return toFiniteNumber(getSchemaConstraint(field, 'lt'))
}

const getNumberStep = (field: SchemaFieldDefinition) => {
  if (typeof field.step === 'number') {
    return field.step
  }
  const multipleOf = toFiniteNumber(getSchemaConstraint(field, 'multiple_of'))
  if (multipleOf && multipleOf > 0) {
    return multipleOf
  }
  return field.type === 'integer' || field.type === 'int' ? 1 : undefined
}

const getJsonText = (field: string) => JSON.stringify(getFieldValue(field) ?? {}, null, 2)

const handleJsonBlur = (field: string, event: FocusEvent) => {
  const value = String((event.target as HTMLTextAreaElement).value || '')
  try {
    const parsed = value.trim() ? JSON.parse(value) : {}
    updateFieldValue(field, parsed)
  } catch {
    validationErrors.value = {
      ...validationErrors.value,
      [field]: 'JSON 格式无效',
    }
    emit('validation-change', validationErrors.value)
  }
}

const normalizeListValueByType = (value: unknown, itemType?: string) => {
  if (itemType === 'number') {
    if (typeof value === 'number') {
      return value
    }
    const numberValue = Number(value)
    return Number.isFinite(numberValue) ? numberValue : 0
  }
  if (itemType === 'boolean') {
    return Boolean(value)
  }
  return String(value ?? '')
}

const getListRows = (field: string): ListRow[] => {
  const value = getFieldValue(field)
  if (!Array.isArray(value)) {
    return []
  }
  return value.map((item, index) => ({
    __rowKey: `${field}-${index}`,
    value: item,
  }))
}

const addListRow = (field: string, itemType?: string) => {
  const value = getFieldValue(field)
  const list = Array.isArray(value) ? [...value] : []
  if (itemType === 'number') {
    list.push(0)
  } else if (itemType === 'boolean') {
    list.push(false)
  } else {
    list.push('')
  }
  updateFieldValue(field, list)
}

const removeListRow = (field: string, index: number) => {
  const value = getFieldValue(field)
  const list = Array.isArray(value) ? [...value] : []
  list.splice(index, 1)
  updateFieldValue(field, list)
}

const updateListRowValue = (field: string, index: number, value: unknown, itemType?: string) => {
  const raw = getFieldValue(field)
  const list = Array.isArray(raw) ? [...raw] : []
  list[index] = normalizeListValueByType(value, itemType)
  updateFieldValue(field, list)
}

const getKeyValueRows = (field: string): KeyValueRow[] => {
  const value = getFieldValue(field)
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return []
  }
  return Object.entries(value as Record<string, unknown>).map(([key, item], index) => ({
    __rowKey: `${field}-${index}`,
    key,
    value: String(item ?? ''),
  }))
}

const addKeyValueRow = (field: string) => {
  const value = getFieldValue(field)
  const obj =
    value && typeof value === 'object' && !Array.isArray(value)
      ? { ...(value as Record<string, unknown>) }
      : {}

  let idx = 1
  let key = `key_${idx}`
  while (Object.prototype.hasOwnProperty.call(obj, key)) {
    idx += 1
    key = `key_${idx}`
  }

  obj[key] = ''
  updateFieldValue(field, obj)
}

const removeKeyValueRow = (field: string, key: string) => {
  const value = getFieldValue(field)
  const obj =
    value && typeof value === 'object' && !Array.isArray(value)
      ? { ...(value as Record<string, unknown>) }
      : {}
  delete obj[key]
  updateFieldValue(field, obj)
}

const updateKeyValueRowKey = (field: string, oldKey: string, newKey: string) => {
  const value = getFieldValue(field)
  const obj =
    value && typeof value === 'object' && !Array.isArray(value)
      ? { ...(value as Record<string, unknown>) }
      : {}
  const finalKey = newKey.trim()
  if (!finalKey || finalKey === oldKey) {
    return
  }
  obj[finalKey] = obj[oldKey]
  delete obj[oldKey]
  updateFieldValue(field, obj)
}

const updateKeyValueRowValue = (field: string, key: string, value: string) => {
  const current = getFieldValue(field)
  const obj =
    current && typeof current === 'object' && !Array.isArray(current)
      ? { ...(current as Record<string, unknown>) }
      : {}
  obj[key] = value
  updateFieldValue(field, obj)
}

const getTableRows = (field: string): TableRow[] => {
  const value = getFieldValue(field)
  if (!Array.isArray(value)) {
    return []
  }
  return value.map((item, index) => ({
    __rowKey: `${field}-${index}`,
    ...(typeof item === 'object' && item ? item : {}),
  }))
}

const getTableColumns = (field: string): TableColumn[] => {
  const rows = getTableRows(field)
  const keys = new Set<string>()

  rows.forEach(row => {
    Object.keys(row).forEach(key => {
      if (key !== '__rowKey') {
        keys.add(key)
      }
    })
  })

  if (keys.size === 0) {
    keys.add('col_1')
  }

  const columns: TableColumn[] = Array.from(keys).map(key => ({
    title: key,
    dataIndex: key,
    key,
  }))

  columns.push({
    title: '操作',
    dataIndex: 'action',
    key: 'action',
  })

  return columns
}

const addTableRow = (field: string) => {
  const rows = getTableRows(field).map(({ __rowKey, ...row }) => row)
  const columns = getTableColumns(field)
  const row: Record<string, unknown> = {}
  columns.forEach(col => {
    if (col.key !== 'action') {
      row[col.key] = ''
    }
  })
  rows.push(row)
  updateFieldValue(field, rows)
}

const removeTableRow = (field: string, index: number) => {
  const rows = getTableRows(field).map(({ __rowKey, ...row }) => row)
  rows.splice(index, 1)
  updateFieldValue(field, rows)
}

const addTableColumn = (field: string) => {
  const rows = getTableRows(field).map(({ __rowKey, ...row }) => ({ ...row }))
  const columns = getTableColumns(field)
  let idx = 1
  let nextKey = `col_${idx}`
  const columnKeys = new Set(columns.filter(col => col.key !== 'action').map(col => col.key))
  while (columnKeys.has(nextKey)) {
    idx += 1
    nextKey = `col_${idx}`
  }
  if (rows.length === 0) {
    rows.push({ [nextKey]: '' })
  } else {
    rows.forEach(row => {
      row[nextKey] = ''
    })
  }
  updateFieldValue(field, rows)
}

const updateTableCellValue = (field: string, index: number, key: string, value: string) => {
  const rows = getTableRows(field).map(({ __rowKey, ...row }) => ({ ...row }))
  if (!rows[index]) {
    rows[index] = {}
  }
  rows[index][key] = value
  updateFieldValue(field, rows)
}

const isValidHttpUrl = (value: string) => {
  try {
    const parsed = new URL(value)
    if (!['http:', 'https:'].includes(parsed.protocol)) {
      return '仅支持 http 或 https 地址'
    }
    return ''
  } catch {
    return 'URL 格式无效'
  }
}

const validateFieldValue = (fieldPath: string, field: SchemaFieldDefinition, value: unknown) => {
  if (isButtonField(field)) {
    return ''
  }

  if (value === undefined || value === null || value === '') {
    return field.required ? '该字段为必填项' : ''
  }

  if (isStringField(field)) {
    const text = String(value)
    const minLength = toFiniteNumber(getSchemaConstraint(field, 'min_length'))
    const maxLength = toFiniteNumber(getSchemaConstraint(field, 'max_length'))
    const pattern = getSchemaConstraint(field, 'pattern')

    if (minLength !== undefined && text.length < minLength) {
      return `至少需要 ${minLength} 个字符`
    }
    if (maxLength !== undefined && text.length > maxLength) {
      return `最多允许 ${maxLength} 个字符`
    }
    if (typeof pattern === 'string' && pattern) {
      try {
        if (!new RegExp(pattern).test(text)) {
          return '内容不符合格式要求'
        }
      } catch {
        return ''
      }
    }
    if (field.format === 'url') {
      return isValidHttpUrl(text)
    }
    return ''
  }

  if (isNumberField(field)) {
    const numberValue = toFiniteNumber(value)
    if (numberValue === undefined) {
      return '请输入有效数字'
    }
    const min = getNumberMin(field)
    const max = getNumberMax(field)
    if (min !== undefined && numberValue < min) {
      return `数值不能小于 ${min}`
    }
    if (max !== undefined && numberValue > max) {
      return `数值不能大于 ${max}`
    }
    return ''
  }

  if (isMultiSelectField(field) || isListField(field)) {
    if (!Array.isArray(value)) {
      return '该字段需要列表值'
    }
    return ''
  }

  if (isJsonField(field)) {
    if (typeof value !== 'object') {
      return '该字段需要 JSON 对象'
    }
    return ''
  }

  if (field.type === 'key_value') {
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
      return '该字段需要键值对象'
    }
    return ''
  }

  if (field.type === 'table') {
    if (!Array.isArray(value)) {
      return '该字段需要表格数组'
    }
    return ''
  }

  return ''
}

const collectValidationErrors = () => {
  const errors: SchemaValidationErrorMap = {}
  normalizedGroups.value.forEach(group => {
    group.fields.forEach(field => {
      const fieldPath = getFieldPath(field)
      const error = validateFieldValue(fieldPath, field, getFieldValue(fieldPath))
      if (error) {
        errors[fieldPath] = error
      }
    })
  })
  return errors
}

const validate = () => {
  const errors = collectValidationErrors()
  validationErrors.value = errors
  emit('validation-change', errors)
  return {
    valid: Object.keys(errors).length === 0,
    errors,
  }
}

const getFieldHelp = (field: SchemaFieldDefinition) => {
  const fieldPath = getFieldPath(field)
  if (validationErrors.value[fieldPath]) {
    return validationErrors.value[fieldPath]
  }
  if (typeof field.help === 'string' && field.help.trim()) {
    return field.help
  }
  if (Array.isArray(field.examples) && field.examples.length > 0) {
    return `示例：${field.examples.map(item => String(item)).join('、')}`
  }
  return undefined
}

const getTypeLabel = (field: SchemaFieldDefinition) => {
  if (isButtonField(field)) {
    return '动作'
  }
  if (isSelectField(field)) {
    return '枚举'
  }
  if (isMultiSelectField(field)) {
    return '多选'
  }
  if (isPasswordField(field)) {
    return '密码'
  }
  if (isStringField(field)) {
    return '文本'
  }
  if (isNumberField(field)) {
    return '数字'
  }
  if (isBooleanField(field)) {
    return '布尔'
  }
  if (isListField(field)) {
    return '列表'
  }
  if (field.type === 'key_value') {
    return '键值表'
  }
  if (field.type === 'table') {
    return '表格'
  }
  if (isJsonField(field)) {
    return 'JSON'
  }
  return field.type
}

watch(
  () => [props.modelValue, props.schema],
  () => {
    validationErrors.value = collectValidationErrors()
    emit('validation-change', validationErrors.value)
  },
  { deep: true, immediate: true }
)

defineExpose({
  validate,
})
</script>

<style scoped>
.schema-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.schema-group {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.schema-group-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.schema-form-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 12px;
}

.schema-form-grid .schema-item {
  min-width: 0;
}

.schema-form-grid .schema-item-size-small {
  grid-column: span 2;
}

.schema-form-grid .schema-item-size-half {
  grid-column: span 3;
}

.schema-form-grid .schema-item-size-medium {
  grid-column: span 4;
}

.schema-form-grid .schema-item-size-large {
  grid-column: 1 / -1;
}

.schema-field-head {
  margin-bottom: 8px;
}

.type-tag {
  font-weight: 500;
}

.schema-item {
  padding: 14px 16px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-bg-container);
  margin-bottom: 0;
}

.schema-item :deep(.ant-form-item-label) {
  padding-bottom: 4px;
}

.schema-item :deep(.ant-form-item-label > label) {
  font-weight: 600;
  color: var(--ant-color-text);
}

@media (max-width: 960px) {
  .schema-form-grid {
    grid-template-columns: 1fr;
  }

  .schema-form-grid .schema-item {
    grid-column: 1 / -1 !important;
  }
}
</style>
