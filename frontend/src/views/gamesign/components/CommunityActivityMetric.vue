<script setup lang="ts">
import { computed } from 'vue'
import type { NoteMetric } from '../communityActivityPresentation'

const props = withDefaults(
  defineProps<{ metric: NoteMetric; featured?: boolean; simplified?: boolean }>(),
  { featured: false, simplified: false }
)
const hasProgress = computed(() => props.metric.target > 0)
const percent = computed(() =>
  hasProgress.value
    ? Math.min(100, Math.max(0, (props.metric.current / props.metric.target) * 100))
    : 0
)
// 数值已表达普通进度；领取、恢复、未解锁等独立状态始终保留。
const showStatus = computed(
  () =>
    props.metric.status &&
    (props.featured ||
      !hasProgress.value ||
      !['进行中', '已完成', '可用'].includes(props.metric.status))
)
</script>

<template>
  <div
    class="activity-metric"
    :class="{ 'activity-metric--featured': featured }"
    :data-period="metric.period"
  >
    <span class="activity-metric-name">{{ metric.name }}</span>
    <strong v-if="hasProgress" class="activity-metric-value">
      {{ metric.current }}<small> / {{ metric.target }}</small>
    </strong>
    <span v-if="showStatus" class="activity-metric-status">{{ metric.status }}</span>
    <a-progress
      v-if="featured && hasProgress && !simplified"
      :percent="percent"
      :show-info="false"
      :stroke-width="3"
      size="small"
      class="activity-metric-bar"
    />
  </div>
</template>

<style scoped>
.activity-metric {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-content: center;
  align-items: baseline;
  gap: 0 6px;
  min-width: 0;
  min-height: 26px;
  box-sizing: border-box;
  padding: 2px 0;
  border-bottom: 1px solid var(--ant-color-border-secondary);
  font-size: 12px;
  line-height: 1.35;
  letter-spacing: 0;
}

.activity-metric-name {
  min-width: 0;
  color: var(--ant-color-text);
  overflow-wrap: anywhere;
}

.activity-metric-value {
  color: var(--ant-color-text);
  font-size: 13px;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.activity-metric-value small {
  color: var(--ant-color-text-secondary);
  font-size: 11px;
  font-weight: 400;
}

.activity-metric-status {
  grid-column: 1 / -1;
  color: var(--ant-color-text-secondary);
  font-size: 11px;
  overflow-wrap: anywhere;
}

.activity-metric--featured {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  justify-content: center;
  gap: 2px;
  border-bottom: 0;
}

.activity-metric--featured .activity-metric-value {
  font-size: 22px;
  line-height: 1.2;
}

.activity-metric--featured .activity-metric-value small {
  font-size: 12px;
}

.activity-metric--featured .activity-metric-status {
  min-height: 15px;
}

.activity-metric-bar {
  margin: 0;
  line-height: 1;
}
</style>
