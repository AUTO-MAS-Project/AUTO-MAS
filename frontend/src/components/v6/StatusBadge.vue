<template>
  <a-tag
    class="v6-status-badge"
    :class="[`v6-status-badge--${status}`]"
    :color="resolvedColor"
    :bordered="false"
    role="status"
    :aria-label="label || status"
  >
    <span v-if="showDot" class="v6-status-badge__dot" aria-hidden="true" />
    <span class="v6-status-badge__label">{{ resolvedLabel }}</span>
  </a-tag>
</template>

<script setup lang="ts">
import { computed } from 'vue'

type Status = 'success' | 'warning' | 'error' | 'info' | 'processing'

interface Props {
  status: Status
  label?: string
  showDot?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  label: '',
  showDot: false,
})

const STATUS_COLOR: Record<Status, string> = {
  success: 'success',
  warning: 'warning',
  error: 'error',
  info: 'processing',
  processing: 'processing',
}

const STATUS_LABEL: Record<Status, string> = {
  success: '成功',
  warning: '警告',
  error: '失败',
  info: '信息',
  processing: '进行中',
}

const resolvedColor = computed(() => STATUS_COLOR[props.status])
const resolvedLabel = computed(() => props.label || STATUS_LABEL[props.status])
</script>

<style scoped>
.v6-status-badge {
  display: inline-flex;
  align-items: center;
  gap: var(--v6-space-1);
  margin: 0;
  padding: 1px var(--v6-space-2);
  font-size: 12px;
  line-height: 18px;
  border-radius: var(--v6-radius-control);
  font-weight: 500;
}

.v6-status-badge__dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}

.v6-status-badge--processing .v6-status-badge__dot {
  animation: v6-status-badge-pulse 1.2s ease-in-out infinite;
}

@keyframes v6-status-badge-pulse {
  0% {
    opacity: 1;
  }
  50% {
    opacity: 0.4;
  }
  100% {
    opacity: 1;
  }
}

/* 低性能模式 / reduced-motion 下停止脉冲动画 */
:root[data-perf-mode='low'] .v6-status-badge--processing .v6-status-badge__dot {
  animation: none;
}

@media (prefers-reduced-motion: reduce) {
  .v6-status-badge--processing .v6-status-badge__dot {
    animation: none;
  }
}
</style>
