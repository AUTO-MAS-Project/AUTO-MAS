<template>
  <!-- 样子照 MaaFWTaskOptionEditor 里的 checkbox 类型选项，看起来是项目选项的第一行 -->
  <div class="option-item task-weekdays-field">
    <div class="option-label">{{ t('core.edit.queueTaskWeekdays') }}</div>
    <div class="weekday-row">
      <!-- 全选放在组外：放进 a-checkbox-group 里会被组的取值接管 -->
      <a-checkbox
        :checked="allChecked"
        :indeterminate="partlyChecked"
        :disabled="disabled"
        @change="handleToggleAll"
      >
        {{ t('core.edit.shellImportSelectAll') }}
      </a-checkbox>
      <a-checkbox-group
        :value="weekdays"
        :disabled="disabled"
        class="option-checkbox-group"
        @change="handleChange"
      >
        <a-checkbox v-for="option in weekdayOptions" :key="option.value" :value="option.value">
          {{ option.label }}
        </a-checkbox>
      </a-checkbox-group>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  MAAFW_WEEKDAYS,
  maafwWeekdaysAfterToggleAll,
  maafwWeekdaysSelectAllState,
} from './maafwTaskSnapshot'

const props = defineProps<{
  /** 显示的勾（ISO 星期，1=周一）：红灯时为空，绿灯时是存的运行日（没设过就是七天） */
  weekdays: number[]
  disabled?: boolean
}>()

const emit = defineEmits<{
  /** 改完后的勾选集合；为空表示一天都不跑（页面据此设成红灯） */
  update: [weekdays: number[]]
}>()

const { t } = useI18n()

// 星期叫法复用队列「执行周期」的词条，顺序是周一到周日
const WEEKDAY_KEYS = [
  'core.queue.time.Monday',
  'core.queue.time.Tuesday',
  'core.queue.time.Wednesday',
  'core.queue.time.Thursday',
  'core.queue.time.Friday',
  'core.queue.time.Saturday',
  'core.queue.time.Sunday',
] as const

const weekdayOptions = computed(() =>
  MAAFW_WEEKDAYS.map((value, index) => ({ value, label: t(WEEKDAY_KEYS[index]) }))
)

const selectAllState = computed(() => maafwWeekdaysSelectAllState(props.weekdays))
const allChecked = computed(() => selectAllState.value === 'all')
const partlyChecked = computed(() => selectAllState.value === 'partial')

const handleChange = (value: unknown) => {
  emit(
    'update',
    (Array.isArray(value) ? value : [])
      .filter((day): day is number => typeof day === 'number')
      .sort((left, right) => left - right)
  )
}

// 已经七天全勾时取消全部（变红灯），否则勾满七天（变绿灯、每天跑）
const handleToggleAll = () => {
  emit('update', maafwWeekdaysAfterToggleAll(props.weekdays))
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

/* 全选与七天排成一行，间距同选项里的勾 */
.weekday-row,
.option-checkbox-group {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 16px;
}
</style>
