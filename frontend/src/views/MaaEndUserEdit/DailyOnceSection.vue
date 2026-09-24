<template>
  <div class="daily-once-section">
    <p class="daily-once-hint">{{ t('edit.maaEndDailyOnceTasksHint') }}</p>
    <a-select
      :value="dailyOnceTaskValues"
      mode="multiple"
      :options="dailyOnceTaskOptions"
      :disabled="loading"
      :aria-label="t('edit.maaEndDailyOnceTasks')"
      option-filter-prop="label"
      show-search
      max-tag-count="responsive"
      :placeholder="t('edit.maaEndDailyOnceTasksPlaceholder')"
      @change="handleChange"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { MAAEND_DAILY_ONCE_TASK_OPTIONS } from '@/utils/maaEndProtocolSpace'

const props = defineProps<{ value: unknown; loading: boolean }>()
const emit = defineEmits<{ save: [value: string] }>()
const { t } = useI18n()

const dailyOnceTaskValues = computed(() => {
  const value = props.value
  if (Array.isArray(value)) {
    return value.filter((item: unknown): item is string => typeof item === 'string')
  }
  if (typeof value === 'string' && value.trim()) {
    try {
      const parsed: unknown = JSON.parse(value)
      return Array.isArray(parsed)
        ? parsed.filter((item): item is string => typeof item === 'string')
        : []
    } catch {
      return []
    }
  }
  return []
})
const dailyOnceTaskOptions = MAAEND_DAILY_ONCE_TASK_OPTIONS.map(task => ({
  label: task.label,
  value: task.name,
}))

const handleChange = (values: string[]) => {
  if (props.loading) return
  emit('save', JSON.stringify(Array.from(new Set(values.filter(Boolean)))))
}
</script>

<style scoped>
.daily-once-hint {
  margin: 0 0 16px;
  color: var(--ant-color-text-secondary);
}
.daily-once-section :deep(.ant-select) {
  width: 100%;
}
</style>
