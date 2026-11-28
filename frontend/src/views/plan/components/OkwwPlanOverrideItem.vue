<template>
  <a-form-item
    class="override-item"
    :class="{ 'override-item--label-only': labelOnly || !overridden }"
  >
    <template #label>
      <a-space wrap>
        <span>{{ title }}</span>
        <a-button
          v-if="!hideToggle"
          :type="overridden ? 'primary' : 'default'"
          size="small"
          :aria-pressed="overridden"
          :disabled="disabled"
          @click="emit('toggle')"
          >{{ t(overridden ? 'core.plan.oknte.overridden' : 'core.plan.oknte.inherit') }}</a-button
        >
        <slot name="actions" />
      </a-space>
    </template>
    <slot v-if="!labelOnly && overridden" />
  </a-form-item>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'

defineProps<{
  title: string
  overridden: boolean
  disabled: boolean
  hideToggle?: boolean
  labelOnly?: boolean
}>()
const emit = defineEmits<{ toggle: [] }>()
const { t } = useI18n()
</script>

<style scoped>
.override-item {
  margin-bottom: 16px;
}
.override-item:last-child {
  margin-bottom: 0;
}
.override-item--label-only :deep(.ant-form-item-control) {
  display: none;
}
.override-item--label-only :deep(.ant-form-item-label) {
  padding-bottom: 0;
}
</style>
