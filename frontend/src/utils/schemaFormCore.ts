/**
 * SchemaForm 纯逻辑核心。
 *
 * 本模块不依赖 Vue，所有函数都是纯函数或仅依赖入参，便于 deterministic 单元测试。
 * Vue composable（`useSchemaFormModel`）在本模块之上提供响应式包装与 emit 集成。
 *
 * 设计原则：
 * - 不引入新依赖；保留 SchemaForm.vue 原有的全部 schema 类型与行为。
 * - 不为视觉效果添加营销式装饰；仅承担 schema 解析、字段渲染辅助、校验和布局映射。
 * - 敏感字段处理（不回显明文 / 保持 / 替换 / 清空）在 `useSensitiveFieldStrategy` 中实现。
 */

import type {
  GroupedSchemaDefinition,
  SchemaDefinition,
  SchemaFieldDefinition,
  SchemaGroupDefinition,
  SchemaValidationErrorMap,
} from '@/types/schemaForm'

/** 字段路径：优先 `key`，回退 `name`，最后空串。 */
export const getFieldPath = (field: SchemaFieldDefinition): string => field.key || field.name || ''

/** 字段标签：优先 `label`，回退 `title`、`description`，最后字段路径。 */
export const getFieldLabel = (field: SchemaFieldDefinition): string =>
  field.label || field.title || field.description || getFieldPath(field)

/** 字段占位文本：仅当显式声明为字符串时返回，否则 undefined。 */
export const getFieldPlaceholder = (field: SchemaFieldDefinition): string | undefined =>
  typeof field.placeholder === 'string' ? field.placeholder : undefined

/** 在对象上按点路径取值；路径为空或中间节点非对象时返回 undefined。 */
export const getValueByPath = (
  source: Record<string, any> | null | undefined,
  path: string
): unknown => {
  if (!path) {
    return undefined
  }
  return path.split('.').reduce<any>((current, key) => {
    if (current == null || typeof current !== 'object') {
      return undefined
    }
    return current[key]
  }, source ?? {})
}

