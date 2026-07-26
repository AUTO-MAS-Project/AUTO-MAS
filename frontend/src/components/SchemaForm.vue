<template>
  <div class="schema-form" :class="`schema-form-${layout}`" :data-status="status">
    <div v-if="status === 'schema-error'" class="schema-form-banner schema-form-banner-error">
      <span>Schema 加载失败，无法渲染表单。</span>
    </div>
    <div v-else-if="status === 'loading'" class="schema-form-banner schema-form-banner-loading">
      <a-spin size="small" />
      <span>正在加载配置项…</span>
    </div>
    <template v-else>
      <div
        v-for="group in normalizedGroups"
        :key="group.key"
        class="schema-group"
        :class="{ 'schema-group-readonly': effectiveReadonly }"
      >
        <div v-if="showGroupTitle(group)" class="schema-group-title">
          {{ group.label || group.key }}
        </div>

        <a-form layout="vertical" :class="{ 'schema-form-grid': layout === 'plugin-grid' }">
          <a-form-item
            v-for="field in group.fields"
            :key="getFieldPath(field)"
            :label="getFieldLabel(field)"
            :required="Boolean(field.required)"
            :help="getFieldHelp(field, validationErrors[getFieldPath(field)] ?? undefined)"
            :validate-status="validationErrors[getFieldPath(field)] ? 'error' : undefined"
            :class="[
              'schema-item',
              `schema-item-${field.type}`,
              layout === 'plugin-grid' ? `schema-item-size-${getFieldLayoutSizeClass(field)}` : '',
            ]"
          >
            <div class="schema-field-head">
              <a-space size="6">
                <a-tag class="type-tag" color="processing">{{ getTypeLabel(field) }}</a-tag>
                <a-tag v-if="field.required" color="error">必填</a-tag>
                <a-tag v-if="isSensitiveField(field)" color="gold">敏感</a-tag>
                <a-tag v-if="field.readonly && !isButtonField(field)" color="default">只读</a-tag>
              </a-space>
            </div>

            <template v-if="isButtonField(field)">
              <a-button
                type="primary"
                :loading="actionLoadingId === getFieldPath(field) || status === 'action-running'"
                :disabled="effectiveReadonly || status === 'action-running'"
                @click="handleButtonClick(getFieldPath(field), field)"
              >
                {{ getActionLabel(field) }}
              </a-button>
            </template>

            <template v-else-if="isAutocompleteField(field)">
              <a-auto-complete
                :value="getAutocompleteInputValue(getFieldPath(field), field)"
                style="width: 100%"
                :options="getFieldOptions(field)"
                :disabled="effectiveReadonly || field.readonly"
                @focus="handleAutocompleteFocus(getFieldPath(field), field)"
                @blur="handleAutocompleteBlur(getFieldPath(field), field, emitUpdate)"
                @select="
                  (val: string) =>
                    handleAutocompleteSelect(getFieldPath(field), field, val, emitUpdate)
                "
                @update:value="(val: string) => handleAutocompleteInput(getFieldPath(field), val)"
              />
            </template>

            <template v-else-if="isOrderedMultiSelectField(field)">
              <div class="schema-ordered-multiselect">
                <button
                  v-for="(option, index) in getFieldOptions(field)"
                  :key="`${getFieldPath(field)}-${String(option.value)}`"
                  type="button"
                  class="schema-ordered-option"
                  :class="{
                    'schema-ordered-option-active': isOrderedOptionChecked(
                      field,
                      getFieldValue(getFieldPath(field)),
                      index
                    ),
                  }"
                  :disabled="effectiveReadonly || field.readonly"
                  @click="toggleOrderedOptionAt(field, index)"
                >
                  <span class="schema-ordered-option-index">{{ index + 1 }}</span>
                  <span class="schema-ordered-option-label">{{ option.label }}</span>
                </button>
              </div>
            </template>

            <template v-else-if="isMultiSelectField(field)">
              <a-select
                mode="multiple"
                :value="getEnumListValue(getFieldValue(getFieldPath(field)))"
                style="width: 100%"
                :options="getFieldOptions(field)"
                :disabled="effectiveReadonly || field.readonly"
                @update:value="
                  (val: unknown[]) => updateFieldValue(getFieldPath(field), val, emitUpdate)
                "
              />
            </template>

            <template v-else-if="isSelectField(field)">
              <a-select
                :value="getFieldValue(getFieldPath(field))"
                style="width: 100%"
                :options="getFieldOptions(field)"
                :disabled="effectiveReadonly || field.readonly"
                @update:value="
                  (val: unknown) => updateFieldValue(getFieldPath(field), val, emitUpdate)
                "
              />
            </template>

            <template v-else-if="isBooleanField(field)">
              <a-switch
                :checked="getBooleanValue(getFieldValue(getFieldPath(field)))"
                checked-children="是"
                un-checked-children="否"
                :disabled="effectiveReadonly || field.readonly"
                @update:checked="
                  (val: boolean) => updateFieldValue(getFieldPath(field), val, emitUpdate)
                "
              />
            </template>

            <template v-else-if="isPathField(field)">
              <div class="schema-path-field">
                <a-input
                  :value="String(getFieldValue(getFieldPath(field)) ?? '')"
                  :placeholder="getFieldPlaceholder(field)"
                  :disabled="effectiveReadonly || field.readonly"
                  @update:value="
                    (val: string) => updateFieldValue(getFieldPath(field), val, emitUpdate)
                  "
                />
                <a-button
                  v-if="hasElectronPathPicker()"
                  :disabled="effectiveReadonly || field.readonly"
                  @click="pickPath(getFieldPath(field), field)"
                >
                  选择
                </a-button>
              </div>
            </template>

            <template v-else-if="isStringField(field)">
              <div v-if="isSensitiveField(field)" class="schema-sensitive-field">
                <a-input-password
                  :value="getSensitiveDraft(getFieldPath(field))"
                  :placeholder="getSensitivePlaceholder(currentModelValue, field)"
                  :maxlength="getStringMaxLength(field)"
                  :disabled="effectiveReadonly || field.readonly"
                  @update:value="(val: string) => handleSensitiveInput(getFieldPath(field), val)"
                />
                <a-button
                  v-if="!effectiveReadonly && !field.readonly"
                  size="small"
                  type="link"
                  danger
                  :disabled="!canClearSensitive(getFieldPath(field))"
                  @click="clearSensitiveDraft(getFieldPath(field))"
                >
                  {{ isSensitiveFieldCleared(currentModelValue, field) ? '已清空' : '清空原值' }}
                </a-button>
              </div>
              <a-textarea
                v-else-if="isTextareaField(field)"
                :value="String(getFieldValue(getFieldPath(field)) ?? '')"
                :placeholder="getFieldPlaceholder(field)"
                :maxlength="getStringMaxLength(field)"
                :rows="getTextareaRows(field)"
                :disabled="effectiveReadonly || field.readonly"
                @update:value="
                  (val: string) => updateFieldValue(getFieldPath(field), val, emitUpdate)
                "
              />
              <a-input
                v-else
                :value="String(getFieldValue(getFieldPath(field)) ?? '')"
                :placeholder="getFieldPlaceholder(field)"
                :maxlength="getStringMaxLength(field)"
                :disabled="effectiveReadonly || field.readonly"
                @update:value="
                  (val: string) => updateFieldValue(getFieldPath(field), val, emitUpdate)
                "
              />
            </template>

            <template v-else-if="isSliderField(field)">
              <div class="schema-slider-field">
                <a-slider
                  :value="getSliderValue(field, getFieldValue(getFieldPath(field)))"
                  :min="getNumberMin(field)"
                  :max="getNumberMax(field)"
                  :step="getNumberStep(field)"
                  :disabled="effectiveReadonly || field.readonly"
                  @update:value="
                    (val: number) => updateFieldValue(getFieldPath(field), val, emitUpdate)
                  "
                />
                <a-input-number
                  :value="getNumberValue(getFieldValue(getFieldPath(field)))"
                  class="schema-slider-number"
                  :min="getNumberMin(field)"
                  :max="getNumberMax(field)"
                  :step="getNumberStep(field)"
                  :disabled="effectiveReadonly || field.readonly"
                  @update:value="
                    (val: number | null) => updateFieldValue(getFieldPath(field), val, emitUpdate)
                  "
                />
              </div>
            </template>

            <template v-else-if="isNumberField(field)">
              <a-input-number
                :value="getNumberValue(getFieldValue(getFieldPath(field)))"
                style="width: 100%"
                :min="getNumberMin(field)"
                :max="getNumberMax(field)"
                :step="getNumberStep(field)"
                :disabled="effectiveReadonly || field.readonly"
                @update:value="
                  (val: number | null) => updateFieldValue(getFieldPath(field), val, emitUpdate)
                "
              />
            </template>

            <template v-else-if="isListField(field)">
              <a-space direction="vertical" style="width: 100%">
                <a-button
                  size="small"
                  :disabled="effectiveReadonly || field.readonly"
                  @click="
                    emitUpdate(
                      addListRow(currentModelValue, getFieldPath(field), getListItemType(field))
                    )
                  "
                >
                  新增一行
                </a-button>
                <a-table
                  :columns="listColumns"
                  :data-source="getListRows(currentModelValue, getFieldPath(field))"
                  :pagination="false"
                  size="small"
                  row-key="__rowKey"
                >
                  <template #bodyCell="{ column, record, index }">
                    <template v-if="column.key === 'value'">
                      <a-switch
                        v-if="getListItemType(field) === 'boolean'"
                        :checked="Boolean(record.value)"
                        :disabled="effectiveReadonly || field.readonly"
                        @update:checked="
                          (val: boolean) =>
                            emitUpdate(
                              updateListRowValue(
                                currentModelValue,
                                getFieldPath(field),
                                index,
                                val,
                                getListItemType(field)
                              )
                            )
                        "
                      />
                      <a-input-number
                        v-else-if="getListItemType(field) === 'number'"
                        style="width: 100%"
                        :value="
                          typeof record.value === 'number'
                            ? record.value
                            : Number(record.value || 0)
                        "
                        :disabled="effectiveReadonly || field.readonly"
                        @update:value="
                          (val: number | null) =>
                            emitUpdate(
                              updateListRowValue(
                                currentModelValue,
                                getFieldPath(field),
                                index,
                                val ?? 0,
                                getListItemType(field)
                              )
                            )
                        "
                      />
                      <a-input
                        v-else
                        :value="String(record.value ?? '')"
                        :disabled="effectiveReadonly || field.readonly"
                        @update:value="
                          (val: string) =>
                            emitUpdate(
                              updateListRowValue(
                                currentModelValue,
                                getFieldPath(field),
                                index,
                                val,
                                getListItemType(field)
                              )
                            )
                        "
                      />
                    </template>
                    <template v-else-if="column.key === 'action'">
                      <a-button
                        danger
                        size="small"
                        :disabled="effectiveReadonly || field.readonly"
                        @click="
                          emitUpdate(removeListRow(currentModelValue, getFieldPath(field), index))
                        "
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
                  :disabled="effectiveReadonly || field.readonly"
                  @click="emitUpdate(addKeyValueRow(currentModelValue, getFieldPath(field)))"
                >
                  新增一行
                </a-button>
                <a-table
                  :columns="keyValueColumns"
                  :data-source="getKeyValueRows(currentModelValue, getFieldPath(field))"
                  :pagination="false"
                  size="small"
                  row-key="__rowKey"
                >
                  <template #bodyCell="{ column, record }">
                    <template v-if="column.key === 'key'">
                      <a-input
                        :value="record.key"
                        :disabled="effectiveReadonly || field.readonly"
                        @blur="
                          (e: FocusEvent) =>
                            emitUpdate(
                              updateKeyValueRowKey(
                                currentModelValue,
                                getFieldPath(field),
                                record.key,
                                String((e.target as HTMLInputElement).value || '')
                              )
                            )
                        "
                      />
                    </template>
                    <template v-else-if="column.key === 'value'">
                      <a-input
                        :value="record.value"
                        :disabled="effectiveReadonly || field.readonly"
                        @update:value="
                          (val: string) =>
                            emitUpdate(
                              updateKeyValueRowValue(
                                currentModelValue,
                                getFieldPath(field),
                                record.key,
                                val
                              )
                            )
                        "
                      />
                    </template>
                    <template v-else-if="column.key === 'action'">
                      <a-button
                        danger
                        size="small"
                        :disabled="effectiveReadonly || field.readonly"
                        @click="
                          emitUpdate(
                            removeKeyValueRow(currentModelValue, getFieldPath(field), record.key)
                          )
                        "
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
                    :disabled="effectiveReadonly || field.readonly"
                    @click="emitUpdate(addTableRow(currentModelValue, getFieldPath(field)))"
                  >
                    新增行
                  </a-button>
                  <a-button
                    size="small"
                    :disabled="effectiveReadonly || field.readonly"
                    @click="emitUpdate(addTableColumn(currentModelValue, getFieldPath(field)))"
                  >
                    新增列
                  </a-button>
                </a-space>
                <a-table
                  :columns="getTableColumns(currentModelValue, getFieldPath(field))"
                  :data-source="getTableRows(currentModelValue, getFieldPath(field))"
                  :pagination="false"
                  size="small"
                  row-key="__rowKey"
                >
                  <template #bodyCell="{ column, record, index }">
                    <template v-if="column.key === 'action'">
                      <a-button
                        danger
                        size="small"
                        :disabled="effectiveReadonly || field.readonly"
                        @click="
                          emitUpdate(removeTableRow(currentModelValue, getFieldPath(field), index))
                        "
                      >
                        删除
                      </a-button>
                    </template>
                    <template v-else>
                      <a-input
                        :value="String(record[column.key] ?? '')"
                        :disabled="effectiveReadonly || field.readonly"
                        @update:value="
                          (val: string) =>
                            emitUpdate(
                              updateTableCellValue(
                                currentModelValue,
                                getFieldPath(field),
                                index,
                                String(column.key),
                                val
                              )
                            )
                        "
                      />
                    </template>
                  </template>
                </a-table>
              </a-space>
            </template>

            <template v-else-if="isJsonField(field)">
              <a-textarea
                :value="getJsonText(currentModelValue, getFieldPath(field))"
                :rows="getTextareaRows(field)"
                :disabled="effectiveReadonly || field.readonly"
                @blur="handleJsonBlur(getFieldPath(field), $event)"
              />
            </template>

            <template v-else>
              <a-input
                :value="String(getFieldValue(getFieldPath(field)) ?? '')"
                :placeholder="getFieldPlaceholder(field)"
                :disabled="effectiveReadonly || field.readonly"
                @update:value="
                  (val: string) => updateFieldValue(getFieldPath(field), val, emitUpdate)
                "
              />
            </template>
          </a-form-item>
        </a-form>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import type {
  SchemaDefinition,
  SchemaFieldDefinition,
  SchemaValidationErrorMap,
} from '@/types/schemaForm'
import { useSchemaFormModel } from '@/composables/useSchemaFormModel'
import {
  isSensitiveField,
  getSensitivePlaceholder,
  isSensitiveFieldCleared,
  hasSensitiveDirtyChange,
  buildSensitiveSavePatch,
  buildSchemaSavePayload,
} from '@/composables/useSensitiveFieldStrategy'
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
  isSelectField,
  isSliderField,
  isStringField,
  isTextareaField,
  normalizeSchemaGroups,
  parseJsonInput,
  removeKeyValueRow,
  removeListRow,
  removeTableRow,
  setValueByPath,
  toggleOrderedOption,
  updateKeyValueRowKey,
  updateKeyValueRowValue,
  updateListRowValue,
  updateTableCellValue,
} from '@/utils/schemaFormCore'

