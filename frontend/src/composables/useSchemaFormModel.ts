/**
 * SchemaForm 响应式模型包装。
 *
 * 在 `@/utils/schemaFormCore` 纯逻辑之上提供 Vue 响应式状态、emit 集成、
 * 校验调度和 status 暴露。SchemaForm.vue 通过本 composable 与核心逻辑交互，
 * 自身只负责模板渲染，从而显著降低体积（任务书 Lane 06 目标 1）。
 *
 * 设计原则：
 * - 不引入新依赖；保留 SchemaForm.vue 原有的全部 schema 类型与行为。
 * - 所有派生状态（normalizedGroups、validationErrors）通过 computed 暴露，
 *   避免在模板中堆积业务表达式。
 * - status prop 在 SchemaForm.vue 中定义；本 composable 仅暴露只读派生状态。
 */

import { computed, ref, watch } from 'vue'
import type {
  SchemaDefinition,
  SchemaFieldDefinition,
  SchemaGroupDefinition,
  SchemaValidationErrorMap,
} from '@/types/schemaForm'
import {
  cloneModel,
  collectValidationErrors,
  getFieldPath,
  getOptionLabelByValue,
  getOptionValueByLabel,
  getValueByPath,
  normalizeSchemaGroups,
  setValueByPath,
  showGroupTitle as showGroupTitleCore,
} from '@/utils/schemaFormCore'

export interface UseSchemaFormModelOptions {
  /** 当前 modelValue（来自 props，只读）。 */
  modelValue: () => Record<string, any>
  /** 当前 schema（来自 props，只读）。 */
  schema: () => SchemaDefinition | null | undefined
  /** 当前 hideFields（来自 props，只读）。 */
  hideFields: () => string[]
  /** 校验错误变更回调（用于 emit validation-change）。 */
  onValidationChange?: (errors: SchemaValidationErrorMap) => void
}

/**
 * 把 schema + hideFields 归一为可见分组数组。
 *
 * 通过 computed 包装，仅在 schema/hideFields 变更时重新计算。
 */
