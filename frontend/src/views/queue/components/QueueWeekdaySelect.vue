<template>
  <a-select
    v-model:value="value"
    mode="multiple"
    size="small"
    :placeholder="t('core.queue.time.selectDays')"
    :disabled="disabled"
    :bordered="bordered"
    :max-tag-count="areAllWeekdaysSelected(value) ? 0 : 7"
    :max-tag-placeholder="() => t('core.plan.week.ALL')"
    @change="emit('change')"
  >
    <a-select-option v-for="day in QUEUE_WEEKDAYS" :key="day" :value="day">
      {{ t(`core.queue.time.${day}`) }}
    </a-select-option>
  </a-select>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { areAllWeekdaysSelected, QUEUE_WEEKDAYS } from './queueWeekdays'

withDefaults(defineProps<{ disabled?: boolean; bordered?: boolean }>(), {
  disabled: false,
  bordered: true,
})
const value = defineModel<string[]>('value', { required: true })
const emit = defineEmits<{ change: [] }>()
const { t } = useI18n()
</script>