export type SchemaFormStatus =
  | 'idle'
  | 'loading'
  | 'schema-error'
  | 'validation-error'
  | 'save-error'
  | 'action-running'
  | 'action-failed'
  | 'readonly'
  | 'disabled'

const props = withDefaults(
  defineProps<{
    modelValue: Record<string, any>
    schema: SchemaDefinition
    readonly?: boolean
    hideFields?: string[]
    actionLoadingId?: string
    layout?: 'single' | 'plugin-grid'
    /** 表单状态：影响渲染与交互。 */
    status?: SchemaFormStatus
    /** 显式禁用所有字段（与 readonly 区别：disabled 不展示只读标签）。 */
    disabled?: boolean
  }>(),
  {
    readonly: false,
    hideFields: () => [],
    actionLoadingId: '',
    layout: 'plugin-grid',
    status: 'idle',
    disabled: false,
  }
)

const emit = defineEmits<{
  (e: 'update:modelValue', value: Record<string, any>): void
  (e: 'trigger-action', payload: { field: string; fieldSchema: SchemaFieldDefinition }): void
  (e: 'validation-change', errors: SchemaValidationErrorMap): void
  (e: 'sensitive-dirty-change', dirty: boolean): void
}>()

const listColumns = [
  { title: '值', dataIndex: 'value', key: 'value' },
  { title: '操作', dataIndex: 'action', key: 'action' },
]

