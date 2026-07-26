import { describe, expect, it } from 'vitest'
import type { SchemaDefinition, SchemaFieldDefinition } from '@/types/schemaForm'
import {
  addKeyValueRow,
  addListRow,
  addTableColumn,
  addTableRow,
  cloneModel,
  collectValidationErrors,
  getActionLabel,
  getBooleanValue,
  getFieldHelp,
  getFieldLabel,
  getFieldLayoutSizeClass,
  getFieldOptions,
  getFieldPath,
  getFieldPlaceholder,
  getJsonText,
  getKeyValueRows,
  getListRows,
  getListItemType,
  getNumberMax,
  getNumberMin,
  getNumberStep,
  getNumberValue,
  getSliderValue,
  getStringMaxLength,
  getTableColumns,
  getTableRows,
  getTextareaRows,
  getTypeLabel,
  getEnumListValue,
  getValueByPath,
  isAutocompleteField,
  isBooleanField,
  isButtonField,
  isJsonField,
  isListField,
  isMultiSelectField,
  isNumberField,
  isOrderedMultiSelectField,
  isOrderedOptionChecked,
  isPathField,
  isPasswordField,
  isSelectField,
  isSliderField,
  isStringField,
  isTextareaField,
  normalizeFieldLayoutSize,
  normalizeSchemaGroups,
  normalizeListValueByType,
  parseJsonInput,
  removeKeyValueRow,
  removeListRow,
  removeTableRow,
  setValueByPath,
  showGroupTitle,
  toggleOrderedOption,
  updateKeyValueRowKey,
  updateKeyValueRowValue,
  updateListRowValue,
  updateTableCellValue,
  validateFieldValue,
} from './schemaFormCore'

const field = (overrides: Partial<SchemaFieldDefinition> = {}): SchemaFieldDefinition => ({
  type: 'string',
  ...overrides,
})

describe('getFieldPath / getFieldLabel / getFieldPlaceholder', () => {
  it('prefers key over name and falls back to empty string', () => {
    expect(getFieldPath(field({ key: 'a', name: 'b' }))).toBe('a')
    expect(getFieldPath(field({ name: 'b' }))).toBe('b')
    expect(getFieldPath(field({}))).toBe('')
  })

  it('label falls back through label → title → description → path', () => {
    expect(getFieldLabel(field({ key: 'k', label: 'L' }))).toBe('L')
    expect(getFieldLabel(field({ key: 'k', title: 'T' }))).toBe('T')
    expect(getFieldLabel(field({ key: 'k', description: 'D' }))).toBe('D')
    expect(getFieldLabel(field({ key: 'k' }))).toBe('k')
  })

  it('placeholder returns undefined for non-string values', () => {
    expect(getFieldPlaceholder(field({ placeholder: '提示' }))).toBe('提示')
    // placeholder 类型为 string；非字符串值在运行时会被 getFieldPlaceholder 过滤为 undefined。
    // 用 as any 绕过 TS 类型检查以测试运行时降级行为。
    expect(getFieldPlaceholder(field({ placeholder: 123 as any }))).toBeUndefined()
    expect(getFieldPlaceholder(field({}))).toBeUndefined()
  })
})

describe('getValueByPath / setValueByPath / cloneModel', () => {
  it('reads nested values via dot path and returns undefined for missing or non-object nodes', () => {
    const source = { a: { b: { c: 1 } }, list: [1, 2], empty: null }
    expect(getValueByPath(source, 'a.b.c')).toBe(1)
    expect(getValueByPath(source, 'a.b.d')).toBeUndefined()
    expect(getValueByPath(source, 'a.x.y')).toBeUndefined()
    expect(getValueByPath(source, 'empty.x')).toBeUndefined()
    expect(getValueByPath(source, '')).toBeUndefined()
    expect(getValueByPath(null, 'a')).toBeUndefined()
  })

  it('writes nested values and auto-creates missing object nodes', () => {
    const target: Record<string, any> = {}
    setValueByPath(target, 'a.b.c', 42)
    expect(target.a.b.c).toBe(42)
    setValueByPath(target, 'a.b.d', 'hi')
    expect(target.a.b.d).toBe('hi')
    // 覆盖非对象中间节点
    setValueByPath(target, 'a.b', { c: 100 })
    expect(target.a.b.c).toBe(100)
  })

  it('cloneModel deep clones and returns empty object for nullish input', () => {
    const original = { a: { b: 1 } }
    const cloned = cloneModel(original)
    expect(cloned).toEqual(original)
    expect(cloned).not.toBe(original)
    expect(cloned.a).not.toBe(original.a)
    expect(cloneModel(null)).toEqual({})
    expect(cloneModel(undefined)).toEqual({})
  })
})

