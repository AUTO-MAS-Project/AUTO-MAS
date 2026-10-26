<template>
  <!-- 样子照 MaaFWTaskOptionEditor 里的 checkbox 类型选项，看起来是项目选项的第一行 -->
  <div class="option-item task-weekdays-field">
    <div class="option-label">{{ t('edit.queueTaskWeekdays') }}</div>
    <a-checkbox-group
      :value="weekdays"
      :disabled="disabled"
      class="option-checkbox-group"
      @change="handleChange"
    >
      <template v-for="option in weekdayOptions" :key="option.value">
        <!-- 只剩一个勾时它不能再取消：不允许一天都不跑，不想跑用队列里的红灯 -->
        <a-tooltip v-if="isLastChecked(option.value)" :title="t('edit.queueTaskWeekdaysKeepOne')">
          <span>
            <a-checkbox :value="option.value" disabled>{{ option.label }}</a-checkbox>
          </span>
        </a-tooltip>
        <a-checkbox v-else :value="option.value">{{ option.label }}</a-checkbox>
      </template>
    </a-checkbox-group>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { MAAFW_WEEKDAYS } from './maafwTaskSnapshot'

const props = defineProps<{
  /** 当前勾着的 ISO 星期（1=周一）；没设过就是七天全勾 */
  weekdays: number[]
  disabled?: boolean
}>()

const emit = defineEmits<{
  update: [weekdays: number[]]
}>()

const { t } = useI18n()

// 星期叫法复用队列「执行周期」的词条，顺序是周一到周日
const WEEKDAY_KEYS = [
  'queue.time.Monday',
  'queue.time.Tuesday',
  'queue.time.Wednesday',
  'queue.time.Thursday',
  'queue.time.Friday',
  'queue.time.Saturday',
  'queue.time.Sunday',
] as const

const weekdayOptions = computed(() =>
  MAAFW_WEEKDAYS.map((value, index) => ({ value, label: t(WEEKDAY_KEYS[index]) }))
)

const isLastChecked = (day: number) => props.weekdays.length === 1 && props.weekdays[0] === day

const handleChange = (value: unknown) => {
  const weekdays = (Array.isArray(value) ? value : [])
    .filter((day): day is number => typeof day === 'number')
    .sort((left, right) => left - right)
  if (weekdays.length === 0) return
  emit('update', weekdays)
}
</script>

<style scoped>
/* 与 MaaFWTaskOptionEditor 的选项同一套样式；下面紧跟编辑器，间距同编辑器内的 16px */
.task-weekdays-field {
  margin-bottom: 16px;
}

.option-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.option-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 600;
  color: var(--ant-color-text);
}

/* antd 的 .ant-checkbox-group 自带 align-self: center，在纵向排列的选项里会被挤到中间；靠左 */
.option-checkbox-group {
  display: flex;
  flex-wrap: wrap;
  align-self: flex-start;
  gap: 8px 16px;
}
</style>
