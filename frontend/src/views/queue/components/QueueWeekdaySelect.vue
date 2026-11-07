<template>
  <a-select
    v-model:value="value"
    mode="multiple"
    size="small"
    :placeholder="t('core.queue.time.selectDays')"
    :disabled="disabled"
    :bordered="bordered"
    :max-tag-count="everyDay ? 0 : maxTagCount"
    :max-tag-placeholder="maxTagPlaceholder"
    @change="emit('change')"
  >
    <a-select-option v-for="day in WEEKDAYS" :key="day" :value="day">
      {{ t(`core.queue.time.${day}`) }}
    </a-select-option>
  </a-select>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

withDefaults(defineProps<{ disabled?: boolean; bordered?: boolean; maxTagCount?: number }>(), {
  disabled: false,
  bordered: true,
  maxTagCount: 7,
})
const value = defineModel<string[]>('value', { required: true })
const emit = defineEmits<{ change: [] }>()
const { t } = useI18n()

// 全选仅折叠标签；星期数组与保存逻辑仍由各调用方持有。
const WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
const everyDay = computed(() => WEEKDAYS.every(day => value.value.includes(day)))
const maxTagPlaceholder = (omittedValues: unknown[]) =>
  omittedValues.length === WEEKDAYS.length ? t('core.plan.week.ALL') : `+${omittedValues.length}`
</script>