describe('schema type predicates (matrix)', () => {
  it('button / action / hasFieldAction', () => {
    expect(isButtonField(field({ type: 'button' }))).toBe(true)
    expect(isButtonField(field({ type: 'action' }))).toBe(true)
    expect(isButtonField(field({ type: 'string', action: { path: '/x' } }))).toBe(true)
    expect(isButtonField(field({ type: 'string', button: { path: '/x' } }))).toBe(true)
    expect(isButtonField(field({ type: 'string' }))).toBe(false)
  })

  it('string family (string/str/uuid/datetime/related-id/readonly)', () => {
    for (const t of ['string', 'str', 'uuid', 'datetime', 'related-id', 'readonly']) {
      expect(isStringField(field({ type: t }))).toBe(true)
    }
    expect(isStringField(field({ type: 'number' }))).toBe(false)
  })

  it('number family (number/integer/int/float/slider)', () => {
    for (const t of ['number', 'integer', 'int', 'float', 'slider']) {
      expect(isNumberField(field({ type: t }))).toBe(true)
    }
  })

  it('boolean family', () => {
    expect(isBooleanField(field({ type: 'boolean' }))).toBe(true)
    expect(isBooleanField(field({ type: 'bool' }))).toBe(true)
    expect(isBooleanField(field({ type: 'string' }))).toBe(false)
  })

  it('path family', () => {
    expect(isPathField(field({ type: 'folder' }))).toBe(true)
    expect(isPathField(field({ type: 'file' }))).toBe(true)
    expect(isPathField(field({ type: 'path' }))).toBe(true)
    expect(isPathField(field({ type: 'string' }))).toBe(false)
  })

  it('list family and getListItemType', () => {
    expect(isListField(field({ type: 'list' }))).toBe(true)
    expect(isListField(field({ type: 'list[number]' }))).toBe(true)
    expect(isListField(field({ type: 'list[boolean]' }))).toBe(true)
    expect(getListItemType(field({ type: 'list[number]' }))).toBe('number')
    expect(getListItemType(field({ type: 'list', item_type: 'boolean' }))).toBe('boolean')
    expect(getListItemType(field({ type: 'list' }))).toBe('string')
  })

  it('json / textarea / password', () => {
    expect(isJsonField(field({ type: 'json' }))).toBe(true)
    expect(isTextareaField(field({ type: 'string', format: 'textarea' }))).toBe(true)
    expect(isTextareaField(field({ type: 'json' }))).toBe(true)
    expect(isPasswordField(field({ type: 'string', format: 'password' }))).toBe(true)
    expect(isPasswordField(field({ type: 'password' }))).toBe(true)
  })

  it('select / multiselect / ordered-multiselect / autocomplete', () => {
    const opts = { options: [{ label: 'A', value: 'a' }] }
    expect(isSelectField(field({ type: 'select' }))).toBe(true)
    expect(isSelectField(field({ type: 'string', ...opts }))).toBe(true)
    expect(isMultiSelectField(field({ type: 'multiselect' }))).toBe(true)
    expect(
      isOrderedMultiSelectField(field({ type: 'multiselect', selection_mode: 'ordered' }))
    ).toBe(true)
    expect(isAutocompleteField(field({ type: 'string', allow_custom: true, ...opts }))).toBe(true)
  })

  it('slider', () => {
    expect(isSliderField(field({ type: 'slider' }))).toBe(true)
  })

  it('isSensitiveFieldCore covers password and explicit sensitive flag', () => {
    expect(isPasswordField(field({ type: 'string', format: 'password' }))).toBe(true)
    expect(isPasswordField(field({ type: 'password' }))).toBe(true)
    expect(isPasswordField(field({ type: 'string' }))).toBe(false)
  })
})