/** 在对象上按点路径设值；中间节点缺失或类型不匹配时自动创建空对象。 */
export const setValueByPath = (source: Record<string, any>, path: string, value: unknown): void => {
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

/** 深拷贝 modelValue；输入为空时返回空对象。 */
export const cloneModel = (
  modelValue: Record<string, any> | null | undefined
): Record<string, any> => JSON.parse(JSON.stringify(modelValue || {}))

/** 将字段的 `options` / `enum` 归一为 `{ label, value }` 数组。 */
export const getFieldOptions = (
  field: SchemaFieldDefinition
): Array<{ label: string; value: unknown }> => {
  if (Array.isArray(field.options) && field.options.length > 0) {
    return field.options.map(item => {
      if (item && typeof item === 'object' && 'value' in item) {
        const option = item as { label?: unknown; value: unknown }
        return {
          label: String(option.label ?? option.value),
          value: option.value,
        }
      }
      return {
        label: String(item),
        value: item,
      }
    })
  }
  return (field.enum || []).map(item => ({
    label: String(item),
    value: item,
  }))
}

export const getOptionLabelByValue = (
  field: SchemaFieldDefinition,
  value: unknown
): string | undefined => {
  const matched = getFieldOptions(field).find(option => option.value === value)
  return matched ? String(matched.label) : undefined
}

export const getOptionValueByLabel = (field: SchemaFieldDefinition, label: string): unknown => {
  const matched = getFieldOptions(field).find(option => String(option.label) === label)
  return matched?.value
}

export const hasSelectableOptions = (field: SchemaFieldDefinition): boolean =>
  (Array.isArray(field.options) && field.options.length > 0) ||
  (Array.isArray(field.enum) && field.enum.length > 0)

/** 字段是否有 action/button 声明。 */
export const hasFieldAction = (field: SchemaFieldDefinition): boolean =>
  Boolean(
    (field.action && typeof field.action === 'object') ||
    (field.button && typeof field.button === 'object')
  )

export const isButtonField = (field: SchemaFieldDefinition): boolean =>
  field.type === 'button' || field.type === 'action' || hasFieldAction(field)

export const isAutocompleteField = (field: SchemaFieldDefinition): boolean =>
  Boolean(field.allow_custom) && isStringField(field) && hasSelectableOptions(field)

export const isOrderedMultiSelectField = (field: SchemaFieldDefinition): boolean =>
  field.selection_mode === 'ordered' && field.type === 'multiselect'

export const isMultiSelectField = (field: SchemaFieldDefinition): boolean =>
  !isOrderedMultiSelectField(field) &&
  (field.type === 'multiselect' || (hasSelectableOptions(field) && isListField(field)))

export const isSelectField = (field: SchemaFieldDefinition): boolean =>
  field.type === 'select' ||
  (!isAutocompleteField(field) && !isMultiSelectField(field) && hasSelectableOptions(field))

export const isBooleanField = (field: SchemaFieldDefinition): boolean =>
  field.type === 'boolean' || field.type === 'bool'

export const isPathField = (field: SchemaFieldDefinition): boolean =>
  ['folder', 'file', 'path'].includes(field.type)

export const isStringField = (field: SchemaFieldDefinition): boolean =>
  ['string', 'str', 'uuid', 'datetime', 'related-id', 'readonly'].includes(field.type)

export const isSliderField = (field: SchemaFieldDefinition): boolean => field.type === 'slider'

export const isNumberField = (field: SchemaFieldDefinition): boolean =>
  ['number', 'integer', 'int', 'float', 'slider'].includes(field.type)

export const isListField = (field: SchemaFieldDefinition): boolean =>
  field.type === 'list' || field.type.startsWith('list[')

export const isJsonField = (field: SchemaFieldDefinition): boolean => field.type === 'json'

export const isPasswordField = (field: SchemaFieldDefinition): boolean =>
  (isStringField(field) && field.format === 'password') || field.type === 'password'

export const isTextareaField = (field: SchemaFieldDefinition): boolean =>
  isJsonField(field) || (isStringField(field) && field.format === 'textarea')

/** list 字段的元素类型：显式 `item_type` 优先，否则解析 `list[<type>]`，默认 string。 */
export const getListItemType = (field: SchemaFieldDefinition): string => {
  if (field.item_type) {
    return field.item_type
  }
  const matched = /^list\[(.+)]$/.exec(field.type)
  return matched?.[1] || 'string'
}

/** path 字段的种类：folder 或 file。 */
export const getPathKind = (field: SchemaFieldDefinition): 'folder' | 'file' => {
  if (field.path_kind === 'folder' || field.type === 'folder') {
    return 'folder'
  }
  return 'file'
}

/** 把任意值转成有限数字；无法转换时返回 undefined。 */
export const toFiniteNumber = (value: unknown): number | undefined => {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value
  }
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : undefined
  }
  return undefined
}

export const getSchemaConstraint = (field: SchemaFieldDefinition, key: string): unknown =>
  field.constraints?.[key]

export const getStringMaxLength = (field: SchemaFieldDefinition): number | undefined =>
  toFiniteNumber(getSchemaConstraint(field, 'max_length'))

export const getTextareaRows = (field: SchemaFieldDefinition): number => {
  const rows = toFiniteNumber(field.rows)
  return rows && rows > 0 ? rows : 4
}

export const getNumberMin = (field: SchemaFieldDefinition): number | undefined => {
  if (typeof field.min === 'number') {
    return field.min
  }
  const ge = toFiniteNumber(getSchemaConstraint(field, 'ge'))
  if (ge !== undefined) {
    return ge
  }
  return toFiniteNumber(getSchemaConstraint(field, 'gt'))
}

export const getNumberMax = (field: SchemaFieldDefinition): number | undefined => {
  if (typeof field.max === 'number') {
    return field.max
  }
  const le = toFiniteNumber(getSchemaConstraint(field, 'le'))
  if (le !== undefined) {
    return le
  }
  return toFiniteNumber(getSchemaConstraint(field, 'lt'))
}

