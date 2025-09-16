<template>
  <div class="log-panel">
    <div class="section-header">
      <h3>日志</h3>
      <div class="log-controls">
        <a-button size="small" @click="clearLogs" :disabled="logs.length === 0">
          清空日志
        </a-button>
        <a-button size="small" @click="scrollToBottom" :disabled="logs.length === 0">
          滚动到底部
        </a-button>
      </div>
    </div>
    <div class="log-content" :ref="setLogRef" @scroll="onScroll">
      <div v-if="logs.length === 0" class="empty-state-mini">
        <img src="@/assets/NoData.png" alt="暂无数据" class="empty-image-mini" />
        <p class="empty-text-mini">暂无日志信息</p>
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

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.section-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--ant-color-text-heading);
}

.log-controls {
  display: flex;
  gap: 8px;
}

.log-content {
  flex: 1;
  padding: 12px;
  background: var(--ant-color-bg-layout);
  border: 1px solid var(--ant-color-border);
  border-radius: 6px;
  overflow-y: auto;
  max-height: 400px;
  font-family: 'Courier New', monospace;
  font-size: 12px;
  line-height: 1.4;
}

.empty-state-mini {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 200px;
  color: var(--ant-color-text-tertiary);
}

.empty-image-mini {
  width: 64px;
  height: 64px;
  opacity: 0.5;
  margin-bottom: 8px;
  filter: var(--ant-color-scheme-dark, brightness(0.8));
}

.empty-text-mini {
  margin: 0;
  font-size: 14px;
  color: var(--ant-color-text-tertiary);
}

.log-line {
  margin-bottom: 2px;
  padding: 2px 4px;
  border-radius: 2px;
  word-wrap: break-word;
}

.log-time {
  color: var(--ant-color-text-secondary);
  margin-right: 8px;
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
  border-left: 3px solid var(--ant-color-error);
}

.log-error .log-message {
  color: var(--ant-color-error-text);
}

.log-warning {
  background-color: var(--ant-color-warning-bg);
  border-left: 3px solid var(--ant-color-warning);
}

.log-warning .log-message {
  color: var(--ant-color-warning-text);
}

.log-success {
  background-color: var(--ant-color-success-bg);
  border-left: 3px solid var(--ant-color-success);
}

.log-success .log-message {
  color: var(--ant-color-success-text);
}

/* 暗色模式适配 */
@media (prefers-color-scheme: dark) {
  .section-header h3 {
    color: var(--ant-color-text-heading, #ffffff);
  }

  .log-content {
    background: var(--ant-color-bg-layout, #141414);
    border: 1px solid var(--ant-color-border, #424242);
  }

  .empty-state-mini {
    color: var(--ant-color-text-tertiary, #8c8c8c);
  }

  .empty-image-mini {
    filter: brightness(0.8);
  }

  .empty-text-mini {
    color: var(--ant-color-text-tertiary, #8c8c8c);
  }

  .log-time {
    color: var(--ant-color-text-secondary, #bfbfbf);
  }

  .log-message {
    color: var(--ant-color-text, #ffffff);
  }

  .log-error {
    background-color: rgba(255, 77, 79, 0.1);
    border-left: 3px solid var(--ant-color-error, #ff4d4f);
  }

  .log-error .log-message {
    color: var(--ant-color-error, #ff7875);
  }

  .log-warning {
    background-color: rgba(250, 173, 20, 0.1);
    border-left: 3px solid var(--ant-color-warning, #faad14);
  }

  .log-warning .log-message {
    color: var(--ant-color-warning, #ffc53d);
  }

  .log-success {
    background-color: rgba(82, 196, 26, 0.1);
    border-left: 3px solid var(--ant-color-success, #52c41a);
  }

  .log-success .log-message {
    color: var(--ant-color-success, #73d13d);
  }
}
</style>