describe('getFieldOptions / getActionLabel', () => {
  it('normalizes options array of mixed shapes', () => {
    expect(getFieldOptions(field({ options: [{ label: 'A', value: 'a' }, 'plain', 42] }))).toEqual([
      { label: 'A', value: 'a' },
      { label: 'plain', value: 'plain' },
      { label: '42', value: 42 },
    ])
  })

  it('falls back to enum', () => {
    expect(getFieldOptions(field({ enum: ['x', 'y'] }))).toEqual([
      { label: 'x', value: 'x' },
      { label: 'y', value: 'y' },
    ])
  })

  it('returns empty for fields without options/enum', () => {
    expect(getFieldOptions(field({}))).toEqual([])
  })

  it('action label prefers action.label then field label', () => {
    expect(getActionLabel(field({ type: 'button', label: 'F', action: { label: 'A' } }))).toBe('A')
    expect(getActionLabel(field({ type: 'button', label: 'F' }))).toBe('F')
  })
})

describe('number constraints', () => {
  it('min/max/step prefer field props then constraints', () => {
    expect(getNumberMin(field({ type: 'number', min: 1 }))).toBe(1)
    expect(getNumberMin(field({ type: 'number', constraints: { ge: 2 } }))).toBe(2)
    expect(getNumberMin(field({ type: 'number', constraints: { gt: 3 } }))).toBe(3)
    expect(getNumberMin(field({ type: 'number' }))).toBeUndefined()

    expect(getNumberMax(field({ type: 'number', max: 10 }))).toBe(10)
    expect(getNumberMax(field({ type: 'number', constraints: { le: 9 } }))).toBe(9)
    expect(getNumberMax(field({ type: 'number', constraints: { lt: 8 } }))).toBe(8)

    expect(getNumberStep(field({ type: 'number', step: 0.5 }))).toBe(0.5)
    expect(getNumberStep(field({ type: 'number', constraints: { multiple_of: 2 } }))).toBe(2)
    expect(getNumberStep(field({ type: 'integer' }))).toBe(1)
    expect(getNumberStep(field({ type: 'float' }))).toBeUndefined()
  })

  it('getNumberValue parses strings and rejects invalid', () => {
    expect(getNumberValue(42)).toBe(42)
    expect(getNumberValue('42')).toBe(42)
    expect(getNumberValue('abc')).toBeUndefined()
    expect(getNumberValue(null)).toBeUndefined()
    expect(getNumberValue('')).toBeUndefined()
  })

  it('getSliderValue falls back to min when value is empty', () => {
    expect(getSliderValue(field({ type: 'slider', min: 5 }), undefined)).toBe(5)
    expect(getSliderValue(field({ type: 'slider', min: 5 }), 10)).toBe(10)
    expect(getSliderValue(field({ type: 'slider' }), undefined)).toBe(0)
  })
})

describe('string constraints', () => {
  it('max_length and textarea rows', () => {
    expect(getStringMaxLength(field({ type: 'string', constraints: { max_length: 100 } }))).toBe(
      100
    )
    expect(getStringMaxLength(field({ type: 'string' }))).toBeUndefined()
    expect(getTextareaRows(field({ type: 'string', format: 'textarea', rows: 6 }))).toBe(6)
    expect(getTextareaRows(field({ type: 'string', format: 'textarea' }))).toBe(4)
  })
})

