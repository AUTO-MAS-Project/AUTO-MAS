<template>
  <div class="v6-error-state" role="alert" aria-live="assertive">
    <a-result status="error" :title="title" :sub-title="description">
      <template v-if="$slots.extra || onRetry !== undefined" #extra>
        <slot name="extra">
          <a-button
            v-if="onRetry !== undefined"
            type="primary"
            :loading="retrying"
            @click="handleRetry"
          >
            {{ retryText }}
          </a-button>
        </slot>
      </template>
    </a-result>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

interface Props {
  title?: string
  description?: string
  onRetry?: () => void | Promise<void>
  retryText?: string
}

const props = withDefaults(defineProps<Props>(), {
  title: '加载失败',
  description: '请稍后重试，或联系管理员。',
  onRetry: undefined,
  retryText: '重试',
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
.v6-error-state {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--v6-space-8) var(--v6-space-6);
  color: var(--v6-color-text);
}

.v6-error-state :deep(.ant-result-title) {
  color: var(--v6-color-text);
}

.v6-error-state :deep(.ant-result-subtitle) {
  color: var(--v6-color-text-secondary);
  font-size: 13px;
  line-height: 1.5;
}
</style>
