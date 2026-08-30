<template>
  <a-form-item class="config-mode-form-item">
    <template #label>
      <span class="config-mode-label">
        {{ t('edit.configurationManagement') }}
        <span v-if="saving" class="config-mode-saving">
          <LoadingOutlined spin />
          {{ t('edit.saving') }}
        </span>
      </span>
    </template>

    <a-radio-group
      :value="modelValue"
      :disabled="disabled || saving"
      class="config-mode-options"
      :style="{ gridTemplateColumns: `repeat(${Math.min(options.length, 3)}, minmax(0, 1fr))` }"
      :aria-label="t('edit.configurationManagement')"
      @change="handleChange"
    >
      <label
        v-for="option in options"
        :key="String(option.value)"
        :class="[
          'config-mode-option',
          { selected: modelValue === option.value, disabled: disabled || saving },
        ]"
      >
        <a-radio :value="option.value" class="config-mode-radio" />
        <span class="config-mode-icon">
          <DatabaseOutlined v-if="option.icon === 'database'" />
          <SettingOutlined v-else-if="option.icon === 'setting'" />
          <FileTextOutlined v-else />
        </span>
        <span class="config-mode-copy">
          <span class="config-mode-title">{{ option.title }}</span>
          <span class="config-mode-description">{{ option.description }}</span>
        </span>
      </label>
    </a-radio-group>

    <a-alert class="config-mode-alert" type="info" show-icon :message="alertMessage" />
  </a-form-item>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import {
  DatabaseOutlined,
  FileTextOutlined,
  LoadingOutlined,
  SettingOutlined,
} from '@ant-design/icons-vue'
import type { RadioChangeEvent } from 'ant-design-vue/es/radio/interface'

const { t } = useI18n()

type ConfigModeOption = {
  value: boolean | string
  title: string
  description: string
  icon?: 'database' | 'file' | 'setting'
}

const props = withDefaults(
  defineProps<{
    modelValue: boolean | string
    disabled?: boolean
    saving?: boolean
    options?: ConfigModeOption[]
    alertMessage?: string
  }>(),
  {
    options: () => [
      {
        value: true,
        title: t('edit.perUserConfiguration'),
        description: t('edit.saveSeparateConfigurationThis'),
        icon: 'database',
      },
      {
        value: false,
        title: t('edit.scriptDirectConfiguration'),
        description: t('edit.useScriptSCurrent'),
        icon: 'file',
      },
    ],
    alertMessage:
      '同一脚本下可以为不同用户选择不同配置来源；直控配置由脚本自身维护，并由直控用户共享。',
  }
)

const options = props.options
const alertMessage = props.alertMessage

const emit = defineEmits<{
  change: [value: boolean | string]
}>()

const handleChange = (event: RadioChangeEvent) => {
  emit('change', event.target.value as boolean | string)
}
</script>

<style scoped>
.config-mode-form-item {
  margin-top: 8px;
}

.config-mode-label {
  display: flex;
  align-items: center;
  gap: 12px;
  font-weight: 600;
}

.config-mode-saving {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  font-weight: 400;
}

.config-mode-options {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  width: 100%;
}

.config-mode-option {
  display: grid;
  grid-template-columns: auto 32px minmax(0, 1fr);
  align-items: start;
  gap: 12px;
  min-width: 0;
  min-height: 96px;
  padding: 16px;
  border: 1px solid var(--ant-color-border);
  border-radius: 8px;
  background: var(--ant-color-bg-container);
  cursor: pointer;
  transition:
    border-color 0.2s ease,
    background 0.2s ease,
    box-shadow 0.2s ease;
}

.config-mode-option:hover:not(.disabled) {
  border-color: var(--ant-color-primary-hover);
}

.config-mode-option.selected {
  border-color: var(--ant-color-primary);
  background: var(--ant-color-primary-bg);
  box-shadow: 0 0 0 1px var(--ant-color-primary);
}

.config-mode-option.disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.config-mode-radio {
  margin-top: 5px;
}

.config-mode-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 6px;
  background: var(--ant-color-bg-layout);
  color: var(--ant-color-text-secondary);
  font-size: 17px;
}

.config-mode-option.selected .config-mode-icon {
  color: var(--ant-color-primary);
}

.config-mode-copy {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.config-mode-title {
  color: var(--ant-color-text);
  font-size: 14px;
  font-weight: 600;
  line-height: 1.5;
}

.config-mode-description {
  color: var(--ant-color-text-secondary);
  font-size: 13px;
  line-height: 1.5;
}

.config-mode-alert {
  margin-top: 12px;
}

@media (max-width: 760px) {
  .config-mode-options {
    grid-template-columns: 1fr;
  }
}
</style>