export const useSchemaFormModel = (options: UseSchemaFormModelOptions) => {
  const { modelValue, schema, hideFields, onValidationChange } = options

  /** 归一化后的可见分组（响应式）。 */
  const normalizedGroups = computed<SchemaGroupDefinition[]>(() =>
    normalizeSchemaGroups(schema(), hideFields())
  )

  /** 当前校验错误映射。 */
  const validationErrors = ref<SchemaValidationErrorMap>({})

  /** autocomplete 字段的草稿（label 文本），仅在用户输入时维护。 */
  const autocompleteDrafts = ref<Record<string, string>>({})

  /** 当前 modelValue 的快照（响应式读取，便于核心函数纯调用）。 */
  const currentModelValue = computed<Record<string, any>>(() => modelValue() || {})

  /** 按字段路径取值。 */
  const getFieldValue = (field: string): unknown => getValueByPath(currentModelValue.value, field)

  /** 是否显示组标题。 */
  const showGroupTitle = (group: SchemaGroupDefinition): boolean =>
    showGroupTitleCore(normalizedGroups.value, group)

  /** 同步 autocomplete 草稿为当前字段值的 label 形式。 */
  const syncAutocompleteDraft = (field: string, fieldSchema: SchemaFieldDefinition) => {
    const rawValue = getFieldValue(field)
    autocompleteDrafts.value[field] =
      getOptionLabelByValue(fieldSchema, rawValue) ?? String(rawValue ?? '')
  }

  /** 读取 autocomplete 在 DOM 中应显示的值。 */
  const getAutocompleteInputValue = (field: string, fieldSchema: SchemaFieldDefinition): string => {
    const current = autocompleteDrafts.value[field]
    if (typeof current === 'string') {
      return current
    }
    const rawValue = getFieldValue(field)
    return getOptionLabelByValue(fieldSchema, rawValue) ?? String(rawValue ?? '')
  }

  /** 用户在 autocomplete 中输入时更新草稿。 */
  const handleAutocompleteInput = (field: string, value: string) => {
    autocompleteDrafts.value[field] = value
  }

  /** 用户在 autocomplete 中选中某项时更新 modelValue 与草稿。 */
  const handleAutocompleteSelect = (
    field: string,
    fieldSchema: SchemaFieldDefinition,
    value: string,
    update: (next: Record<string, any>) => void
  ) => {
    const matchedLabel = getOptionLabelByValue(fieldSchema, value)
    autocompleteDrafts.value[field] = matchedLabel ?? value
    const next = cloneModel(currentModelValue.value)
    setValueByPath(next, field, value)
    update(next)
  }

  /** autocomplete 失焦时把草稿解析回 value；解析失败按字面值保存。 */
  const handleAutocompleteBlur = (
    field: string,
    fieldSchema: SchemaFieldDefinition,
    update: (next: Record<string, any>) => void
  ) => {
    const draftValue = autocompleteDrafts.value[field]
    if (typeof draftValue !== 'string') {
      syncAutocompleteDraft(field, fieldSchema)
      return
    }

    const trimmedValue = draftValue.trim()
    if (!trimmedValue) {
      const next = cloneModel(currentModelValue.value)
      setValueByPath(next, field, '')
      update(next)
      autocompleteDrafts.value[field] = ''
      return
    }

    const matchedByLabel = getOptionValueByLabel(fieldSchema, trimmedValue)
    if (matchedByLabel !== undefined) {
      const next = cloneModel(currentModelValue.value)
      setValueByPath(next, field, matchedByLabel)
      update(next)
      autocompleteDrafts.value[field] =
        getOptionLabelByValue(fieldSchema, matchedByLabel) ?? trimmedValue
      return
    }

    const matchedByValueLabel = getOptionLabelByValue(fieldSchema, trimmedValue)
    if (matchedByValueLabel !== undefined) {
      const next = cloneModel(currentModelValue.value)
      setValueByPath(next, field, trimmedValue)
      update(next)
      autocompleteDrafts.value[field] = matchedByValueLabel
      return
    }

    const next = cloneModel(currentModelValue.value)
    setValueByPath(next, field, trimmedValue)
    update(next)
    autocompleteDrafts.value[field] = trimmedValue
  }

  const handleAutocompleteFocus = (field: string, fieldSchema: SchemaFieldDefinition) => {
    syncAutocompleteDraft(field, fieldSchema)
  }

  /** 更新字段值并 emit 新 modelValue。 */
  const updateFieldValue = (
    field: string,
    value: unknown,
    update: (next: Record<string, any>) => void
  ) => {
    const next = cloneModel(currentModelValue.value)
    setValueByPath(next, field, value)
    update(next)
  }

  /** 收集当前 schema 与 modelValue 的所有校验错误。 */
  const collectErrors = (): SchemaValidationErrorMap =>
    collectValidationErrors(normalizedGroups.value, currentModelValue.value)

  /** 触发完整校验；返回 { valid, errors }，并 emit validation-change。 */
  const validate = (): { valid: boolean; errors: SchemaValidationErrorMap } => {
    const errors = collectErrors()
    validationErrors.value = errors
    onValidationChange?.(errors)
    return {
      valid: Object.keys(errors).length === 0,
      errors,
    }
  }

  /** 显式设置校验错误（用于 JSON 解析失败等场景）。 */
  const setFieldError = (field: string, error: string) => {
    validationErrors.value = {
      ...validationErrors.value,
      [field]: error,
    }
    onValidationChange?.(validationErrors.value)
  }

  /** 监听 modelValue/schema 变化，自动重算校验并同步 autocomplete 草稿。 */
  watch(
    () => [currentModelValue.value, schema(), hideFields()] as const,
    () => {
      normalizedGroups.value.forEach(group => {
        group.fields.forEach(field => {
          // 仅对 autocomplete 字段同步草稿；其余字段不需要维护草稿。
          if (field.allow_custom && Array.isArray(field.options) && field.options.length > 0) {
            syncAutocompleteDraft(getFieldPath(field), field)
          }
        })
      })
      validationErrors.value = collectErrors()
      onValidationChange?.(validationErrors.value)
    },
    { deep: true, immediate: true }
  )

  return {
    normalizedGroups,
    validationErrors,
    autocompleteDrafts,
    currentModelValue,
    getFieldValue,
    showGroupTitle,
    syncAutocompleteDraft,
    getAutocompleteInputValue,
    handleAutocompleteInput,
    handleAutocompleteSelect,
    handleAutocompleteBlur,
    handleAutocompleteFocus,
    updateFieldValue,
    collectErrors,
    validate,
    setFieldError,
  }
}