const keyValueColumns = [
  { title: '键', dataIndex: 'key', key: 'key' },
  { title: '值', dataIndex: 'value', key: 'value' },
  { title: '操作', dataIndex: 'action', key: 'action' },
]

/** 实际只读状态：readonly prop 或 status=readonly/disabled。 */
const effectiveReadonly = computed(
  () =>
    props.readonly || props.status === 'readonly' || props.status === 'disabled' || props.disabled
)

/** 敏感字段草稿：DOM 中显示的值，初始为空串（不回显明文）。 */
const sensitiveDrafts = ref<Record<string, string>>({})

/** 显式清空标志：用户点击“清空原值”按钮的字段集合。 */
const sensitiveExplicitClears = ref<Set<string>>(new Set())

/** 读取敏感字段在 DOM 中应显示的草稿值。 */
const getSensitiveDraft = (field: string): string => sensitiveDrafts.value[field] ?? ''

/**
 * 用户在敏感字段中输入时：仅更新本地草稿，**不污染 modelValue**。
 *
 * 设计理由（对应 Lane 06 任务书第 3 条）：
 * - 敏感字段的 modelValue 来自后端密文解密，前端不得把未加密的草稿写回 modelValue。
 * - 保存时由父组件通过 `collectSensitiveSavePatch` 取出 patch 提交后端。
 * - 用户输入触发 dirty，但不触发即时 emit('update:modelValue')。
 */
