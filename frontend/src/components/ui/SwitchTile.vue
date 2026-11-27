<script setup lang="ts">
import { useId, type Component } from 'vue'

withDefaults(
  defineProps<{
    title: string
    description?: string
    icon?: Component
    variant?: 'tile' | 'card'
    disabled?: boolean
    loading?: boolean
  }>(),
  { description: undefined, icon: undefined, variant: 'tile' }
)

const checked = defineModel<boolean>('checked', { required: true })
const emit = defineEmits<{ change: [checked: boolean] }>()
const descriptionId = useId()

function handleChange(value: boolean | string | number) {
  const next = Boolean(value)
  checked.value = next
  emit('change', next)
}
</script>

<template>
  <div
    class="switch-tile"
    :class="[`switch-tile--${variant}`, { 'switch-tile--disabled': disabled }]"
  >
    <div class="switch-tile-copy">
      <div class="switch-tile-title">
        <component :is="icon" v-if="icon" class="switch-tile-icon" aria-hidden="true" />
        {{ title }}
      </div>
      <div v-if="description" :id="descriptionId" class="switch-tile-description">
        {{ description }}
      </div>
    </div>
    <a-switch
      :checked="checked"
      :disabled="disabled"
      :loading="loading"
      :aria-label="title"
      :aria-describedby="description ? descriptionId : undefined"
      @change="handleChange"
    />
  </div>
</template>

<style scoped>
.switch-tile {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 14px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: var(--ant-border-radius-lg, 8px);
  background: var(--ant-color-fill-quaternary);
}

.switch-tile--tile {
  height: 100%;
}

.switch-tile--card {
  padding: 14px 20px;
  margin-bottom: 16px;
  border-radius: var(--ant-border-radius-lg);
  background: var(--app-appearance-surface-bg, var(--ant-color-bg-container));
}

html:not(.dark):not(.appearance-custom) .switch-tile--card {
  box-shadow:
    0 1px 2px rgba(16, 24, 40, 0.04),
    0 4px 12px -4px rgba(16, 24, 40, 0.06);
}

.switch-tile--disabled {
  opacity: 0.65;
}

.switch-tile-copy {
  min-width: 0;
  overflow-wrap: anywhere;
}

.switch-tile-title {
  color: var(--ant-color-text);
  font-size: 13px;
  font-weight: 500;
}

.switch-tile--card .switch-tile-title {
  font-size: 14px;
  font-weight: 600;
}

.switch-tile-icon {
  margin-inline-end: 6px;
  color: var(--ant-color-primary);
}

.switch-tile-description {
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
  line-height: 20px;
}
</style>