export const getNumberStep = (field: SchemaFieldDefinition): number | undefined => {
  if (typeof field.step === 'number') {
    return field.step
  }
  const multipleOf = toFiniteNumber(getSchemaConstraint(field, 'multiple_of'))
  if (multipleOf && multipleOf > 0) {
    return multipleOf
  }
  return field.type === 'integer' || field.type === 'int' ? 1 : undefined
}

/** 字段布局尺寸别名 → 标准化 key。 */
const schemaFieldSizeAliases = {
  small: '1/3',
  half: '1/2',
  medium: '2/3',
  large: '1/1',
} as const

const schemaFieldSizeClasses = {
  '1/1': '1-1',
  '1/2': '1-2',
  '1/3': '1-3',
  '2/3': '2-3',
  '1/4': '1-4',
  '3/4': '3-4',
} as const

export type SchemaFieldLayoutSize = keyof typeof schemaFieldSizeClasses

export const normalizeFieldLayoutSize = (
  size: SchemaFieldDefinition['size']
): SchemaFieldLayoutSize => {
  if (typeof size !== 'string') {
    return '1/3'
  }

  if (size in schemaFieldSizeClasses) {
    return size as SchemaFieldLayoutSize
  }

  if (size in schemaFieldSizeAliases) {
    return schemaFieldSizeAliases[size as keyof typeof schemaFieldSizeAliases]
  }

  return '1/3'
}

export const getFieldLayoutSizeClass = (field: SchemaFieldDefinition): string =>
  schemaFieldSizeClasses[normalizeFieldLayoutSize(field.size)]