const handleSensitiveInput = (field: string, value: string) => {
  sensitiveDrafts.value[field] = value
  // 用户重新输入时撤销“显式清空”意图（替换优先于清空）。
  if (value !== '' && sensitiveExplicitClears.value.has(field)) {
    sensitiveExplicitClears.value.delete(field)
  }
  emit('sensitive-dirty-change', hasSensitiveDirty())
}

/**
 * 用户显式点击“清空原值”：
 * - 把草稿置空；
 * - 把字段加入 explicitClears 集合，构造 patch 时写入空串 `""`（对应后端清空语义）。
 *
 * 不可清空的情况：
 * - 字段已在 modelValue 中为空（原值已经是空），点击清空无意义 → 按钮 disabled。
 */
const clearSensitiveDraft = (field: string) => {
  if (!canClearSensitive(field)) {
    return
  }
  sensitiveDrafts.value[field] = ''
  if (!sensitiveExplicitClears.value.has(field)) {
    sensitiveExplicitClears.value = new Set([...sensitiveExplicitClears.value, field])
  }
  emit('sensitive-dirty-change', hasSensitiveDirty())
}

/** 判断敏感字段当前是否可清空：只有原值非空（modelValue 中有值）时才允许清空。 */
const canClearSensitive = (field: string): boolean => {
  if (effectiveReadonly.value) {
    return false
  }
  const groups = normalizedGroups.value
  const fieldSchema = groups.flatMap(g => g.fields).find(f => getFieldPath(f) === field)
  if (!fieldSchema) {
    return false
  }
  return !isSensitiveFieldCleared(currentModelValue.value, fieldSchema)
}

