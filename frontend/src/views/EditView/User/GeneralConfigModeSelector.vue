<template>
  <a-form-item class="config-mode-form-item">
    <template #label>
      <span class="config-mode-label">
        配置管理方式
        <span v-if="saving" class="config-mode-saving">
          <LoadingOutlined spin />
          正在保存
        </span>
      </span>
    </template>

    <a-radio-group
      :value="modelValue"
      :disabled="disabled || saving"
      class="config-mode-options"
      aria-label="配置管理方式"
      @change="handleChange"
    >
      <label
        :class="['config-mode-option', { selected: modelValue, disabled: disabled || saving }]"
      >
        <a-radio :value="true" class="config-mode-radio" />
        <span class="config-mode-icon"><DatabaseOutlined /></span>
        <span class="config-mode-copy">
          <span class="config-mode-title">用户独立配置</span>
          <span class="config-mode-description">
            为该用户保存独立配置，运行前加载，结束时按任务策略保存。
          </span>
        </span>
      </label>

      <label
        :class="['config-mode-option', { selected: !modelValue, disabled: disabled || saving }]"
      >
        <a-radio :value="false" class="config-mode-radio" />
        <span class="config-mode-icon"><FileTextOutlined /></span>
        <span class="config-mode-copy">
          <span class="config-mode-title">脚本直控配置</span>
          <span class="config-mode-description">
            直接使用脚本当前配置，不加载或回写该用户的独立配置。
          </span>
        </span>
      </label>
    </a-radio-group>

    <a-alert
      class="config-mode-alert"
      type="info"
      show-icon
      message="同一通用脚本下可以为不同用户选择不同配置来源；脚本直控配置由脚本自身维护，并由直控用户共享。"
    />
  </a-form-item>
</template>

<script setup lang="ts">
import { DatabaseOutlined, FileTextOutlined, LoadingOutlined } from '@ant-design/icons-vue'
import type { RadioChangeEvent } from 'ant-design-vue/es/radio/interface'

defineProps<{
  modelValue: boolean
  disabled?: boolean
  saving?: boolean
}>()

const emit = defineEmits<{
  change: [value: boolean]
}>()

const handleChange = (event: RadioChangeEvent) => {
  emit('change', Boolean(event.target.value))
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
