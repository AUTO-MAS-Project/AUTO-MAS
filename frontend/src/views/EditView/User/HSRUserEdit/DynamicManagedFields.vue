<template>
  <div class="dynamic-fields">
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
        <!-- 标记与恢复放在复选框外面，点它们不会顺带切换勾选 -->
        <span v-if="isFieldOverridden(field)" class="override-actions">
          <a-tooltip :title="overrideTooltip(field)">
            <a-tag color="blue" class="override-tag">{{ t('edit.hsrFieldOverridden') }}</a-tag>
          </a-tooltip>
          <a-button
            v-if="canResetField(field)"
            type="link"
            size="small"
            class="reset-link"
            :disabled="disabled"
            @click="emit('reset', field.key)"
          >
            {{ t('edit.hsrFieldReset') }}
          </a-button>
        </span>
      </div>

      <template v-else>
        <div class="option-label">
          <span>{{ field.label }}</span>
          <a-tooltip v-if="field.description" :title="field.description">
            <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
          </a-tooltip>
          <template v-if="isFieldOverridden(field)">
            <a-tooltip :title="overrideTooltip(field)">
              <a-tag color="blue" class="override-tag">{{ t('edit.hsrFieldOverridden') }}</a-tag>
            </a-tooltip>
            <a-button
              v-if="canResetField(field)"
              type="link"
              size="small"
              class="reset-link"
              :disabled="disabled"
              @click="emit('reset', field.key)"
            >
              {{ t('edit.hsrFieldReset') }}
            </a-button>
          </template>
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
        <ManagedListField
          v-else-if="isRowListField(field)"
          :field-key="field.key"
          :value="field.value"
          :disabled="disabled || Boolean(field.readonly)"
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
import ManagedListField from './ManagedListField.vue'
import {
  canResetField,
  formatManagedValue,
  isFieldOverridden,
  isRowListField,
} from './managedFields'

const { t } = useI18n()

const props = defineProps<{
  fields: HSRManagedField[]
  disabled: boolean
}>()

const emit = defineEmits<{
  change: [key: string, value: unknown]
  /** 删掉该键在 MAS 里的覆盖值，回到三月七 / SRA 里的设置。 */
  reset: [key: string]
}>()

// 文本与 JSON 输入只在失焦时提交，而父级每次保存都会整体重渲染受控输入。
// 未提交的内容先留在草稿里，避免重渲染用旧的 field.value 把用户输入冲掉。
const drafts = reactive<Record<string, string>>({})

// 字段离开本列表（换模块、换引擎、被显示条件隐藏）时丢掉它的草稿。不按数组身份清：
// 分组数组在相邻字段保存、显示条件变化时都会重算成新数组，那样会把正在输入的内容冲掉。
watch(
  () => props.fields.map(field => field.key).join('\n'),
  joined => {
    const keys = new Set(joined.split('\n'))
    Object.keys(drafts).forEach(key => {
      if (!keys.has(key)) delete drafts[key]
    })
  }
)

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

// 有原值才挂提示；没有原值时「已改」标签自己就说明白了
const overrideTooltip = (field: HSRManagedField) =>
  field.native_value === undefined
    ? undefined
    : t('edit.hsrFieldNativeValue', {
        value: formatManagedValue(field, field.native_value, {
          on: t('edit.hsrValueOn'),
          off: t('edit.hsrValueOff'),
          empty: t('edit.hsrValueEmpty'),
        }),
      })

const handleTextBlur = (field: HSRManagedField, event: FocusEvent) => {
  const value = (event.target as HTMLInputElement).value
  clearDraft(field)
  // 没改动的失焦不提交，免得点一下就把原值存成覆盖
  if (value === String(field.value ?? '')) return
  emitValue(field, value)
}

const handleJsonBlur = (field: HSRManagedField, event: FocusEvent) => {
  const raw = (event.target as HTMLTextAreaElement).value
  try {
    const parsed = JSON.parse(raw)
    clearDraft(field)
    if (JSON.stringify(parsed) === JSON.stringify(field.value ?? null)) return
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
  flex-wrap: wrap;
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
  flex-wrap: wrap;
  gap: 4px;
}

.option-item-boolean {
  justify-content: center;
}

.boolean-control :deep(.ant-checkbox-wrapper) {
  display: inline-flex;
  align-items: center;
}

.override-actions {
  display: inline-flex;
  align-items: center;
  gap: 2px;
}

.override-tag {
  margin-inline-end: 0;
  font-size: 12px;
  font-weight: 400;
  line-height: 18px;
  cursor: default;
}

.reset-link {
  height: auto;
  padding: 0 4px;
  font-size: 12px;
  font-weight: 400;
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