/**
 * 收集敏感字段的保存 patch。
 *
 * 父组件在“保存”按钮点击时调用此方法，获取需要发送给后端的敏感字段 patch：
 * - 未触碰字段：不包含在 patch 中（后端保持原值）。
 * - 输入新值字段：patch 中含新字符串（后端加密为新密文）。
 * - 显式清空字段：patch 中含空串 `""`（后端加密为空密文）。
 *
 * 与后端契约严格对齐（见 START_SNAPSHOT.md 证据 1-3）。
 */
const collectSensitiveSavePatch = (): Record<string, any> =>
  buildSensitiveSavePatch(
    props.schema,
    { ...sensitiveDrafts.value },
    new Set(sensitiveExplicitClears.value)
  )

/**
 * 构造可直接提交的完整表单 payload。
 *
 * 原始 model 中所有敏感字段先被移除，再只合入用户明确替换/清空的 patch，
 * 避免未触碰的解密值被重新发送。
 */
const buildSavePayload = (): Record<string, any> =>
  buildSchemaSavePayload(currentModelValue.value, props.schema, collectSensitiveSavePatch())

/** 敏感字段是否存在未保存变更（用于 useUnsavedChangesGuard.isDirty）。 */
const hasSensitiveDirty = (): boolean =>
  hasSensitiveDirtyChange(
    props.schema,
    { ...sensitiveDrafts.value },
    new Set(sensitiveExplicitClears.value)
  )

