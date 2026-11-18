<template>
  <div v-if="collapsed" class="option-item task-weekdays-field task-weekdays-summary">
    <span class="option-label">{{ t('core.edit.queueTaskWeekdays') }}</span>
    <span class="task-weekdays-value">{{ t('core.edit.queueTaskWeekdaysEveryDay') }}</span>
    <a-button type="link" size="small" :disabled="disabled" @click="expanded = true">
      {{ t('core.edit.queueTaskWeekdaysChange') }}
    </a-button>
  </div>
  <div v-else class="option-item task-weekdays-field">
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
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  MAAFW_WEEKDAYS,
  maafwWeekdaysAfterToggleAll,
  maafwWeekdaysSelectAllState,
} from './maafwTaskSnapshot'

/**
 * 右栏「运行日」：样子照 MaaFWTaskOptionEditor 里的 checkbox 类型选项。七天全勾（每天跑，多数任务
 * 如此）时收成一行「运行日：每天」，点「修改」才展开八个勾；不是每天时直接展开。
 */
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

// 点过「修改」就一直展开（又勾回七天也不收），换一个任务时由父级按任务重建、重新收起
const expanded = ref(false)
const collapsed = computed(() => allChecked.value && !expanded.value)

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
/* 与 MaaFWTaskOptionEditor 的选项同一套样式 */
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

/* 收起时一行：标签、「每天」、修改入口 */
.task-weekdays-summary {
  flex-direction: row;
  flex-wrap: wrap;
  align-items: center;
}

.task-weekdays-value {
  color: var(--ant-color-text-secondary);
}

.task-weekdays-summary :deep(.ant-btn) {
  padding-inline: 0;
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
