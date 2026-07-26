<template>
  <a-tag
    class="v6-status-badge"
    :class="[
      `v6-status-badge--${status}`,
      `v6-status-badge--${size}`,
      { 'v6-status-badge--dot-only': dotOnly && !label && !$slots.default },
    ]"
    :color="resolvedColor"
    :bordered="false"
    :style="customStyle"
    role="status"
    :aria-label="ariaLabel"
  >
    <span v-if="showDot" class="v6-status-badge__dot" aria-hidden="true" />
    <span v-if="label || $slots.default" class="v6-status-badge__label">
      <slot>{{ resolvedLabel }}</slot>
    </span>
  </a-tag>
</template>

<script setup lang="ts">
import { computed } from 'vue'

type Status = 'success' | 'warning' | 'error' | 'info' | 'processing' | 'default' | 'idle'
type Size = 'small' | 'middle' | 'large'

interface Props {
  status?: Status
  label?: string
  showDot?: boolean
  dotOnly?: boolean
  color?: string
  size?: Size
}

const props = withDefaults(defineProps<Props>(), {
  status: 'default',
  label: '',
  showDot: true,
  dotOnly: false,
  color: undefined,
  size: 'middle',
})

const STATUS_COLOR: Record<Status, string> = {
  success: 'success',
  warning: 'warning',
  error: 'error',
  info: 'processing',
  processing: 'processing',
  default: 'default',
  idle: 'default',
}

const STATUS_LABEL: Record<Status, string> = {
  success: '成功',
  warning: '警告',
  error: '失败',
  info: '信息',
  processing: '进行中',
  default: '默认',
  idle: '空闲',
}

const resolvedColor = computed(() => props.color || STATUS_COLOR[props.status])
const resolvedLabel = computed(() => props.label || STATUS_LABEL[props.status])

const ariaLabel = computed(() => {
  const labelText = props.label || STATUS_LABEL[props.status]
  return `${labelText}${props.status ? `: ${props.status}` : ''}`
})

const customStyle = computed(() => {
  if (!props.color) return {}
  return {}
})
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
  transition: all 0.2s ease;
}

.v6-status-badge--small {
  padding: 0 var(--v6-space-1);
  font-size: 11px;
  line-height: 16px;
  gap: 2px;
}

.v6-status-badge--middle {
  padding: 1px var(--v6-space-2);
  font-size: 12px;
  line-height: 18px;
}

.v6-status-badge--large {
  padding: 2px var(--v6-space-3);
  font-size: 13px;
  line-height: 20px;
  gap: 6px;
}

.v6-status-badge--dot-only {
  padding: 0;
  width: 8px;
  height: 8px;
  justify-content: center;
}

.v6-status-badge--small.v6-status-badge--dot-only {
  width: 6px;
  height: 6px;
}

.v6-status-badge--large.v6-status-badge--dot-only {
  width: 10px;
  height: 10px;
}

.v6-status-badge__dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
  flex-shrink: 0;
  transition:
    width 0.2s ease,
    height 0.2s ease;
}

.v6-status-badge--small .v6-status-badge__dot {
  width: 5px;
  height: 5px;
}

.v6-status-badge--large .v6-status-badge__dot {
  width: 7px;
  height: 7px;
}

.v6-status-badge--dot-only .v6-status-badge__dot {
  width: 100%;
  height: 100%;
}

.v6-status-badge__label {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.v6-status-badge--processing .v6-status-badge__dot,
.v6-status-badge--info .v6-status-badge__dot {
  animation: v6-status-badge-pulse 1.2s ease-in-out infinite;
}

.v6-status-badge--idle .v6-status-badge__dot,
.v6-status-badge--default .v6-status-badge__dot {
  background: var(--v6-color-text-tertiary);
}

@keyframes v6-status-badge-pulse {
  0% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: 0.5;
    transform: scale(0.85);
  }
  100% {
    opacity: 1;
    transform: scale(1);
  }
}

/* 低性能模式 / reduced-motion 下停止脉冲动画 */
:root[data-perf-mode='low'] .v6-status-badge--processing .v6-status-badge__dot,
:root[data-perf-mode='low'] .v6-status-badge--info .v6-status-badge__dot {
  animation: none;
}

:root[data-perf-mode='low'] .v6-status-badge {
  transition: none;
}

@media (prefers-reduced-motion: reduce) {
  .v6-status-badge--processing .v6-status-badge__dot,
  .v6-status-badge--info .v6-status-badge__dot {
    animation: none;
  }
  .v6-status-badge {
    transition: none;
  }
}
</style>