/** 校验 URL 是否为 http/https。 */
export const isValidHttpUrl = (value: string): string => {
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

/** 对单个字段值进行校验；返回错误文案，空串表示通过。 */
export const validateFieldValue = (
  fieldPath: string,
  field: SchemaFieldDefinition,
  value: unknown
): string => {
  // fieldPath 参数保留以便未来在错误消息中引用路径；当前实现与原 SchemaForm 一致。
  void fieldPath

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

  if (isOrderedMultiSelectField(field) || isMultiSelectField(field) || isListField(field)) {
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

/** 字段帮助文案：优先校验错误，其次 `help`，再次 `description`（与 label 不同时），最后 examples。 */
export const getFieldHelp = (
  field: SchemaFieldDefinition,
  fieldError: string | undefined
): string | undefined => {
  if (fieldError) {
    return fieldError
  }
  if (typeof field.help === 'string' && field.help.trim()) {
    return field.help
  }
  if (
    typeof field.description === 'string' &&
    field.description.trim() &&
    field.description !== getFieldLabel(field)
  ) {
    return field.description
  }
  if (Array.isArray(field.examples) && field.examples.length > 0) {
    return `示例：${field.examples.map(item => String(item)).join('、')}`
  }
  return undefined
}

/** 字段类型展示标签（中文）。 */
export const getTypeLabel = (field: SchemaFieldDefinition): string => {
  if (isButtonField(field)) {
    return '动作'
  }
  if (isSelectField(field)) {
    return '枚举'
  }
  if (isOrderedMultiSelectField(field) || isMultiSelectField(field)) {
    return '多选'
  }
  if (isSliderField(field)) {
    return '滑动条'
  }
  if (isPathField(field)) {
    return getPathKind(field) === 'folder' ? '文件夹' : '文件'
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

/** 动作按钮文案：优先 `action.label`，回退字段标签。 */
export const getActionLabel = (field: SchemaFieldDefinition): string => {
  const action = field.action || field.button
  return action?.label || getFieldLabel(field)
}

/** 判断字段是否应被渲染（未隐藏且不在 hideFields 中）。 */
export const shouldRenderField = (field: SchemaFieldDefinition, hideFields: string[]): boolean =>
  !field.hidden && !hideFields.includes(getFieldPath(field))

/**
 * 将 schema 归一为分组数组。
 *
 * - 若 schema 是 `GroupedSchemaDefinition`（含 `groups`），按声明顺序返回，并过滤隐藏字段与空组。
 * - 否则视为 `Record<string, SchemaFieldDefinition>`，把每个 entry 的 key 作为字段 key，归入单一默认组。
 */
export const normalizeSchemaGroups = (
  schema: SchemaDefinition | null | undefined,
  hideFields: string[] = []
): SchemaGroupDefinition[] => {
  if (!schema) {
    return []
  }

  if ('groups' in schema && Array.isArray((schema as GroupedSchemaDefinition).groups)) {
    return (schema as GroupedSchemaDefinition).groups
      .map(group => ({
        ...group,
        fields: (group.fields || []).filter(field => shouldRenderField(field, hideFields)),
      }))
      .filter(group => group.fields.length > 0)
  }

  const fields = Object.entries(schema as Record<string, SchemaFieldDefinition>)
    .map(([field, fieldSchema]) => ({
      ...fieldSchema,
      key: field,
    }))
    .filter(field => shouldRenderField(field, hideFields))

  return [
    {
      key: 'default',
      label: '',
      fields,
    },
  ]
}

/** 是否显示组标题：存在多组且当前组有 label 或非默认 key。 */
export const showGroupTitle = (
  groups: SchemaGroupDefinition[],
  group: SchemaGroupDefinition
): boolean => groups.length > 1 && Boolean(group.label || (group.key && group.key !== 'default'))

/** 收集所有可见字段的校验错误。 */
export const collectValidationErrors = (
  groups: SchemaGroupDefinition[],
  modelValue: Record<string, any>
): SchemaValidationErrorMap => {
  const errors: SchemaValidationErrorMap = {}
  groups.forEach(group => {
    group.fields.forEach(field => {
      const fieldPath = getFieldPath(field)
      const error = validateFieldValue(fieldPath, field, getValueByPath(modelValue, fieldPath))
      if (error) {
        errors[fieldPath] = error
      }
    })
  })
  return errors
}

/** list 元素值归一化：number 转 number，boolean 转 boolean，其余转字符串。 */
export const normalizeListValueByType = (value: unknown, itemType?: string): unknown => {
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

/** 把 list 值归一为带 `__rowKey` 的行数组，供 a-table 渲染。 */
export const getListRows = (
  modelValue: Record<string, any>,
  field: string
): Array<{ __rowKey: string; value: unknown }> => {
  const value = getValueByPath(modelValue, field)
  if (!Array.isArray(value)) {
    return []
  }
  return value.map((item, index) => ({
    __rowKey: `${field}-${index}`,
    value: item,
  }))
}

/** 新增一行到 list 字段；返回应 emit 的新 modelValue。 */
export const addListRow = (
  modelValue: Record<string, any>,
  field: string,
  itemType?: string
): Record<string, any> => {
  const value = getValueByPath(modelValue, field)
  const list = Array.isArray(value) ? [...value] : []
  if (itemType === 'number') {
    list.push(0)
  } else if (itemType === 'boolean') {
    list.push(false)
  } else {
    list.push('')
  }
  const next = cloneModel(modelValue)
  setValueByPath(next, field, list)
  return next
}

/** 删除 list 字段中指定索引的行；返回应 emit 的新 modelValue。 */
export const removeListRow = (
  modelValue: Record<string, any>,
  field: string,
  index: number
): Record<string, any> => {
  const value = getValueByPath(modelValue, field)
  const list = Array.isArray(value) ? [...value] : []
  list.splice(index, 1)
  const next = cloneModel(modelValue)
  setValueByPath(next, field, list)
  return next
}

/** 更新 list 字段中指定索引的行值；返回应 emit 的新 modelValue。 */
export const updateListRowValue = (
  modelValue: Record<string, any>,
  field: string,
  index: number,
  value: unknown,
  itemType?: string
): Record<string, any> => {
  const raw = getValueByPath(modelValue, field)
  const list = Array.isArray(raw) ? [...raw] : []
  list[index] = normalizeListValueByType(value, itemType)
  const next = cloneModel(modelValue)
  setValueByPath(next, field, list)
  return next
}

/** 把 key_value 对象归一为带 `__rowKey` 的行数组。 */
export const getKeyValueRows = (
  modelValue: Record<string, any>,
  field: string
): Array<{ __rowKey: string; key: string; value: string }> => {
  const value = getValueByPath(modelValue, field)
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return []
  }
  return Object.entries(value as Record<string, unknown>).map(([key, item], index) => ({
    __rowKey: `${field}-${index}`,
    key,
    value: String(item ?? ''),
  }))
}

/** 为 key_value 字段新增一个不冲突的键；返回应 emit 的新 modelValue。 */
export const addKeyValueRow = (
  modelValue: Record<string, any>,
  field: string
): Record<string, any> => {
  const value = getValueByPath(modelValue, field)
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
  const next = cloneModel(modelValue)
  setValueByPath(next, field, obj)
  return next
}

/** 删除 key_value 字段中指定键；返回应 emit 的新 modelValue。 */
export const removeKeyValueRow = (
  modelValue: Record<string, any>,
  field: string,
  key: string
): Record<string, any> => {
  const value = getValueByPath(modelValue, field)
  const obj =
    value && typeof value === 'object' && !Array.isArray(value)
      ? { ...(value as Record<string, unknown>) }
      : {}
  delete obj[key]
  const next = cloneModel(modelValue)
  setValueByPath(next, field, obj)
  return next
}

/** 更新 key_value 字段中指定键的键名；返回应 emit 的新 modelValue。 */
export const updateKeyValueRowKey = (
  modelValue: Record<string, any>,
  field: string,
  oldKey: string,
  newKey: string
): Record<string, any> => {
  const value = getValueByPath(modelValue, field)
  const obj =
    value && typeof value === 'object' && !Array.isArray(value)
      ? { ...(value as Record<string, unknown>) }
      : {}
  const finalKey = newKey.trim()
  if (!finalKey || finalKey === oldKey) {
    return modelValue
  }
  obj[finalKey] = obj[oldKey]
  delete obj[oldKey]
  const next = cloneModel(modelValue)
  setValueByPath(next, field, obj)
  return next
}

/** 更新 key_value 字段中指定键的值；返回应 emit 的新 modelValue。 */
export const updateKeyValueRowValue = (
  modelValue: Record<string, any>,
  field: string,
  key: string,
  value: string
): Record<string, any> => {
  const current = getValueByPath(modelValue, field)
  const obj =
    current && typeof current === 'object' && !Array.isArray(current)
      ? { ...(current as Record<string, unknown>) }
      : {}
  obj[key] = value
  const next = cloneModel(modelValue)
  setValueByPath(next, field, obj)
  return next
}

export interface TableRow {
  __rowKey: string
  [key: string]: unknown
}

export interface TableColumn {
  title: string
  dataIndex: string
  key: string
}

/** 把 table 字段值归一为带 `__rowKey` 的行数组。 */
export const getTableRows = (modelValue: Record<string, any>, field: string): TableRow[] => {
  const value = getValueByPath(modelValue, field)
  if (!Array.isArray(value)) {
    return []
  }
  return value.map((item, index) => ({
    __rowKey: `${field}-${index}`,
    ...(typeof item === 'object' && item ? item : {}),
  }))
}

/** 根据现有行推断 table 字段的列定义；无数据时给一列 `col_1`，并追加操作列。 */
export const getTableColumns = (modelValue: Record<string, any>, field: string): TableColumn[] => {
  const rows = getTableRows(modelValue, field)
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

/** 为 table 字段新增一行（按现有列填空串）；返回应 emit 的新 modelValue。 */
export const addTableRow = (
  modelValue: Record<string, any>,
  field: string
): Record<string, any> => {
  const rows = getTableRows(modelValue, field).map(({ __rowKey, ...row }) => row)
  const columns = getTableColumns(modelValue, field)
  const row: Record<string, unknown> = {}
  columns.forEach(col => {
    if (col.key !== 'action') {
      row[col.key] = ''
    }
  })
  rows.push(row)
  const next = cloneModel(modelValue)
  setValueByPath(next, field, rows)
  return next
}

/** 删除 table 字段中指定索引的行；返回应 emit 的新 modelValue。 */
export const removeTableRow = (
  modelValue: Record<string, any>,
  field: string,
  index: number
): Record<string, any> => {
  const rows = getTableRows(modelValue, field).map(({ __rowKey, ...row }) => row)
  rows.splice(index, 1)
  const next = cloneModel(modelValue)
  setValueByPath(next, field, rows)
  return next
}

/** 为 table 字段新增一列（在所有行上填空串）；返回应 emit 的新 modelValue。 */
export const addTableColumn = (
  modelValue: Record<string, any>,
  field: string
): Record<string, any> => {
  const rows = getTableRows(modelValue, field).map(({ __rowKey, ...row }) => ({ ...row }))
  const columns = getTableColumns(modelValue, field)
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
  const next = cloneModel(modelValue)
  setValueByPath(next, field, rows)
  return next
}

/** 更新 table 字段中指定行与列的单元格值；返回应 emit 的新 modelValue。 */
export const updateTableCellValue = (
  modelValue: Record<string, any>,
  field: string,
  index: number,
  key: string,
  value: string
): Record<string, any> => {
  const rows = getTableRows(modelValue, field).map(({ __rowKey, ...row }) => ({ ...row }))
  if (!rows[index]) {
    rows[index] = {}
  }
  rows[index][key] = value
  const next = cloneModel(modelValue)
  setValueByPath(next, field, rows)
  return next
}

/** 把 JSON 字段值序列化为带缩进的文本；值为空时返回 `'{}'`。 */
export const getJsonText = (modelValue: Record<string, any>, field: string): string =>
  JSON.stringify(getValueByPath(modelValue, field) ?? {}, null, 2)

/** 解析 JSON 字段的失焦输入；返回 `{ value, error }`，error 非空时表示格式无效。 */
export const parseJsonInput = (text: string): { value: unknown; error: string } => {
  try {
    const parsed = text.trim() ? JSON.parse(text) : {}
    return { value: parsed, error: '' }
  } catch {
    return { value: undefined, error: 'JSON 格式无效' }
  }
}

/** 把 boolean 字段值转为布尔。 */
export const getBooleanValue = (value: unknown): boolean => Boolean(value)

/** 把 number 字段值转为有限数字；无法转换时返回 undefined。 */
export const getNumberValue = (value: unknown): number | undefined => {
  if (typeof value === 'number') {
    return value
  }
  if (typeof value === 'string' && value.trim() !== '') {
    const numberValue = Number(value)
    return Number.isFinite(numberValue) ? numberValue : undefined
  }
  return undefined
}

/** 把 slider 字段值转为有限数字；为空时回退到字段 min。 */
export const getSliderValue = (field: SchemaFieldDefinition, value: unknown): number => {
  const num = getNumberValue(value)
  if (num !== undefined) {
    return num
  }
  return getNumberMin(field) ?? 0
}

/** 把 multiselect 字段值归一为数组。 */
export const getEnumListValue = (value: unknown): unknown[] => (Array.isArray(value) ? value : [])

/** 把 ordered-multiselect 字段值按 options 顺序归一。 */
export const normalizeOrderedMultiSelectValue = (
  field: SchemaFieldDefinition,
  value: unknown
): unknown[] => {
  const selected = new Set(Array.isArray(value) ? value : [])
  const normalized: unknown[] = []
  for (const option of getFieldOptions(field)) {
    if (selected.has(option.value)) {
      normalized.push(option.value)
    }
  }
  return normalized
}

/** 判断 ordered-multiselect 字段中指定索引的 option 是否被选中。 */
export const isOrderedOptionChecked = (
  field: SchemaFieldDefinition,
  value: unknown,
  index: number
): boolean => {
  const options = getFieldOptions(field)
  const current = normalizeOrderedMultiSelectValue(field, value)
  return current.includes(options[index]?.value)
}

/** 切换 ordered-multiselect 字段中指定索引的 option 选中状态；返回新数组。 */
export const toggleOrderedOption = (
  field: SchemaFieldDefinition,
  value: unknown,
  index: number
): unknown[] => {
  const options = getFieldOptions(field)
  const current = normalizeOrderedMultiSelectValue(field, value)
  const target = options[index]?.value
  const exists = current.includes(target)
  return exists
    ? current.filter(item => item !== target)
    : normalizeOrderedMultiSelectValue(field, [...current, target])
}
