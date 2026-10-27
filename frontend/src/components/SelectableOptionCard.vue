<template>
  <a-radio
    :value="value"
    :disabled="disabled"
    :class="[
      'selectable-option-card',
      {
        selected,
        disabled,
        'align-start': align === 'start',
        'radio-end': radioPosition === 'end',
      },
    ]"
  >
    <slot name="icon" />
    <span class="selectable-option-card__content">
      <span class="selectable-option-card__title">{{ title }}</span>
      <slot name="meta" />
      <span v-if="description || $slots.description" class="selectable-option-card__description">
        <slot name="description">{{ description }}</slot>
      </span>
    </span>
  </a-radio>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    value: string
    title: string
    description?: string
    selected?: boolean
    disabled?: boolean
    align?: 'center' | 'start'
    radioPosition?: 'start' | 'end'
  }>(),
  {
    description: undefined,
    selected: false,
    disabled: false,
    align: 'center',
    radioPosition: 'start',
  }
)
</script>

<style scoped>
.selectable-option-card {
  display: flex;
  width: 100%;
  min-width: 0;
  gap: 12px;
  align-items: center;
  margin-inline-end: 0;
  padding: 14px;
  border: 1px solid var(--ant-color-border);
  border-radius: 8px;
  color: var(--ant-color-text);
  background: var(--ant-color-bg-container);
  cursor: pointer;
}

.selectable-option-card :deep(.ant-radio + span) {
  display: flex;
  min-width: 0;
  flex: 1;
  gap: 12px;
  align-items: center;
}

.selectable-option-card.radio-end :deep(.ant-radio) {
  order: 1;
}

.selectable-option-card.radio-end :deep(.ant-radio + span) {
  order: 0;
}

.selectable-option-card.align-start {
  align-items: flex-start;
}

.selectable-option-card.align-start :deep(.ant-radio + span) {
  align-items: flex-start;
}

.selectable-option-card:hover,
.selectable-option-card.selected {
  border-color: var(--ant-color-primary);
}

.selectable-option-card.selected {
  background: var(--ant-color-primary-bg);
}

.selectable-option-card.disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.selectable-option-card__content {
  display: flex;
  min-width: 0;
  flex: 1;
  flex-direction: column;
}

.selectable-option-card__title {
  color: var(--ant-color-text);
  font-size: 14px;
  font-weight: 600;
}

.selectable-option-card__description {
  margin-top: 3px;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
}

:slotted(.selectable-option-icon) {
  display: inline-flex;
  width: 38px;
  height: 38px;
  flex: 0 0 38px;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  color: var(--ant-color-primary);
  background: var(--ant-color-primary-bg);
  font-size: 19px;
}

:slotted(.selectable-option-image) {
  width: 34px;
  height: 34px;
  flex: 0 0 34px;
  border-radius: 6px;
  object-fit: contain;
}
</style>