/**
 * 保存成功 / 权威 reload 后调用：清空所有草稿与显式清空标志。
 *
 * 设计理由：reload 后 modelValue 已更新为新密文解密的明文，前端草稿失去意义；
 * 若不清空，下次 DOM 渲染会显示陈旧草稿。
 */
const resetSensitiveDrafts = () => {
  sensitiveDrafts.value = {}
  sensitiveExplicitClears.value = new Set()
  emit('sensitive-dirty-change', false)
}

const emitUpdate = (next: Record<string, any>) => {
  emit('update:modelValue', next)
}

const {
  normalizedGroups,
  validationErrors,
  currentModelValue,
  getFieldValue,
  showGroupTitle,
  getAutocompleteInputValue,
  handleAutocompleteInput,
  handleAutocompleteSelect,
  handleAutocompleteBlur,
  handleAutocompleteFocus,
  updateFieldValue,
  validate,
  setFieldError,
} = useSchemaFormModel({
  modelValue: () => props.modelValue,
  schema: () => props.schema,
  hideFields: () => props.hideFields,
  onValidationChange: errors => emit('validation-change', errors),
})

const hasElectronPathPicker = () => {
  if (typeof window === 'undefined') {
    return false
  }
  const electronAPI: Partial<Window['electronAPI']> | undefined = window.electronAPI
  return (
    typeof electronAPI?.selectFolder === 'function' && typeof electronAPI.selectFile === 'function'
  )
}

const pickPath = async (field: string, fieldSchema: SchemaFieldDefinition) => {
  if (!hasElectronPathPicker()) {
    return
  }
  const kind =
    fieldSchema.path_kind === 'folder' || fieldSchema.type === 'folder' ? 'folder' : 'file'
  if (kind === 'folder') {
    const selected = await window.electronAPI.selectFolder()
    if (selected) {
      updateFieldValue(field, selected, emitUpdate)
    }
    return
  }
  const selected = await window.electronAPI.selectFile(fieldSchema.filters)
  if (Array.isArray(selected) && selected[0]) {
    updateFieldValue(field, selected[0], emitUpdate)
  }
}

const handleJsonBlur = (field: string, event: FocusEvent) => {
  const value = String((event.target as HTMLTextAreaElement).value || '')
  const { value: parsed, error } = parseJsonInput(value)
  if (error) {
    setFieldError(field, error)
    return
  }
  updateFieldValue(field, parsed, emitUpdate)
}

