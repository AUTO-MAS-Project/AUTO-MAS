<script setup lang="ts">
import { ref, useId } from 'vue'
import { useI18n } from 'vue-i18n'
import { DatabaseOutlined, FileTextOutlined, SettingOutlined } from '@ant-design/icons-vue'
import type { RadioChangeEvent } from 'ant-design-vue/es/radio/interface'
import type { ConfigModeOption } from './configModeOptions'

withDefaults(
  defineProps<{
    modelValue: boolean | string | undefined
    label: string
    options: ConfigModeOption[]
    disabled?: boolean
  }>(),
  { disabled: false }
)

const emit = defineEmits<{ change: [event: RadioChangeEvent] }>()
const { t } = useI18n()
const detailsId = useId()
const descriptionsExpanded = ref(false)
</script>

<template>
  <div class="config-mode-choices">
    <a-radio-group
      :value="modelValue"
      :disabled="disabled"
      class="config-mode-options"
      :aria-label="label"
      @change="emit('change', $event)"
    >
      <label
        v-for="option in options"
        :key="String(option.value)"
        class="config-mode-option"
        :class="{ selected: modelValue === option.value, disabled: disabled || option.disabled }"
        :aria-disabled="disabled || option.disabled || undefined"
      >
        <a-radio
          :value="option.value"
          class="config-mode-radio"
          :disabled="disabled || option.disabled"
        />
        <span class="config-mode-icon" aria-hidden="true">
          <DatabaseOutlined v-if="option.icon === 'database'" />
          <SettingOutlined v-else-if="option.icon === 'setting'" />
          <FileTextOutlined v-else />
        </span>
        <span class="config-mode-copy">
          <span class="config-mode-title">{{ option.title }}</span>
          <span v-if="option.summary" class="config-mode-summary">{{ option.summary }}</span>
          <span
            class="config-mode-description"
            :class="{ 'config-mode-description--collapsible': option.summary }"
            >{{ option.description }}</span
          >
          <span
            v-if="option.disabled && option.disabledReason"
            class="config-mode-disabled-reason"
            >{{ option.disabledReason }}</span
          >
        </span>
      </label>
    </a-radio-group>

    <a-button
      class="config-mode-details-toggle"
      type="link"
      size="small"
      html-type="button"
      :aria-expanded="descriptionsExpanded"
      :aria-controls="detailsId"
      @click="descriptionsExpanded = !descriptionsExpanded"
    >
      {{
        t(
          descriptionsExpanded
            ? 'core.edit.configModeHideDescriptions'
            : 'core.edit.configModeShowDescriptions'
        )
      }}
    </a-button>
    <div v-show="descriptionsExpanded" :id="detailsId" class="config-mode-details">
      <dl>
        <template v-for="option in options" :key="String(option.value)">
          <dt>{{ option.title }}</dt>
          <dd>{{ option.description }}</dd>
        </template>
      </dl>
    </div>
  </div>
</template>

<style scoped>
.config-mode-choices {
  min-width: 0;
  container-type: inline-size;
  container-name: config-mode;
}

.config-mode-options {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 260px), 1fr));
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
  overflow-wrap: anywhere;
  white-space: normal;
}

.config-mode-title {
  color: var(--ant-color-text);
  font-size: 14px;
  font-weight: 600;
  line-height: 1.5;
}

.config-mode-description,
.config-mode-summary,
.config-mode-disabled-reason {
  color: var(--ant-color-text-secondary);
  font-size: 13px;
  line-height: 1.5;
  /* 保留描述文案中的换行，如 ZZZ-OD 原生来源的约束说明。 */
  white-space: pre-line;
}

.config-mode-summary,
.config-mode-details-toggle,
.config-mode-details {
  display: none;
}

.config-mode-details-toggle {
  height: auto;
  margin-top: 8px;
  padding-inline: 0;
  white-space: normal;
  text-align: left;
}

.config-mode-details dl {
  margin: 12px 0 0;
  overflow-wrap: anywhere;
}

.config-mode-details dt {
  font-weight: 600;
  color: var(--ant-color-text);
}

.config-mode-details dd {
  margin: 4px 0 12px;
  color: var(--ant-color-text-secondary);
  font-size: 13px;
  white-space: pre-line;
}

@container config-mode (max-width: 640px) {
  .config-mode-options {
    grid-template-columns: minmax(0, 1fr);
  }

  .config-mode-option {
    min-height: 0;
    padding: 12px;
  }

  .config-mode-summary,
  .config-mode-details {
    display: block;
  }

  .config-mode-description--collapsible {
    display: none;
  }

  .config-mode-details-toggle {
    display: inline-flex;
  }
}

@container config-mode (max-width: 360px) {
  .config-mode-option {
    grid-template-columns: auto minmax(0, 1fr);
    gap: 8px;
  }

  .config-mode-icon {
    display: none;
  }
}
</style>