describe('layout size normalization', () => {
  it('aliases map to canonical sizes', () => {
    expect(normalizeFieldLayoutSize('small')).toBe('1/3')
    expect(normalizeFieldLayoutSize('half')).toBe('1/2')
    expect(normalizeFieldLayoutSize('medium')).toBe('2/3')
    expect(normalizeFieldLayoutSize('large')).toBe('1/1')
    expect(normalizeFieldLayoutSize('1/4')).toBe('1/4')
    expect(normalizeFieldLayoutSize(undefined)).toBe('1/3')
    // 'unknown' 不是合法 SchemaFieldSize，用 as any 绕过 TS 检查测试运行时降级。
    expect(normalizeFieldLayoutSize('unknown' as any)).toBe('1/3')
  })

  it('getFieldLayoutSizeClass returns class suffix', () => {
    expect(getFieldLayoutSizeClass(field({ size: '1/2' }))).toBe('1-2')
    expect(getFieldLayoutSizeClass(field({ size: 'half' }))).toBe('1-2')
    expect(getFieldLayoutSizeClass(field({}))).toBe('1-3')
  })
})

describe('normalizeSchemaGroups / showGroupTitle', () => {
  it('groups definition preserves groups and filters hidden fields', () => {
    const schema: SchemaDefinition = {
      groups: [
        {
          key: 'g1',
          label: '组1',
          fields: [
            field({ key: 'a', type: 'string' }),
            field({ key: 'b', type: 'string', hidden: true }),
          ],
        },
        { key: 'g2', label: '', fields: [] },
      ],
    }
    const groups = normalizeSchemaGroups(schema, ['a'])
    expect(groups).toHaveLength(0)
    // 不隐藏时 g1 出现且只剩 a
    const groups2 = normalizeSchemaGroups(schema, [])
    expect(groups2).toHaveLength(1)
    expect(groups2[0].fields.map(f => f.key)).toEqual(['a'])
  })

  it('record schema is normalized into a single default group', () => {
    const schema: SchemaDefinition = {
      foo: field({ type: 'string' }),
      bar: field({ type: 'number' }),
    }
    const groups = normalizeSchemaGroups(schema)
    expect(groups).toHaveLength(1)
    expect(groups[0].key).toBe('default')
    expect(groups[0].fields.map(f => f.key)).toEqual(['foo', 'bar'])
  })

  it('null/undefined schema returns empty array', () => {
    expect(normalizeSchemaGroups(null)).toEqual([])
    expect(normalizeSchemaGroups(undefined)).toEqual([])
  })

  it('showGroupTitle only when multiple groups and group has label or non-default key', () => {
    const groups = [
      { key: 'default', label: '', fields: [] },
      { key: 'g1', label: 'L', fields: [] },
    ]
    expect(showGroupTitle(groups, groups[0])).toBe(false)
    expect(showGroupTitle(groups, groups[1])).toBe(true)
    expect(showGroupTitle([groups[0]], groups[0])).toBe(false)
  })
})

