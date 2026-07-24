<template>
  <div class="v6-offline-skeleton" role="alert" aria-live="assertive">
    <div class="v6-offline-skeleton__body">
      <DisconnectOutlined class="v6-offline-skeleton__icon" aria-hidden="true" />
      <div class="v6-offline-skeleton__text">
        <p class="v6-offline-skeleton__title">{{ title }}</p>
        <p v-if="message" class="v6-offline-skeleton__message">{{ message }}</p>
      </div>
      <a-button v-if="onRetry !== undefined" :loading="retrying" size="small" @click="handleRetry">
        {{ retryText }}
      </a-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { DisconnectOutlined } from '@ant-design/icons-vue'

interface Props {
  message?: string
  onRetry?: () => void | Promise<void>
  retryText?: string
  title?: string
}

const props = withDefaults(defineProps<Props>(), {
  message: '',
  onRetry: undefined,
  retryText: '重试',
  title: '当前处于离线状态',
})

const retrying = ref(false)

const handleRetry = async () => {
  if (!props.onRetry || retrying.value) return
  retrying.value = true
  try {
    await props.onRetry()
  } finally {
    retrying.value = false
  }
}
</script>

<style scoped>
.v6-offline-skeleton {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--v6-space-6) var(--v6-space-6);
  border: 1px solid var(--v6-color-border-subtle);
  border-radius: var(--v6-radius-card);
  background: var(--v6-color-surface);
}

.v6-offline-skeleton__body {
  display: flex;
  align-items: center;
  gap: var(--v6-space-3);
  max-width: 480px;
}

.v6-offline-skeleton__icon {
  font-size: 24px;
  color: var(--v6-color-text-tertiary);
  flex-shrink: 0;
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
}

.v6-offline-skeleton__message {
  margin: 0;
  font-size: 13px;
  color: var(--v6-color-text-secondary);
  line-height: 1.5;
}
</style>
