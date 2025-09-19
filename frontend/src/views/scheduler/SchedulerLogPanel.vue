<template>
  <div class="log-panel">
    <a-card class="section-card" :bordered="false">
      <template #title>
        <div class="section-header">
          <h3>日志</h3>
          <div class="log-controls">
            <a-space size="small">
              <a-button @click="clearLogs" :disabled="logs.length === 0" size="small">
                清空日志
              </a-button>
              <a-button @click="scrollToBottom" :disabled="logs.length === 0" size="small">
                滚动到底部
              </a-button>
            </a-space>
          </div>
        </div>
      </template>
      <div class="log-content" :ref="setLogRef" @scroll="onScroll">
        <div v-if="logs.length === 0" class="empty-state-mini">
          <a-empty description="暂无日志信息" />
        </div>
        <div
          v-for="(log, index) in logs"
          :key="`${tabKey}-${index}-${log.timestamp}`"
          :class="['log-line', `log-${log.type}`]"
        >
          <span class="log-time">{{ log.time }}</span>
          <span class="log-message">{{ log.message }}</span>
        </div>
      </div>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { nextTick } from 'vue'
import type { LogEntry } from './schedulerConstants'

interface Props {
  logs: LogEntry[]
  tabKey: string
  isLogAtBottom: boolean
}

interface Emits {
  (e: 'scroll', isAtBottom: boolean): void

  (e: 'setRef', el: HTMLElement | null, key: string): void

  (e: 'clearLogs'): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const setLogRef = (el: HTMLElement | null) => {
  emit('setRef', el, props.tabKey)
}

const onScroll = (event: Event) => {
  const el = event.target as HTMLElement
  if (!el) return

  const threshold = 5
  const isAtBottom = el.scrollHeight - el.scrollTop - el.clientHeight <= threshold
  emit('scroll', isAtBottom)
}

const scrollToBottom = () => {
  nextTick(() => {
    const el = document.querySelector(
      `[data-tab-key="${props.tabKey}"] .log-content`
    ) as HTMLElement
    if (el) {
      el.scrollTo({
        top: el.scrollHeight,
        behavior: 'smooth',
      })
    }
  })
}

const clearLogs = () => {
  emit('clearLogs')
}
</script>

<style scoped>
.log-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.section-card {
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  border: 1px solid var(--ant-color-border-secondary);
  height: 100%;
}

.section-card :deep(.ant-card-head) {
  border-bottom: 1px solid var(--ant-color-border-secondary);
  padding: 0 16px;
  border-radius: 12px 12px 0 0;
}

.section-card :deep(.ant-card-body) {
  padding: 0;
  height: calc(100% - 52px);
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.section-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--ant-color-text-heading);
}

.log-controls {
  display: flex;
  gap: 8px;
}

.log-content {
  height: 100%;
  padding: 16px;
  background: var(--ant-color-bg-container);
  overflow-y: auto;
  font-family: 'Courier New', monospace;
  font-size: 13px;
  line-height: 1.5;
}

.empty-state-mini {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  min-height: 300px;
}

.log-line {
  margin-bottom: 4px;
  padding: 4px 8px;
  border-radius: 4px;
  word-wrap: break-word;
}

.log-time {
  color: var(--ant-color-text-secondary);
  margin-right: 12px;
  font-weight: 500;
}

.log-message {
  color: var(--ant-color-text);
}

.log-info {
  background-color: transparent;
}

.log-error {
  background-color: var(--ant-color-error-bg);
  border-left: 4px solid var(--ant-color-error);
}

.log-error .log-message {
  color: var(--ant-color-error-text);
}

.log-warning {
  background-color: var(--ant-color-warning-bg);
  border-left: 4px solid var(--ant-color-warning);
}

.log-warning .log-message {
  color: var(--ant-color-warning-text);
}

.log-success {
  background-color: var(--ant-color-success-bg);
  border-left: 4px solid var(--ant-color-success);
}

.log-success .log-message {
  color: var(--ant-color-success-text);
}

/* 暗色模式适配 */
@media (prefers-color-scheme: dark) {
  .section-card {
    background: var(--ant-color-bg-container, #1f1f1f);
    border: 1px solid var(--ant-color-border, #424242);
  }
  
  .section-card :deep(.ant-card-head) {
    background: var(--ant-color-bg-layout, #141414);
    border-bottom: 1px solid var(--ant-color-border, #424242);
  }
  
  .section-card :deep(.ant-card-body) {
    background: var(--ant-color-bg-container, #1f1f1f);
  }
  
  .section-header h3 {
    color: var(--ant-color-text-heading, #ffffff);
  }

  .log-content {
    background: var(--ant-color-bg-container, #1f1f1f);
  }

  .log-time {
    color: var(--ant-color-text-secondary, #bfbfbf);
  }

  .log-message {
    color: var(--ant-color-text, #ffffff);
  }

  .log-error {
    background-color: rgba(255, 77, 79, 0.1);
    border-left: 4px solid var(--ant-color-error, #ff4d4f);
  }

  .log-error .log-message {
    color: var(--ant-color-error, #ff7875);
  }

  .log-warning {
    background-color: rgba(250, 173, 20, 0.1);
    border-left: 4px solid var(--ant-color-warning, #faad14);
  }

  .log-warning .log-message {
    color: var(--ant-color-warning, #ffc53d);
  }

  .log-success {
    background-color: rgba(82, 196, 26, 0.1);
    border-left: 4px solid var(--ant-color-success, #52c41a);
  }

  .log-success .log-message {
    color: var(--ant-color-success, #73d13d);
  }
}

@media (max-width: 768px) {
  .log-content {
    padding: 12px;
  }
  
  .section-card :deep(.ant-card-head) {
    padding: 0 16px;
  }
}
</style>