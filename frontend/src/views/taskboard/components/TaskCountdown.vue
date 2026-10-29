<template>
  <div v-if="parts" class="tb-countdown">
    <span class="tb-cd-cell">
      <span class="tb-cd-num">{{ parts.days }}</span>
      <span class="tb-cd-unit">{{ t('core.taskboard.unitDay') }}</span>
    </span>
    <span class="tb-cd-cell">
      <span class="tb-cd-num">{{ pad2(parts.hours) }}</span>
      <span class="tb-cd-unit">{{ t('core.taskboard.unitHour') }}</span>
    </span>
    <span class="tb-cd-cell">
      <span class="tb-cd-num">{{ pad2(parts.minutes) }}</span>
      <span class="tb-cd-unit">{{ t('core.taskboard.unitMinute') }}</span>
    </span>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { parseActivityTime } from '@/utils/activityTime'
import { useCountdownClock } from '../useCountdownClock'

interface Props {
  endTime: string
}

const props = defineProps<Props>()
const { t } = useI18n()
const now = useCountdownClock()

const DAY = 86_400_000
const HOUR = 3_600_000
const MINUTE = 60_000

/* 结束时间只解析一次，分钟级刷新只影响下面的天/时/分计算。 */
const end = computed(() => parseActivityTime(props.endTime))

const parts = computed(() => {
  const timestamp = end.value
  if (!timestamp) return null
  const left = Math.max(0, timestamp - now.value)
  return {
    days: Math.floor(left / DAY),
    hours: Math.floor((left % DAY) / HOUR),
    minutes: Math.floor((left % HOUR) / MINUTE),
  }
})

const pad2 = (value: number) => String(value).padStart(2, '0')
</script>

<style scoped>
.tb-countdown {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 6px;
}

.tb-cd-cell {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 4px 0 3px;
  border-radius: 6px;
  background: var(--ant-color-fill-secondary);
}

.tb-cd-num {
  color: var(--ant-color-text);
  font-size: 18px;
  font-weight: 600;
  line-height: 1.2;
  font-variant-numeric: tabular-nums;
}

.tb-cd-unit {
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
  line-height: 1.4;
}
</style>
