<template>
  <a-form-item>
    <template #label>
      <FieldLabelWithHint
        :text="t('core.edit.emulator')"
        :hint="t('core.edit.pickEmulatorUse')"
        variant="form"
      />
    </template>
    <a-select
      v-model:value="value"
      size="large"
      :placeholder="t('core.edit.pickEmulator')"
      :loading="loading"
      @change="emit('change', $event)"
    >
      <a-select-option v-for="item in options" :key="item.value" :value="item.value">
        {{ item.label }}
      </a-select-option>
    </a-select>
  </a-form-item>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import FieldLabelWithHint from '@/components/FieldLabelWithHint.vue'
import type { ComboBoxItem } from '@/api'
defineProps<{ options: ComboBoxItem[]; loading: boolean }>()
const value = defineModel<string | null>({ required: true })
const emit = defineEmits<{ change: [value: string] }>()
const { t } = useI18n()
</script>
