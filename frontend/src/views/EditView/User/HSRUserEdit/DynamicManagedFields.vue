<template>
  <a-empty v-if="fields.length === 0" :description="t('edit.thisVersionHasNothing')" />
  <div v-else class="dynamic-fields">
    <div
      v-for="field in fields"
      :key="field.key"
      class="option-item"
      :class="{
        'option-item-boolean': field.type === 'boolean',
        'option-item-wide': field.type === 'json',
      }"
    >
      <div v-if="field.type === 'boolean'" class="boolean-control">
        <a-checkbox
          :checked="Boolean(field.value)"
          :disabled="disabled || field.readonly"
          @change="handleBooleanChange(field, $event)"
        >
          <span class="option-label">
            <span>{{ field.label }}</span>
            <a-tooltip v-if="field.description" :title="field.description">
              <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
            </a-tooltip>
          </span>
        </a-checkbox>
      </div>

      <template v-else>
        <div class="option-label">
          <span>{{ field.label }}</span>
          <a-tooltip v-if="field.description" :title="field.description">
            <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
          </a-tooltip>
        </div>
        <a-select
          v-if="field.type === 'select'"
          :value="field.value"
          :options="field.options || []"
          :disabled="disabled || field.readonly"
          class="option-control"
          @change="emitValue(field, $event)"
        />
        <a-input-number
          v-else-if="field.type === 'integer' || field.type === 'number'"
          :value="numberValue(field.value)"
          :min="field.minimum ?? undefined"
          :max="field.maximum ?? undefined"
          :precision="field.type === 'integer' ? 0 : undefined"
          :disabled="disabled || field.readonly"
          class="option-control"
          @change="emitValue(field, $event)"
        />
        <a-textarea
          v-else-if="field.type === 'json'"
          :value="draftValue(field, formatJson(field.value))"
          :auto-size="{ minRows: 3, maxRows: 10 }"
          :disabled="disabled || field.readonly"
          class="option-control monospace-input"
          @update:value="setDraft(field, $event)"
          @blur="handleJsonBlur(field, $event)"
        />
        <a-input
          v-else
          :value="draftValue(field, String(field.value ?? ''))"
          :disabled="disabled || field.readonly"
          class="option-control"
          @update:value="setDraft(field, $event)"
          @blur="handleTextBlur(field, $event)"
        />
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
import type { HSRManagedField } from '@/composables/useHSRPluginApi'

const { t } = useI18n()

const props = defineProps<{
  fields: HSRManagedField[]
  disabled: boolean
}>()

const emit = defineEmits<{
  change: [key: string, value: unknown]
}>()

// 文本与 JSON 输入只在失焦时提交，而父级每次保存都会整体重渲染受控输入。
// 未提交的内容先留在草稿里，避免重渲染用旧的 field.value 把用户输入冲掉。
const drafts = reactive<Record<string, string>>({})

const clearDrafts = () => {
  Object.keys(drafts).forEach(key => delete drafts[key])
}

watch(() => props.fields, clearDrafts)

const draftValue = (field: HSRManagedField, fallback: string) => drafts[field.key] ?? fallback

const setDraft = (field: HSRManagedField, value: string) => {
  drafts[field.key] = value
}

const clearDraft = (field: HSRManagedField) => {
  delete drafts[field.key]
}

const emitValue = (field: HSRManagedField, value: unknown) => {
  if (value === null || value === undefined) return
  emit('change', field.key, value)
}

const handleBooleanChange = (field: HSRManagedField, event: { target?: { checked?: boolean } }) => {
  emitValue(field, Boolean(event.target?.checked))
}

const numberValue = (value: unknown) => {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : undefined
}

const formatJson = (value: unknown) => JSON.stringify(value ?? null, null, 2)

const handleTextBlur = (field: HSRManagedField, event: FocusEvent) => {
  clearDraft(field)
  emitValue(field, (event.target as HTMLInputElement).value)
}

const handleJsonBlur = (field: HSRManagedField, event: FocusEvent) => {
  const raw = (event.target as HTMLTextAreaElement).value
  try {
    const parsed = JSON.parse(raw)
    clearDraft(field)
    emitValue(field, parsed)
  } catch {
    // 保留草稿，让用户在原文上继续修正而不是丢失已输入的内容
    message.error(t('edit.p0NotValidJson', { p0: field.label }))
  }
}
</script>

<style scoped>
.dynamic-fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px 20px;
}

.option-item {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.option-item-wide {
  grid-column: 1 / -1;
}

.option-label {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--ant-color-text);
  font-size: 14px;
  font-weight: 600;
}

.help-icon {
  color: var(--ant-color-text-tertiary);
  font-size: 13px;
}

.boolean-control {
  min-height: 32px;
  display: flex;
  align-items: center;
}

.option-item-boolean {
  justify-content: center;
}

.boolean-control :deep(.ant-checkbox-wrapper) {
  display: inline-flex;
  align-items: center;
}

.option-control {
  width: 100%;
}

.monospace-input {
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
}

@media (max-width: 768px) {
  .dynamic-fields {
    grid-template-columns: 1fr;
  }

  .option-item-wide {
    grid-column: auto;
  }
}
</style>
