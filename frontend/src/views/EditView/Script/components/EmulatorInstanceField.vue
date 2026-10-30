<template>
  <a-form-item>
    <template #label>
      <FieldLabelWithHint
        :text="t('core.edit.emulatorInstance')"
        :hint="
          options.length === 0 && !loading
            ? t('core.edit.thisEmulatorCannotBe')
            : t('core.edit.pickEmulatorInstance')
        "
        variant="form"
      />
    </template>
    <!-- 当API返回空列表时显示输入框 -->
    <a-input
      v-if="options.length === 0 && !loading && emulatorId"
      v-model:value="value"
      size="large"
      :placeholder="t('core.edit.enterInstanceInfoAs')"
      class="modern-input"
      @blur="emit('save', value)"
    />
    <!-- 正常情况下显示下拉框 -->
    <a-select
      v-else
      v-model:value="value"
      size="large"
      :placeholder="t('core.edit.pickEmulatorFirst')"
      :loading="loading"
      :disabled="!emulatorId"
      @change="emit('save', $event)"
    >
      <a-select-option
        v-for="item in options"
        :key="item.value"
        :value="item.value"
        :disabled="item.disabled"
      >
        {{ item.label }}
      </a-select-option>
    </a-select>
  </a-form-item>
</template>

<script setup lang="ts">
import FieldLabelWithHint from '@/components/FieldLabelWithHint.vue'
import { useI18n } from 'vue-i18n'
import type { EmulatorDeviceOption } from '@/composables/useEmulatorDeviceOptions'
defineProps<{ emulatorId: string | null; options: EmulatorDeviceOption[]; loading: boolean }>()
const value = defineModel<string | null>({ required: true })
const emit = defineEmits<{ save: [value: string | null] }>()
const { t } = useI18n()
</script>

<style scoped>
.modern-input {
  border-radius: 8px;
  border: 2px solid var(--ant-color-border);
  background: var(--ant-color-bg-container);
  transition: all 0.3s ease;
}

.modern-input:hover {
  border-color: var(--ant-color-primary-hover);
}

.modern-input:focus,
.modern-input.ant-input-focused {
  border-color: var(--ant-color-primary);
  box-shadow: 0 0 0 4px rgba(24, 144, 255, 0.1);
}

html.dark .modern-input:focus,
html.dark .modern-input.ant-input-focused {
  box-shadow: 0 0 0 4px rgba(24, 144, 255, 0.2);
}
</style>
