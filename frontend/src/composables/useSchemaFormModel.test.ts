import { effectScope, ref, nextTick } from 'vue'
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import type { SchemaDefinition, SchemaFieldDefinition } from '@/types/schemaForm'
import { useSchemaFormModel } from './useSchemaFormModel'

/**
 * useSchemaFormModel 测试：响应式状态包装、校验调度、autocomplete 草稿管理。
 *
 * 这些测试不依赖 DOM，只验证 composable 的纯响应式行为。
 */

const field = (overrides: Partial<SchemaFieldDefinition> = {}): SchemaFieldDefinition => ({
  type: 'string',
  ...overrides,
})

const basicSchema: SchemaDefinition = {
  groups: [
    {
      key: 'g1',
      label: '基础',
      fields: [
        field({ key: 'name', type: 'string', label: '名称', required: true }),
        field({ key: 'age', type: 'number', min: 0, max: 200 }),
      ],
    },
    {
      key: 'g2',
      label: '高级',
      fields: [field({ key: 'tags', type: 'multiselect', options: ['a', 'b', 'c'] })],
    },
  ],
}

describe('useSchemaFormModel', () => {
  let scope: ReturnType<typeof effectScope> | null = null

  beforeEach(() => {
    scope = effectScope()
  })

  afterEach(() => {
    scope?.stop()
    scope = null
  })

  const createModel = (
    overrides: {
      modelValue?: Record<string, any>
      schema?: SchemaDefinition | null
      hideFields?: string[]
      onValidationChange?: (errors: any) => void
    } = {}
  ) => {
    const modelValue = ref<Record<string, any>>(overrides.modelValue ?? {})
    // 显式区分 undefined（使用默认 basicSchema）与 null（使用 null）
    const schema = ref<SchemaDefinition | null | undefined>(
      overrides.schema === undefined ? basicSchema : overrides.schema
    )
    const hideFields = ref<string[]>(overrides.hideFields ?? [])
    let model: ReturnType<typeof useSchemaFormModel> | null = null
    scope!.run(() => {
      model = useSchemaFormModel({
        modelValue: () => modelValue.value,
        schema: () => schema.value,
        hideFields: () => hideFields.value,
        onValidationChange: overrides.onValidationChange,
      })
    })
    return {
      modelValue,
      schema,
      hideFields,
      ...(model as unknown as ReturnType<typeof useSchemaFormModel>),
    }
  }

  describe('normalizedGroups', () => {
    it('exposes schema groups as a computed', () => {
      const { normalizedGroups } = createModel()
      expect(normalizedGroups.value).toHaveLength(2)
      expect(normalizedGroups.value[0].key).toBe('g1')
      expect(normalizedGroups.value[1].key).toBe('g2')
    })

    it('hides fields listed in hideFields', () => {
      const { normalizedGroups } = createModel({ hideFields: ['age'] })
      expect(normalizedGroups.value[0].fields.map(f => f.key)).toEqual(['name'])
    })

    it('returns empty array for null schema', () => {
      // createModel 中 schema === undefined 时回退到 basicSchema，
      // 因此显式传 null 来测试 null 的处理。
      const { normalizedGroups } = createModel({ schema: null })
      expect(normalizedGroups.value).toEqual([])
    })

    it('returns empty array for explicit undefined schema via direct call', () => {
      // 直接测试 composable 接受 undefined schema（绕过 createModel 默认值）
      let model: ReturnType<typeof useSchemaFormModel> | null = null
      scope!.run(() => {
        model = useSchemaFormModel({
          modelValue: () => ({}),
          schema: () => undefined,
          hideFields: () => [],
        })
      })
      expect((model as any).normalizedGroups.value).toEqual([])
    })

    it('reacts to schema changes', async () => {
      const { schema, normalizedGroups } = createModel()
      expect(normalizedGroups.value).toHaveLength(2)
      schema.value = { groups: [{ key: 'x', fields: [field({ key: 'a' })] }] }
      await nextTick()
      expect(normalizedGroups.value).toHaveLength(1)
      expect(normalizedGroups.value[0].key).toBe('x')
    })

    it('reacts to hideFields changes', async () => {
      const { hideFields, normalizedGroups } = createModel()
      expect(normalizedGroups.value[0].fields).toHaveLength(2)
      hideFields.value = ['name']
      await nextTick()
      expect(normalizedGroups.value[0].fields.map(f => f.key)).toEqual(['age'])
    })
  })

  describe('getFieldValue / updateFieldValue', () => {
    it('reads value by path from modelValue', () => {
      const { getFieldValue } = createModel({ modelValue: { name: 'alice', age: 30 } })
      expect(getFieldValue('name')).toBe('alice')
      expect(getFieldValue('age')).toBe(30)
      expect(getFieldValue('missing')).toBeUndefined()
    })

    it('reads nested values by dotted path', () => {
      const { getFieldValue } = createModel({
        modelValue: { Info: { Name: 'bob', Tags: ['x'] } },
      })
      expect(getFieldValue('Info.Name')).toBe('bob')
      expect(getFieldValue('Info.Tags')).toEqual(['x'])
    })

    it('updateFieldValue emits next modelValue via update callback', () => {
      const update = vi.fn()
      const { updateFieldValue } = createModel({ modelValue: { name: 'a' } })
      updateFieldValue('name', 'b', update)
      expect(update).toHaveBeenCalledTimes(1)
      const next = update.mock.calls[0][0]
      expect(next.name).toBe('b')
      // 不修改原 modelValue（深拷贝）
    })

    it('updateFieldValue writes nested path', () => {
      const update = vi.fn()
      const { updateFieldValue } = createModel({ modelValue: { Info: {} } })
      updateFieldValue('Info.Name', 'alice', update)
      const next = update.mock.calls[0][0]
      expect(next.Info.Name).toBe('alice')
    })
  })

  describe('showGroupTitle', () => {
    it('shows title for non-default group with label when multiple groups', () => {
      const { showGroupTitle, normalizedGroups } = createModel()
      expect(showGroupTitle(normalizedGroups.value[0])).toBe(true) // 'g1' + label '基础'
      expect(showGroupTitle(normalizedGroups.value[1])).toBe(true) // 'g2' + label '高级'
    })

    it('hides title for default group with empty label', () => {
      const { showGroupTitle, normalizedGroups } = createModel({
        schema: {
          groups: [
            { key: 'default', label: '', fields: [field({ key: 'a' })] },
            { key: 'g1', label: 'L', fields: [field({ key: 'b' })] },
          ],
        },
      })
      expect(showGroupTitle(normalizedGroups.value[0])).toBe(false)
      expect(showGroupTitle(normalizedGroups.value[1])).toBe(true)
    })

    it('hides title when only one group exists', () => {
      const { showGroupTitle, normalizedGroups } = createModel({
        schema: { groups: [{ key: 'g1', label: 'L', fields: [field({ key: 'a' })] }] },
      })
      expect(showGroupTitle(normalizedGroups.value[0])).toBe(false)
    })
  })

  describe('validate', () => {
    it('collects errors for invalid required fields and returns valid=false', () => {
      const onValidationChange = vi.fn()
      const { validate } = createModel({
        modelValue: { name: '', age: 5 },
        onValidationChange,
      })
      const result = validate()
      expect(result.valid).toBe(false)
      expect(result.errors.name).toBe('该字段为必填项')
      expect(result.errors.age).toBeUndefined() // age=5 within [0,200]
      expect(onValidationChange).toHaveBeenCalledWith(result.errors)
    })

    it('returns valid=true when all fields pass', () => {
      const { validate } = createModel({ modelValue: { name: 'alice', age: 30 } })
      const result = validate()
      expect(result.valid).toBe(true)
      expect(Object.keys(result.errors)).toHaveLength(0)
    })

    it('exposes validationErrors ref after validate', () => {
      // composable 在 watch immediate: true 时会自动 collectErrors 一次，
      // 因此初始 validationErrors 已包含 name 字段错误。
      const { validate, validationErrors } = createModel({ modelValue: { name: '' } })
      expect(validationErrors.value.name).toBe('该字段为必填项')
      // 再次调用 validate 不会改变内容，但会触发 onValidationChange
      const result = validate()
      expect(result.valid).toBe(false)
      expect(validationErrors.value.name).toBe('该字段为必填项')
    })

    it('handles nested path validation', () => {
      const schema: SchemaDefinition = {
        groups: [
          {
            key: 'g1',
            fields: [field({ key: 'Info.Name', type: 'string', required: true })],
          },
        ],
      }
      const { validate } = createModel({ modelValue: { Info: {} }, schema })
      const result = validate()
      expect(result.valid).toBe(false)
      expect(result.errors['Info.Name']).toBe('该字段为必填项')
    })
  })

  describe('setFieldError', () => {
    it('sets an explicit error and emits validation-change', () => {
      const onValidationChange = vi.fn()
      const { setFieldError, validationErrors } = createModel({
        modelValue: { name: 'a' },
        onValidationChange,
      })
      setFieldError('json_field', 'JSON 格式无效')
      expect(validationErrors.value.json_field).toBe('JSON 格式无效')
      expect(onValidationChange).toHaveBeenCalledWith(validationErrors.value)
    })

    it('preserves existing errors when adding new one', () => {
      const { validate, setFieldError, validationErrors } = createModel({
        modelValue: { name: '' },
      })
      validate()
      expect(validationErrors.value.name).toBe('该字段为必填项')
      setFieldError('age', '自定义错误')
      expect(validationErrors.value.name).toBe('该字段为必填项')
      expect(validationErrors.value.age).toBe('自定义错误')
    })
  })

  describe('autocomplete drafts', () => {
    const autocompleteField = field({
      key: 'city',
      type: 'string',
      allow_custom: true,
      options: [
        { label: '北京', value: 'bj' },
        { label: '上海', value: 'sh' },
      ],
    })
    const autocompleteSchema: SchemaDefinition = {
      groups: [{ key: 'g', fields: [autocompleteField] }],
    }

    it('syncAutocompleteDraft initializes draft to current value label', () => {
      const { syncAutocompleteDraft, getAutocompleteInputValue } = createModel({
        modelValue: { city: 'bj' },
        schema: autocompleteSchema,
      })
      syncAutocompleteDraft('city', autocompleteField)
      expect(getAutocompleteInputValue('city', autocompleteField)).toBe('北京')
    })

    it('handleAutocompleteInput updates draft only (not modelValue)', () => {
      const { handleAutocompleteInput, getAutocompleteInputValue } = createModel({
        modelValue: { city: 'bj' },
        schema: autocompleteSchema,
      })
      handleAutocompleteInput('city', '北')
      expect(getAutocompleteInputValue('city', autocompleteField)).toBe('北')
    })

    it('handleAutocompleteSelect updates draft and modelValue via update callback', () => {
      const update = vi.fn()
      const { handleAutocompleteSelect, getAutocompleteInputValue } = createModel({
        modelValue: { city: 'bj' },
        schema: autocompleteSchema,
      })
      handleAutocompleteSelect('city', autocompleteField, 'sh', update)
      expect(update).toHaveBeenCalledTimes(1)
      expect(update.mock.calls[0][0].city).toBe('sh')
      expect(getAutocompleteInputValue('city', autocompleteField)).toBe('上海')
    })

    it('handleAutocompleteBlur resolves draft back to value via label match', () => {
      const update = vi.fn()
      const { handleAutocompleteInput, handleAutocompleteBlur } = createModel({
        modelValue: { city: 'bj' },
        schema: autocompleteSchema,
      })
      handleAutocompleteInput('city', '上海')
      handleAutocompleteBlur('city', autocompleteField, update)
      expect(update).toHaveBeenCalledTimes(1)
      expect(update.mock.calls[0][0].city).toBe('sh')
    })

    it('handleAutocompleteBlur with empty draft clears value', () => {
      const update = vi.fn()
      const { handleAutocompleteInput, handleAutocompleteBlur } = createModel({
        modelValue: { city: 'bj' },
        schema: autocompleteSchema,
      })
      handleAutocompleteInput('city', '   ')
      handleAutocompleteBlur('city', autocompleteField, update)
      expect(update).toHaveBeenCalledTimes(1)
      expect(update.mock.calls[0][0].city).toBe('')
    })

    it('handleAutocompleteBlur with non-matching draft keeps literal value', () => {
      const update = vi.fn()
      const { handleAutocompleteInput, handleAutocompleteBlur } = createModel({
        modelValue: { city: 'bj' },
        schema: autocompleteSchema,
      })
      handleAutocompleteInput('city', '深圳')
      handleAutocompleteBlur('city', autocompleteField, update)
      expect(update.mock.calls[0][0].city).toBe('深圳')
    })

    it('handleAutocompleteFocus syncs draft to current value', () => {
      const { handleAutocompleteFocus, getAutocompleteInputValue } = createModel({
        modelValue: { city: 'sh' },
        schema: autocompleteSchema,
      })
      handleAutocompleteFocus('city', autocompleteField)
      expect(getAutocompleteInputValue('city', autocompleteField)).toBe('上海')
    })
  })

  describe('collectErrors (silent validation)', () => {
    it('returns errors without mutating validationErrors ref or emitting beyond initial watch', () => {
      const onValidationChange = vi.fn()
      const { collectErrors } = createModel({
        modelValue: { name: '' },
        onValidationChange,
      })
      // composable 初始化时 watch immediate: true 已调用 collectErrors 一次并触发 emit
      const initialCallCount = onValidationChange.mock.calls.length
      const errors = collectErrors()
      expect(errors.name).toBe('该字段为必填项')
      // collectErrors 本身不写 ref，不触发 emit
      expect(onValidationChange.mock.calls.length).toBe(initialCallCount)
    })
  })

  describe('currentModelValue', () => {
    it('returns empty object for nullish modelValue', () => {
      const { currentModelValue } = createModel({ modelValue: null as any })
      expect(currentModelValue.value).toEqual({})
    })

    it('reacts to modelValue changes', async () => {
      const { modelValue, currentModelValue } = createModel({ modelValue: { a: 1 } })
      expect(currentModelValue.value.a).toBe(1)
      modelValue.value = { a: 2 }
      await nextTick()
      expect(currentModelValue.value.a).toBe(2)
    })
  })
})