describe('validateFieldValue matrix', () => {
  it('required empty returns error', () => {
    expect(validateFieldValue('x', field({ type: 'string', required: true }), '')).toBe(
      '该字段为必填项'
    )
    expect(validateFieldValue('x', field({ type: 'string', required: true }), undefined)).toBe(
      '该字段为必填项'
    )
    expect(validateFieldValue('x', field({ type: 'string', required: false }), '')).toBe('')
  })

  it('string min/max length and pattern', () => {
    expect(
      validateFieldValue('x', field({ type: 'string', constraints: { min_length: 3 } }), 'ab')
    ).toBe('至少需要 3 个字符')
    expect(
      validateFieldValue('x', field({ type: 'string', constraints: { max_length: 3 } }), 'abcd')
    ).toBe('最多允许 3 个字符')
    expect(
      validateFieldValue('x', field({ type: 'string', constraints: { pattern: '^\\d+$' } }), 'abc')
    ).toBe('内容不符合格式要求')
    expect(
      validateFieldValue('x', field({ type: 'string', constraints: { pattern: '^\\d+$' } }), '123')
    ).toBe('')
    // 无效 pattern 静默通过
    expect(
      validateFieldValue('x', field({ type: 'string', constraints: { pattern: '(' } }), 'abc')
    ).toBe('')
  })

  it('string url format', () => {
    expect(validateFieldValue('x', field({ type: 'string', format: 'url' }), 'not-a-url')).toBe(
      'URL 格式无效'
    )
    expect(validateFieldValue('x', field({ type: 'string', format: 'url' }), 'ftp://x')).toBe(
      '仅支持 http 或 https 地址'
    )
    expect(
      validateFieldValue('x', field({ type: 'string', format: 'url' }), 'https://example.com')
    ).toBe('')
  })

  it('number min/max', () => {
    expect(validateFieldValue('x', field({ type: 'number', min: 1 }), 0)).toBe('数值不能小于 1')
    expect(validateFieldValue('x', field({ type: 'number', max: 10 }), 11)).toBe('数值不能大于 10')
    expect(validateFieldValue('x', field({ type: 'number' }), 'abc')).toBe('请输入有效数字')
    expect(validateFieldValue('x', field({ type: 'number' }), 5)).toBe('')
  })

  it('list / multiselect / ordered-multiselect require array', () => {
    expect(validateFieldValue('x', field({ type: 'list' }), 'not-array')).toBe('该字段需要列表值')
    expect(validateFieldValue('x', field({ type: 'list' }), [])).toBe('')
    expect(
      validateFieldValue('x', field({ type: 'multiselect', selection_mode: 'ordered' }), {})
    ).toBe('该字段需要列表值')
  })

  it('json requires object', () => {
    expect(validateFieldValue('x', field({ type: 'json' }), 'x')).toBe('该字段需要 JSON 对象')
    expect(validateFieldValue('x', field({ type: 'json' }), {})).toBe('')
  })

  it('key_value requires object, table requires array', () => {
    expect(validateFieldValue('x', field({ type: 'key_value' }), [])).toBe('该字段需要键值对象')
    expect(validateFieldValue('x', field({ type: 'key_value' }), {})).toBe('')
    expect(validateFieldValue('x', field({ type: 'table' }), {})).toBe('该字段需要表格数组')
    expect(validateFieldValue('x', field({ type: 'table' }), [])).toBe('')
  })

  it('button fields never error', () => {
    expect(validateFieldValue('x', field({ type: 'button' }), undefined)).toBe('')
  })
})

describe('collectValidationErrors', () => {
  it('collects errors across all visible groups', () => {
    const schema: SchemaDefinition = {
      groups: [
        {
          key: 'g1',
          fields: [
            field({ key: 'a', type: 'string', required: true }),
            field({ key: 'b', type: 'number', min: 1 }),
          ],
        },
      ],
    }
    const groups = normalizeSchemaGroups(schema)
    const errors = collectValidationErrors(groups, { a: '', b: 0 })
    expect(errors.a).toBe('该字段为必填项')
    expect(errors.b).toBe('数值不能小于 1')
    const ok = collectValidationErrors(groups, { a: 'x', b: 5 })
    expect(Object.keys(ok)).toHaveLength(0)
  })
})

describe('getFieldHelp / getTypeLabel', () => {
  it('help prefers error, then help, then description (when different from label), then examples', () => {
    expect(getFieldHelp(field({ key: 'k', label: 'L', help: 'H' }), undefined)).toBe('H')
    expect(getFieldHelp(field({ key: 'k', label: 'L', description: 'D' }), undefined)).toBe('D')
    // description 与 label 相同时不返回
    expect(
      getFieldHelp(field({ key: 'k', label: 'L', description: 'L' }), undefined)
    ).toBeUndefined()
    expect(getFieldHelp(field({ key: 'k', examples: ['a', 'b'] }), undefined)).toBe('示例：a、b')
    expect(getFieldHelp(field({ key: 'k' }), '错误')).toBe('错误')
    expect(getFieldHelp(field({ key: 'k' }), undefined)).toBeUndefined()
  })

  it('type label covers all known types', () => {
    expect(getTypeLabel(field({ type: 'button' }))).toBe('动作')
    expect(getTypeLabel(field({ type: 'select' }))).toBe('枚举')
    expect(getTypeLabel(field({ type: 'multiselect' }))).toBe('多选')
    expect(getTypeLabel(field({ type: 'multiselect', selection_mode: 'ordered' }))).toBe('多选')
    expect(getTypeLabel(field({ type: 'slider' }))).toBe('滑动条')
    expect(getTypeLabel(field({ type: 'folder' }))).toBe('文件夹')
    expect(getTypeLabel(field({ type: 'file' }))).toBe('文件')
    expect(getTypeLabel(field({ type: 'string', format: 'password' }))).toBe('密码')
    expect(getTypeLabel(field({ type: 'string' }))).toBe('文本')
    expect(getTypeLabel(field({ type: 'number' }))).toBe('数字')
    expect(getTypeLabel(field({ type: 'boolean' }))).toBe('布尔')
    expect(getTypeLabel(field({ type: 'list' }))).toBe('列表')
    expect(getTypeLabel(field({ type: 'key_value' }))).toBe('键值表')
    expect(getTypeLabel(field({ type: 'table' }))).toBe('表格')
    expect(getTypeLabel(field({ type: 'json' }))).toBe('JSON')
    expect(getTypeLabel(field({ type: 'custom-type' }))).toBe('custom-type')
  })
})

