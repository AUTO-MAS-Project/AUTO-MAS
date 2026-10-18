<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
import type { NotifyChannelFieldOut } from '@/api/models/NotifyChannelFieldOut'
import { normalizeControl } from '../notifyChannelView'

const props = withDefaults(
  defineProps<{
    field: NotifyChannelFieldOut
    value: unknown
    disabled?: boolean
    /** 单行布局：标签在左、控件在右；开关项恒为单行，其余控件默认标签在上 */
    inline?: boolean
    /** 提示浮层容器；通知配置弹窗场景传其 wrap 节点，让浮层压在标题栏之下 */
    getPopupContainer?: () => HTMLElement
  }>(),
  { disabled: false, inline: false, getPopupContainer: undefined }
)

const emit = defineEmits<{ save: [value: unknown] }>()

const { t } = useI18n()

const control = computed(() => normalizeControl(props.field.control))
const inline = computed(() => props.inline || control.value === 'bool')
const placeholder = computed(() =>
  props.field.placeholderKey ? t(props.field.placeholderKey) : undefined
)
const selectOptions = computed(() =>
  (props.field.options ?? []).map(option => ({
    value: option.value,
    label: t(option.labelKey),
  }))
)

const onInputSave = (event: FocusEvent) => {
  const target = event.target as HTMLInputElement | HTMLTextAreaElement | null
  if (target) emit('save', target.value)
}
</script>

<template>
  <div class="field-item" :class="{ inline }">
    <div class="field-label-wrapper">
      <span class="field-label">{{ t(field.labelKey) }}</span>
      <a-tooltip
        v-if="field.tipKey"
        :title="t(field.tipKey)"
        :get-popup-container="getPopupContainer"
      >
        <QuestionCircleOutlined class="help-icon" />
      </a-tooltip>
    </div>

    <a-switch
      v-if="control === 'bool'"
      :checked="value === true"
      :disabled="disabled"
      @change="(checked: boolean | string | number) => emit('save', Boolean(checked))"
    />
    <a-select
      v-else-if="control === 'select'"
      :value="(value as string | undefined) ?? undefined"
      :options="selectOptions"
      :disabled="disabled"
      :placeholder="placeholder"
      size="large"
      @change="(next: unknown) => emit('save', next)"
    />
    <a-textarea
      v-else-if="control === 'json'"
      :value="(value as string | undefined) ?? ''"
      :disabled="disabled"
      :placeholder="placeholder"
      :rows="4"
      @blur="onInputSave"
    />
    <a-input-password
      v-else-if="control === 'password'"
      :value="(value as string | undefined) ?? ''"
      :disabled="disabled"
      :placeholder="placeholder"
      size="large"
      autocomplete="new-password"
      @blur="onInputSave"
    />
    <a-input
      v-else
      :value="(value as string | undefined) ?? ''"
      :disabled="disabled"
      :placeholder="placeholder"
      size="large"
      @blur="onInputSave"
    />
  </div>
</template>

<style scoped>
.field-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* 单行形态：标签在左、控件在右；控件占满剩余宽度，开关只占自身宽度 */
.field-item.inline {
  flex-direction: row;
  align-items: center;
}

.field-item.inline > :deep(.ant-select),
.field-item.inline > :deep(.ant-input-affix-wrapper),
.field-item.inline > :deep(.ant-input),
.field-item.inline > :deep(.ant-input-number) {
  flex: 0 0 auto;
  width: 180px;
}

.field-label-wrapper {
  display: flex;
  align-items: center;
  gap: 8px;
}

.field-label {
  font-weight: 600;
  color: var(--ant-color-text);
  font-size: 14px;
}

.help-icon {
  color: #8c8c8c;
  font-size: 14px;
}
</style>
