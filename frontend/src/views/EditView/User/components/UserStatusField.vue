<template>
  <a-form-item>
    <template #label>
      <FieldLabelWithHint
        :text="t('core.edit.enabled')"
        :hint="hint ?? t('core.edit.whetherThisUserEnabled')"
        variant="form"
      />
    </template>
    <a-select
      :value="value ? 'enabled' : 'disabled'"
      :disabled="disabled"
      :placeholder="placeholder"
      size="large"
      style="width: 100%"
      @change="handleChange"
    >
      <a-select-option value="enabled">{{ t('core.edit.yes') }}</a-select-option>
      <a-select-option value="disabled">{{ t('core.edit.no') }}</a-select-option>
    </a-select>
  </a-form-item>
</template>
<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import FieldLabelWithHint from '@/components/FieldLabelWithHint.vue'
defineProps<{ hint?: string; placeholder?: string; disabled?: boolean }>()
const value = defineModel<boolean>({ required: true })
const emit = defineEmits<{ save: [value: boolean] }>()

const { t } = useI18n()

// Select 的值只支持字符串/数字，对外仍保留布尔状态契约。
const handleChange = (selected: string) => {
  const enabled = selected === 'enabled'
  value.value = enabled
  emit('save', enabled)
}
</script>
