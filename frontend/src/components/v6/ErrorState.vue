<template>
  <div
    class="v6-error-state"
    :class="{ 'v6-error-state--fullscreen': fullscreen }"
    role="alert"
    aria-live="assertive"
  >
    <a-result status="error" :title="resolvedTitle" :sub-title="description">
      <template v-if="errorCode || error" #subtitle>
        <div class="v6-error-state__subtitle-wrapper">
          <p v-if="description" class="v6-error-state__description">{{ description }}</p>
          <p v-if="errorCode" class="v6-error-state__code">
            <span class="v6-error-state__code-label">错误代码：</span>
            <code class="v6-error-state__code-value">{{ errorCode }}</code>
          </p>
        </div>
      </template>
      <template v-if="$slots.extra || onRetry !== undefined || error" #extra>
        <div class="v6-error-state__actions">
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
          <a-button
            v-if="error"
            type="text"
            size="small"
            @click="toggleDetails"
            :aria-expanded="showDetails"
            aria-controls="error-details"
          >
            {{ showDetails ? '隐藏详情' : '查看详情' }}
          </a-button>
          <a-button
            v-if="error"
            type="text"
            size="small"
            :icon="copied ? CheckOutlined : CopyOutlined"
            @click="copyError"
            :aria-label="copied ? '已复制' : '复制错误信息'"
          >
            {{ copied ? '已复制' : '复制' }}
          </a-button>
        </div>
      </template>
    </a-result>
    <transition
      name="v6-error-state-details"
      @enter="onEnter"
      @after-enter="onAfterEnter"
      @leave="onLeave"
      @after-leave="onAfterLeave"
    >
      <div
        v-if="error && showDetails"
        id="error-details"
        class="v6-error-state__details"
        role="region"
        aria-label="错误详情"
      >
        <pre class="v6-error-state__details-content"><code>{{ formattedError }}</code></pre>
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { CopyOutlined, CheckOutlined } from '@ant-design/icons-vue'

interface Props {
  title?: string
  description?: string
  onRetry?: () => void | Promise<void>
  retryText?: string
  error?: Error | string | unknown
  errorCode?: string | number
  fullscreen?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  title: '加载失败',
  description: '请稍后重试，或联系管理员。',
  onRetry: undefined,
  retryText: '重试',
  error: undefined,
  errorCode: undefined,
  fullscreen: false,
})

const retrying = ref(false)
const showDetails = ref(false)
const copied = ref(false)

const resolvedTitle = computed(() => {
  if (props.errorCode) {
    return `${props.title} (${props.errorCode})`
  }
  return props.title
})

const formattedError = computed(() => {
  if (!props.error) return ''
  if (typeof props.error === 'string') return props.error
  if (props.error instanceof Error) {
    return props.error.stack || props.error.message
  }
  try {
    return JSON.stringify(props.error, null, 2)
  } catch {
    return String(props.error)
  }
})

const handleRetry = async () => {
  if (!props.onRetry || retrying.value) return
  retrying.value = true
  try {
    await props.onRetry()
  } finally {
    retrying.value = false
  }
}

const toggleDetails = () => {
  showDetails.value = !showDetails.value
}

const copyError = async () => {
  if (!formattedError.value) return
  try {
    await navigator.clipboard.writeText(formattedError.value)
    copied.value = true
    setTimeout(() => {
      copied.value = false
    }, 2000)
  } catch {
    const textarea = document.createElement('textarea')
    textarea.value = formattedError.value
    document.body.appendChild(textarea)
    textarea.select()
    document.execCommand('copy')
    document.body.removeChild(textarea)
    copied.value = true
    setTimeout(() => {
      copied.value = false
    }, 2000)
  }
}

const onEnter = (el: Element) => {
  const element = el as HTMLElement
  element.style.height = '0'
  element.style.opacity = '0'
}

const onAfterEnter = (el: Element) => {
  const element = el as HTMLElement
  element.style.height = 'auto'
  element.style.opacity = '1'
}

const onLeave = (el: Element) => {
  const element = el as HTMLElement
  element.style.height = element.offsetHeight + 'px'
  element.style.opacity = '1'
  requestAnimationFrame(() => {
    element.style.height = '0'
    element.style.opacity = '0'
  })
}

const onAfterLeave = (el: Element) => {
  const element = el as HTMLElement
  element.style.height = ''
  element.style.opacity = ''
}
</script>

<style scoped>
.v6-error-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--v6-space-8) var(--v6-space-6);
  color: var(--v6-color-text);
}

.v6-error-state--fullscreen {
  position: fixed;
  inset: 0;
  z-index: 1000;
  background: var(--v6-color-window);
  padding: var(--v6-space-8);
}

.v6-error-state__subtitle-wrapper {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--v6-space-1);
}

.v6-error-state__description {
  margin: 0;
}

.v6-error-state__code {
  margin: 0;
  font-size: 12px;
  color: var(--v6-color-text-tertiary);
}

.v6-error-state__code-label {
  color: var(--v6-color-text-tertiary);
}

.v6-error-state__code-value {
  font-family: monospace;
  padding: 1px var(--v6-space-1);
  background: var(--v6-color-surface-elevated);
  border-radius: var(--v6-radius-sm);
  color: var(--v6-color-error);
}

.v6-error-state__actions {
  display: flex;
  align-items: center;
  gap: var(--v6-space-2);
  flex-wrap: wrap;
  justify-content: center;
}

.v6-error-state__details {
  width: 100%;
  max-width: 600px;
  margin-top: var(--v6-space-4);
  overflow: hidden;
  transition:
    height 0.3s ease,
    opacity 0.3s ease;
}

.v6-error-state__details-content {
  margin: 0;
  padding: var(--v6-space-3);
  background: var(--v6-color-surface-elevated);
  border-radius: var(--v6-radius-card);
  font-size: 12px;
  line-height: 1.6;
  color: var(--v6-color-text-secondary);
  white-space: pre-wrap;
  word-break: break-all;
  overflow-x: auto;
  max-height: 300px;
  overflow-y: auto;
}

.v6-error-state :deep(.ant-result-title) {
  color: var(--v6-color-text);
}

.v6-error-state :deep(.ant-result-subtitle) {
  color: var(--v6-color-text-secondary);
  font-size: 13px;
  line-height: 1.5;
}

/* 低性能模式 / reduced-motion 下去除过渡 */
:root[data-perf-mode='low'] .v6-error-state__details {
  transition: none;
}

@media (prefers-reduced-motion: reduce) {
  .v6-error-state__details {
    transition: none;
  }
}
</style>