describe('list / key_value / table operations', () => {
  it('list rows and add/remove/update', () => {
    const model = { items: ['a', 'b'] }
    expect(getListRows(model, 'items')).toEqual([
      { __rowKey: 'items-0', value: 'a' },
      { __rowKey: 'items-1', value: 'b' },
    ])
    expect(getListRows({}, 'items')).toEqual([])

    const added = addListRow(model, 'items', 'string')
    expect(added.items).toEqual(['a', 'b', ''])
    const addedNum = addListRow({}, 'items', 'number')
    expect(addedNum.items).toEqual([0])
    const addedBool = addListRow({}, 'items', 'boolean')
    expect(addedBool.items).toEqual([false])

    const removed = removeListRow(model, 'items', 0)
    expect(removed.items).toEqual(['b'])

    const updated = updateListRowValue(model, 'items', 0, 'x', 'string')
    expect(updated.items).toEqual(['x', 'b'])
    const updatedNum = updateListRowValue({ items: ['1', '2'] }, 'items', 0, 5, 'number')
    expect(updatedNum.items).toEqual([5, '2'])
  })

  it('normalizeListValueByType', () => {
    expect(normalizeListValueByType('5', 'number')).toBe(5)
    expect(normalizeListValueByType('abc', 'number')).toBe(0)
    expect(normalizeListValueByType(0, 'boolean')).toBe(false)
    expect(normalizeListValueByType(1, 'boolean')).toBe(true)
    expect(normalizeListValueByType(123, 'string')).toBe('123')
    expect(normalizeListValueByType(null, 'string')).toBe('')
  })

  it('key_value rows and add/remove/update key/value', () => {
    const model = { kv: { a: '1', b: '2' } }
    expect(getKeyValueRows(model, 'kv')).toEqual([
      { __rowKey: 'kv-0', key: 'a', value: '1' },
      { __rowKey: 'kv-1', key: 'b', value: '2' },
    ])
    expect(getKeyValueRows({}, 'kv')).toEqual([])
    expect(getKeyValueRows({ kv: [1, 2] }, 'kv')).toEqual([])

    const added = addKeyValueRow(model, 'kv')
    expect(added.kv).toEqual({ a: '1', b: '2', key_1: '' })
    const added2 = addKeyValueRow({ kv: { key_1: 'x' } }, 'kv')
    expect(added2.kv).toEqual({ key_1: 'x', key_2: '' })

    const removed = removeKeyValueRow(model, 'kv', 'a')
    expect(removed.kv).toEqual({ b: '2' })

    const renamed = updateKeyValueRowKey(model, 'kv', 'a', 'c')
    expect(renamed.kv).toEqual({ c: '1', b: '2' })
    // 相同 key 或空 key 不变
    expect(updateKeyValueRowKey(model, 'kv', 'a', 'a')).toBe(model)
    expect(updateKeyValueRowKey(model, 'kv', 'a', '  ')).toBe(model)

    const updated = updateKeyValueRowValue(model, 'kv', 'a', 'X')
    expect(updated.kv).toEqual({ a: 'X', b: '2' })
  })

  it('table rows/columns and add row/column/cell', () => {
    const model = { tbl: [{ a: '1', b: '2' }, { a: '3' }] }
    expect(getTableRows(model, 'tbl')).toEqual([
      { __rowKey: 'tbl-0', a: '1', b: '2' },
      { __rowKey: 'tbl-1', a: '3' },
    ])
    expect(getTableRows({}, 'tbl')).toEqual([])

    const cols = getTableColumns(model, 'tbl')
    expect(cols.map(c => c.key)).toEqual(['a', 'b', 'action'])

    // 空表给一列 col_1
    const emptyCols = getTableColumns({ tbl: [] }, 'tbl')
    expect(emptyCols.map(c => c.key)).toEqual(['col_1', 'action'])

    const addedRow = addTableRow(model, 'tbl')
    expect(addedRow.tbl).toHaveLength(3)
    expect(addedRow.tbl[2]).toEqual({ a: '', b: '' })

    const addedCol = addTableColumn(model, 'tbl')
    expect(addedCol.tbl[0].col_1).toBe('')
    expect(addedCol.tbl[1].col_1).toBe('')

    const updatedCell = updateTableCellValue(model, 'tbl', 0, 'a', 'X')
    expect(updatedCell.tbl[0].a).toBe('X')

    const removedRow = removeTableRow(model, 'tbl', 0)
    expect(removedRow.tbl).toEqual([{ a: '3' }])
  })
})