const flushActiveField = async () => {
  if (typeof document === 'undefined') {
    return
  }
  const activeElement = document.activeElement
  if (activeElement instanceof HTMLElement) {
    activeElement.blur()
    await nextTick()
  }
}

const handleButtonClick = async (field: string, fieldSchema: SchemaFieldDefinition) => {
  await flushActiveField()
  emit('trigger-action', { field, fieldSchema })
}

/** 切换 ordered-multiselect 字段中指定索引的 option 选中状态。 */
const toggleOrderedOptionAt = (field: SchemaFieldDefinition, index: number) => {
  const path = getFieldPath(field)
  const nextValue = toggleOrderedOption(field, getFieldValue(path), index)
  const next = cloneModel(currentModelValue.value)
  setValueByPath(next, path, nextValue)
  emit('update:modelValue', next)
}

/**
 * 监听 modelValue 外部变更（如重新加载）：重置敏感字段草稿为空串，
 * 避免显示陈旧草稿；同时确保新增的敏感字段也有空草稿。
 *
 * 注意：仅在 schema 首次出现某敏感字段时初始化空草稿；
 * 已存在的草稿**不被覆盖**，避免破坏用户正在输入的内容。
 * 真正的 reload 清理由父组件显式调用 `resetSensitiveDrafts()` 完成。
 */
watch(
  () => props.modelValue,
  () => {
    const groups = normalizeSchemaGroups(props.schema, props.hideFields)
    groups.forEach(group => {
      group.fields.forEach(field => {
        if (isSensitiveField(field)) {
          const path = getFieldPath(field)
          // 仅在草稿不存在时初始化；用户正在输入时不覆盖。
          if (!(path in sensitiveDrafts.value)) {
            sensitiveDrafts.value[path] = ''
          }
        }
      })
    })
  },
  { deep: true, immediate: true }
)

