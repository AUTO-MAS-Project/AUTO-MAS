<template>
  <aside
    class="mac-state-panel"
    :class="[
      `mac-state-panel--${type}`,
      {
        'mac-state-panel--bordered': bordered,
        'mac-state-panel--closable': closable,
        'mac-state-panel--compact': compact,
      },
    ]"
    role="status"
    :aria-label="computedAriaLabel"
  >
    <div class="mac-state-panel__indicator" aria-hidden="true" />
    <div class="mac-state-panel__body">
      <header v-if="hasHeader" class="mac-state-panel__header">
        <div class="mac-state-panel__title-group">
          <slot name="icon">
            <span v-if="icon" class="mac-state-panel__icon" aria-hidden="true">{{ icon }}</span>
          </slot>
          <slot name="title">
            <h3 v-if="title" class="mac-state-panel__title">{{ title }}</h3>
          </slot>
        </div>
        <div v-if="$slots.actions || closable" class="mac-state-panel__header-actions">
          <slot name="actions" />
          <button
            v-if="closable"
            type="button"
            class="mac-state-panel__close"
            aria-label="关闭"
            @click="handleClose"
          >
            <svg viewBox="0 0 12 12" aria-hidden="true">
              <path
                d="M3 3L9 9M9 3L3 9"
                fill="none"
                stroke="currentColor"
                stroke-width="1.5"
                stroke-linecap="round"
              />
            </svg>
          </button>
        </div>
      </header>
      <div v-if="$slots.default" class="mac-state-panel__content">
        <slot />
      </div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useSlots } from 'vue'

type PanelType = 'info' | 'success' | 'warning' | 'error' | 'neutral'

interface Props {
  title?: string
  icon?: string
  type?: PanelType
  bordered?: boolean
  closable?: boolean
  compact?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  title: undefined,
  icon: undefined,
  type: 'neutral',
  bordered: true,
  closable: false,
  compact: false,
})

const emit = defineEmits<{
  close: []
}>()

const slots = useSlots()

const TYPE_LABELS: Record<PanelType, string> = {
  info: '信息',
  success: '成功',
  warning: '警告',
  error: '错误',
  neutral: '状态',
}

const hasHeader = computed(
  () =>
    props.title || props.icon || !!slots.title || !!slots.icon || !!slots.actions || props.closable
)

const computedAriaLabel = computed(() => {
  if (props.title) return `${TYPE_LABELS[props.type]}: ${props.title}`
  return TYPE_LABELS[props.type]
})

function handleClose() {
  emit('close')
}
</script>

<style scoped>
.mac-state-panel {
  position: relative;
  display: flex;
  gap: var(--v6-space-3);
  padding: var(--v6-space-4);
  background: var(--v6-color-surface);
  border: 1px solid var(--v6-color-border);
  border-radius: var(--v6-radius-card);
  box-shadow: var(--v6-shadow-card);
  overflow: hidden;
  transition:
    padding var(--v6-motion-fast) var(--v6-ease-out),
    border-color var(--v6-motion-fast) var(--v6-ease-out),
    box-shadow var(--v6-motion-fast) var(--v6-ease-out);
}

.mac-state-panel--compact {
  padding: var(--v6-space-2) var(--v6-space-3);
  gap: var(--v6-space-2);
}

.mac-state-panel--bordered {
  border-color: var(--v6-color-border);
}

.mac-state-panel__indicator {
  position: absolute;
  top: 0;
  left: 0;
  bottom: 0;
  width: 3px;
  flex-shrink: 0;
  border-radius: var(--v6-radius-card) 0 0 var(--v6-radius-card);
  transition: background-color var(--v6-motion-fast) var(--v6-ease-out);
}

.mac-state-panel--info .mac-state-panel__indicator {
  background-color: var(--v6-color-info);
}

.mac-state-panel--success .mac-state-panel__indicator {
  background-color: var(--v6-color-success);
}

.mac-state-panel--warning .mac-state-panel__indicator {
  background-color: var(--v6-color-warning);
}

.mac-state-panel--error .mac-state-panel__indicator {
  background-color: var(--v6-color-error);
}

.mac-state-panel--neutral .mac-state-panel__indicator {
  background-color: var(--v6-color-text-tertiary);
}

.mac-state-panel--info {
  background: var(--v6-color-info-bg);
  border-color: var(--v6-color-info-border);
}

.mac-state-panel--success {
  background: var(--v6-color-success-bg);
  border-color: var(--v6-color-success-border);
}

.mac-state-panel--warning {
  background: var(--v6-color-warning-bg);
  border-color: var(--v6-color-warning-border);
}

.mac-state-panel--error {
  background: var(--v6-color-error-bg);
  border-color: var(--v6-color-error-border);
}

.mac-state-panel__body {
  flex: 1;
  min-width: 0;
  padding-left: var(--v6-space-2);
}

.mac-state-panel__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--v6-space-2);
}

.mac-state-panel__title-group {
  display: flex;
  align-items: center;
  gap: var(--v6-space-2);
  min-width: 0;
  flex: 1;
}

.mac-state-panel__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: var(--v6-font-size-lg);
  flex-shrink: 0;
}

.mac-state-panel--info .mac-state-panel__icon {
  color: var(--v6-color-info);
}

.mac-state-panel--success .mac-state-panel__icon {
  color: var(--v6-color-success);
}

.mac-state-panel--warning .mac-state-panel__icon {
  color: var(--v6-color-warning);
}

.mac-state-panel--error .mac-state-panel__icon {
  color: var(--v6-color-error);
}

.mac-state-panel__title {
  margin: 0;
  font-size: var(--v6-font-size-base);
  font-weight: var(--v6-font-weight-semibold);
  line-height: var(--v6-line-height-snug);
  color: var(--v6-color-text);
}

.mac-state-panel__header-actions {
  display: flex;
  align-items: center;
  gap: var(--v6-space-1);
  flex-shrink: 0;
}

.mac-state-panel__close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  padding: 0;
  margin: 0;
  background: none;
  border: none;
  border-radius: var(--v6-radius-sm);
  color: var(--v6-color-text-tertiary);
  cursor: pointer;
  transition:
    color var(--v6-motion-fast) var(--v6-ease-out),
    background-color var(--v6-motion-fast) var(--v6-ease-out);
}

.mac-state-panel__close:hover {
  color: var(--v6-color-text);
  background: var(--v6-vibrancy-hover);
}

.mac-state-panel__close:focus-visible {
  outline: var(--v6-outline-width) solid var(--v6-color-info);
  outline-offset: var(--v6-focus-ring-offset);
}

.mac-state-panel__close svg {
  width: 10px;
  height: 10px;
}

.mac-state-panel__content {
  margin-top: var(--v6-space-2);
  font-size: var(--v6-font-size-sm);
  line-height: var(--v6-line-height-normal);
  color: var(--v6-color-text-secondary);
}

.mac-state-panel--compact .mac-state-panel__content {
  margin-top: var(--v6-space-1);
}

:root[data-perf-mode='low'] .mac-state-panel {
  box-shadow: none;
  transition: none;
}

:root[data-perf-mode='low'] .mac-state-panel__indicator,
:root[data-perf-mode='low'] .mac-state-panel__close {
  transition: none;
}

@media (prefers-reduced-motion: reduce) {
  .mac-state-panel,
  .mac-state-panel__indicator,
  .mac-state-panel__close {
    transition: none;
  }
}
</style>