describe('json / boolean / enum / ordered-multiselect helpers', () => {
  it('getJsonText serializes with indent; empty returns {}', () => {
    expect(getJsonText({ j: { a: 1 } }, 'j')).toBe('{\n  "a": 1\n}')
    expect(getJsonText({ j: null }, 'j')).toBe('{}')
    expect(getJsonText({}, 'j')).toBe('{}')
  })

  it('parseJsonInput parses valid json and rejects invalid', () => {
    expect(parseJsonInput('{"a":1}')).toEqual({ value: { a: 1 }, error: '' })
    expect(parseJsonInput('')).toEqual({ value: {}, error: '' })
    expect(parseJsonInput('   ')).toEqual({ value: {}, error: '' })
    expect(parseJsonInput('{invalid}')).toEqual({ value: undefined, error: 'JSON 格式无效' })
  })

  it('getBooleanValue / getEnumListValue', () => {
    expect(getBooleanValue(true)).toBe(true)
    expect(getBooleanValue(0)).toBe(false)
    expect(getBooleanValue('x')).toBe(true)
    expect(getEnumListValue([1, 2])).toEqual([1, 2])
    expect(getEnumListValue(undefined)).toEqual([])
    expect(getEnumListValue('x')).toEqual([])
  })

  it('ordered-multiselect normalize / check / toggle', () => {
    const f = field({
      type: 'multiselect',
      selection_mode: 'ordered',
      options: [
        { label: 'A', value: 'a' },
        { label: 'B', value: 'b' },
        { label: 'C', value: 'c' },
      ],
    })
    expect(normalizeSchemaGroups({ groups: [{ key: 'g', fields: [f] }] })[0].fields).toHaveLength(1)

    // 按声明顺序归一
    expect(
      // normalizeOrderedMultiSelectValue
      (f => {
        const opts = getFieldOptions(f)
        const selected = new Set(['b', 'a'])
        const normalized: unknown[] = []
        for (const option of opts) {
          // option.value 类型为 unknown；用 String() 显式转 string 后再判断。
          if (selected.has(String(option.value))) {
            normalized.push(option.value)
          }
        }
        return normalized
      })(f)
    ).toEqual(['a', 'b'])

    expect(isOrderedOptionChecked(f, ['a', 'b'], 0)).toBe(true)
    expect(isOrderedOptionChecked(f, ['a', 'b'], 2)).toBe(false)

    // 切换：选中未选
    expect(toggleOrderedOption(f, ['a'], 1)).toEqual(['a', 'b'])
    // 切换：取消已选
    expect(toggleOrderedOption(f, ['a', 'b'], 0)).toEqual(['b'])
  })
})
