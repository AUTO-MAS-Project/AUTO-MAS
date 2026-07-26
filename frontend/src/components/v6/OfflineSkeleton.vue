<template>
  <div
    class="v6-offline-skeleton"
    :class="{ 'v6-offline-skeleton--compact': compact }"
    role="alert"
    aria-live="assertive"
  >
    <div class="v6-offline-skeleton__body">
      <DisconnectOutlined class="v6-offline-skeleton__icon" aria-hidden="true" />
      <div class="v6-offline-skeleton__text">
        <p class="v6-offline-skeleton__title">{{ title }}</p>
        <p v-if="message" class="v6-offline-skeleton__message">{{ message }}</p>
        <p v-if="diagnosticInfo" class="v6-offline-skeleton__diagnostic">
          {{ diagnosticInfo }}
        </p>
        <p
          v-if="currentCountdown !== undefined && currentCountdown > 0"
          class="v6-offline-skeleton__countdown"
          aria-live="polite"
        >
          {{ resolvedCountdownText }}
        </p>
      </div>
      <div
        v-if="$slots.actions || onRetry !== undefined || autoReconnect"
        class="v6-offline-skeleton__actions"
      >
        <slot name="actions" />
        <a-button
          v-if="onRetry !== undefined"
          :loading="retrying"
          :size="compact ? 'small' : 'middle'"
          @click="handleRetry"
        >
          {{ retryText }}
        </a-button>
        <a-button
          v-if="autoReconnect && countdownCancelled"
          type="text"
          size="small"
          @click="restartCountdown"
        >
          重新连接
        </a-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { DisconnectOutlined } from '@ant-design/icons-vue'

interface Props {
  message?: string
  onRetry?: () => void | Promise<void>
  retryText?: string
  title?: string
  compact?: boolean
  diagnosticInfo?: string
  reconnectCountdown?: number
  autoReconnect?: boolean
  countdownText?: string
}

const props = withDefaults(defineProps<Props>(), {
  message: '',
  onRetry: undefined,
  retryText: '重试',
  title: '当前处于离线状态',
  compact: false,
  diagnosticInfo: '',
  reconnectCountdown: undefined,
  autoReconnect: false,
  countdownText: '秒后自动重连',
})

const emit = defineEmits<{
  reconnect: []
}>()

const retrying = ref(false)
const currentCountdown = ref(props.reconnectCountdown)
const countdownCancelled = ref(false)
let countdownTimer: ReturnType<typeof setInterval> | null = null
let countdownGeneration = 0
let isUnmounted = false

const resolvedCountdownText = computed(() => {
  if (currentCountdown.value === undefined || currentCountdown.value <= 0) return ''
  return `${currentCountdown.value} ${props.countdownText}`
})

const clearCountdownTimer = () => {
  if (countdownTimer) {
    clearInterval(countdownTimer)
    countdownTimer = null
  }
}

const startCountdown = () => {
  if (isUnmounted) return

  const myGeneration = ++countdownGeneration
  clearCountdownTimer()
  countdownCancelled.value = false
  currentCountdown.value = props.reconnectCountdown

  if (!props.autoReconnect || currentCountdown.value === undefined || currentCountdown.value <= 0) {
    return
  }

  countdownTimer = setInterval(() => {
    if (isUnmounted || myGeneration !== countdownGeneration) {
      clearCountdownTimer()
      return
    }
    if (currentCountdown.value === undefined) return
    currentCountdown.value -= 1
    if (currentCountdown.value <= 0) {
      clearCountdownTimer()
      emit('reconnect')
      if (props.onRetry) {
        void handleRetry()
      }
    }
  }, 1000)
}

const restartCountdown = () => {
  if (isUnmounted) return
  startCountdown()
}

const cancelCountdown = () => {
  countdownGeneration++
  clearCountdownTimer()
  countdownCancelled.value = true
}

const handleRetry = async () => {
  if (!props.onRetry || retrying.value || isUnmounted) return
  cancelCountdown()
  retrying.value = true
  try {
    await props.onRetry()
  } finally {
    if (!isUnmounted) {
      retrying.value = false
    }
  }
}

watch(
  () => props.reconnectCountdown,
  (newVal, oldVal) => {
    if (isUnmounted) return
    if (newVal !== undefined && newVal > 0 && props.autoReconnect && newVal !== oldVal) {
      startCountdown()
    }
  },
  { immediate: true }
)

onBeforeUnmount(() => {
  isUnmounted = true
  countdownGeneration++
  clearCountdownTimer()
})
</script>

<style scoped>
.v6-offline-skeleton {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--v6-space-6);
  border: 1px solid var(--v6-color-border-subtle);
  border-radius: var(--v6-radius-card);
  background: var(--v6-color-surface);
  transition: padding 0.2s ease;
}

.v6-offline-skeleton--compact {
  padding: var(--v6-space-3) var(--v6-space-4);
}

.v6-offline-skeleton__body {
  display: flex;
  align-items: center;
  gap: var(--v6-space-3);
  max-width: 480px;
  width: 100%;
  transition: gap 0.2s ease;
}

.v6-offline-skeleton--compact .v6-offline-skeleton__body {
  gap: var(--v6-space-2);
}

.v6-offline-skeleton__icon {
  font-size: 24px;
  color: var(--v6-color-warning);
  flex-shrink: 0;
  transition: font-size 0.2s ease;
}

.v6-offline-skeleton--compact .v6-offline-skeleton__icon {
  font-size: 18px;
}

.v6-offline-skeleton__text {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.v6-offline-skeleton__title {
  margin: 0;
  font-size: 14px;
  font-weight: 500;
  color: var(--v6-color-text);
  transition: font-size 0.2s ease;
}

.v6-offline-skeleton--compact .v6-offline-skeleton__title {
  font-size: 13px;
}

.v6-offline-skeleton__message {
  margin: 0;
  font-size: 13px;
  color: var(--v6-color-text-secondary);
  line-height: 1.5;
  transition: font-size 0.2s ease;
}

.v6-offline-skeleton--compact .v6-offline-skeleton__message {
  font-size: 12px;
}

.v6-offline-skeleton__diagnostic {
  margin: 0;
  font-size: 12px;
  color: var(--v6-color-text-tertiary);
  font-family: monospace;
  word-break: break-all;
}

.v6-offline-skeleton__countdown {
  margin: var(--v6-space-1) 0 0;
  font-size: 12px;
  color: var(--v6-color-info);
}

.v6-offline-skeleton__actions {
  display: flex;
  align-items: center;
  gap: var(--v6-space-2);
  flex-shrink: 0;
}

/* 低性能模式 / reduced-motion 下去除过渡 */
:root[data-perf-mode='low'] .v6-offline-skeleton,
:root[data-perf-mode='low'] .v6-offline-skeleton__body,
:root[data-perf-mode='low'] .v6-offline-skeleton__icon,
:root[data-perf-mode='low'] .v6-offline-skeleton__title,
:root[data-perf-mode='low'] .v6-offline-skeleton__message {
  transition: none;
}

@media (prefers-reduced-motion: reduce) {
  .v6-offline-skeleton,
  .v6-offline-skeleton__body,
  .v6-offline-skeleton__icon,
  .v6-offline-skeleton__title,
  .v6-offline-skeleton__message {
    transition: none;
  }
}
</style>