defineExpose({
  validate,
  /** 暴露 collectErrors 便于外部触发静默校验。 */
  collectErrors: () => collectValidationErrors(normalizedGroups.value, currentModelValue.value),
  /**
   * 收集敏感字段的保存 patch（Lane 06 任务书第 2 条）：
   * - 未触碰字段 → 省略（保持原值）。
   * - 输入新值 → 替换。
   * - 显式清空 → 传空串 `""`。
   *
   * 父组件在“保存”按钮调用此方法获取敏感字段 patch，与非敏感字段 patch 合并后送后端。
   */
  collectSensitiveSavePatch,
  /**
   * 返回可直接提交的完整表单 payload：保留非敏感字段，省略未触碰敏感字段，
   * 仅包含显式替换或清空的敏感值。
   */
  buildSavePayload,
  /**
   * 敏感字段是否存在未保存变更。
   * 父组件用于 `useUnsavedChangesGuard.isDirty`。
   */
  hasSensitiveDirty,
  /**
   * 保存成功 / 权威 reload 后清空所有敏感字段草稿与显式清空标志。
   *
   * 必须在父组件完成 reload 后调用，否则下次渲染会显示陈旧草稿。
   */
  resetSensitiveDrafts,
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

.schema-group-readonly {
  opacity: 0.92;
}

.schema-group-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.schema-form-grid {
  display: grid;
  grid-template-columns: repeat(12, minmax(0, 1fr));
  gap: 12px;
}

.schema-form-grid .schema-item {
  min-width: 0;
}

.schema-form-grid .schema-item-size-1-4 {
  grid-column: span 3;
}

.schema-form-grid .schema-item-size-1-3 {
  grid-column: span 4;
}

.schema-form-grid .schema-item-size-1-2 {
  grid-column: span 6;
}

.schema-form-grid .schema-item-size-2-3 {
  grid-column: span 8;
}

.schema-form-grid .schema-item-size-3-4 {
  grid-column: span 9;
}

.schema-form-grid .schema-item-size-1-1 {
  grid-column: span 12;
}

/* 插件详情页（plugin-page 容器内）：iPad 设置式双栏瀑布，取代 12 列等高行网格。
   multi-column 让高矮卡片在各自列内独立纵向堆叠，矮卡下方不再随行高留白；
   卡片 inline-block + width:100% + break-inside:avoid 防止跨列断裂。
   min-width: 0px 恒真，仅表达"位于 plugin-page 容器内"这一条件本身；
   其他 SchemaForm 使用方（无 plugin-page 祖先容器）保持上方 12 列网格不变。 */
@container plugin-page (min-width: 0px) {
  .schema-form-grid {
    display: block;
    columns: 1;
    column-gap: var(--v6-space-3, 12px);
    /* 列内间距由卡片 margin-bottom 提供，末尾多出的一档用负 margin 抵消，
       保持组间节奏与原 gap 布局一致 */
    margin-block-end: calc(-1 * var(--v6-space-3, 12px));
  }

  .schema-form-grid .schema-item {
    display: inline-block;
    width: 100%;
    vertical-align: top;
    break-inside: avoid;
    margin-bottom: var(--v6-space-3, 12px);
  }
}

/* 宽容器（>980px）双栏；更窄时沿用上方单列堆叠，阈值切换只改列数，不引入过渡 */
@container plugin-page (min-width: 981px) {
  .schema-form-grid {
    columns: 2;
  }
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

.schema-path-field {
  display: flex;
  gap: 8px;
  width: 100%;
}

.schema-path-field :deep(.ant-input) {
  flex: 1 1 auto;
  min-width: 0;
}

.schema-sensitive-field {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
  width: 100%;
}

.schema-sensitive-field :deep(.ant-input-password) {
  width: 100%;
}

.schema-sensitive-field :deep(.ant-btn-link) {
  padding: 0;
  height: auto;
  font-size: 12px;
  line-height: 1.5;
}

.schema-slider-field {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 112px;
  gap: 12px;
  align-items: center;
}

.schema-slider-number {
  width: 112px;
}

.schema-ordered-multiselect {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.schema-ordered-option {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 10px;
  background: var(--ant-color-fill-quaternary);
  color: var(--ant-color-text);
  text-align: left;
  transition:
    border-color 0.2s ease,
    background-color 0.2s ease,
    transform 0.2s ease;
}

.schema-ordered-option:not(:disabled) {
  cursor: pointer;
}

.schema-ordered-option:not(:disabled):hover {
  border-color: var(--ant-color-primary-hover);
  background: var(--ant-color-fill-secondary);
  transform: translateY(-1px);
}

.schema-ordered-option:disabled {
  cursor: not-allowed;
  opacity: 0.72;
}

.schema-ordered-option-active {
  border-color: var(--ant-color-primary);
  background: color-mix(in srgb, var(--ant-color-primary-bg) 72%, white);
}

.schema-ordered-option-index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 28px;
  width: 28px;
  height: 28px;
  border-radius: 999px;
  background: var(--ant-color-bg-container);
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  font-weight: 700;
}

.schema-ordered-option-active .schema-ordered-option-index {
  background: var(--ant-color-primary);
  color: #fff;
}

.schema-ordered-option-label {
  font-weight: 600;
  line-height: 1.4;
}

.schema-form-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  border-radius: 8px;
  font-size: 14px;
}

.schema-form-banner-error {
  background: var(--ant-color-error-bg);
  color: var(--ant-color-error);
  border: 1px solid var(--ant-color-error-border);
}

.schema-form-banner-loading {
  background: var(--ant-color-fill-quaternary);
  color: var(--ant-color-text-secondary);
  border: 1px solid var(--ant-color-border-secondary);
}

@media (max-width: 960px) {
  .schema-form-grid {
    grid-template-columns: 1fr;
  }

  .schema-form-grid .schema-item {
    grid-column: 1 / -1 !important;
  }

  .schema-slider-field {
    grid-template-columns: 1fr;
  }

  .schema-slider-number {
    width: 100%;
  }
}

@media (prefers-reduced-motion: reduce) {
  .schema-ordered-option {
    transition: none;
  }

  .schema-ordered-option:not(:disabled):hover {
    transform: none;
  }
}
</style>
