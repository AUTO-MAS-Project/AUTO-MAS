<template>
  <a-card class="home-status-card" :bordered="false">
    <div class="status-heading">
      <span class="running-badge" :class="{ 'running-badge--warning': !isReady || hasErrors }">
        <span class="running-dot" aria-hidden="true"></span>
        {{ isReady && !hasErrors ? '运行中' : '需要关注' }}
      </span>
    </div>

    <div class="status-grid">
      <div class="status-cell">
        <strong class="status-value">{{ backendStatusLabel }}</strong>
        <span class="status-label">后端服务</span>
      </div>
      <div class="status-cell">
        <strong class="status-value">{{ wsStatus }}</strong>
        <span class="status-label">WebSocket</span>
        <button
          v-if="showReconnect"
          type="button"
          class="reconnect-btn"
          :disabled="reconnecting"
          @click="handleReconnect"
        >
          {{ reconnecting ? '重连中…' : '重新连接' }}
        </button>
      </div>
      <div class="status-cell">
        <strong class="status-value">{{ queuedTasks }}</strong>
        <span class="status-label">队列任务</span>
      </div>
      <div class="status-cell">
        <strong class="status-value">{{ recentResults }}</strong>
        <span class="status-label">近期结果</span>
      </div>
    </div>

    <div v-if="hasErrors" class="status-hint">
      <ExclamationCircleOutlined class="hint-icon" />
      <span>检测到代理错误，请检查历史记录或日志</span>
    </div>
  </a-card>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ExclamationCircleOutlined } from '@ant-design/icons-vue'
import { useWebSocket } from '@/composables/useWebSocket'

interface Props {
  wsStatus: string
  backendStatus: string
  isReady: boolean
  hasErrors: boolean
  queuedTasks: number
  recentResults: number
}

const props = defineProps<Props>()

const backendStatusLabel = computed(() => {
  const map: Record<string, string> = {
    running: '运行中',
    starting: '启动中',
    stopped: '已停止',
    error: '错误',
    unknown: '未知',
  }
  return map[props.backendStatus] || props.backendStatus
})

// 手动重连入口。此前 manualReconnect 只在 devtools 暴露，主界面对
// suspended 挂起态（1009 消息超限 / 4001 连接被替换后停止自动重连）
// 没有任何用户可见的恢复入口。
const { state: wsState, manualReconnect } = useWebSocket()
const reconnecting = ref(false)

const showReconnect = computed(() => {
  const state = wsState.value
  // suspended：自动重连已停止，只有用户显式 force 重连才能恢复
  if (state === 'suspended') return true
  // closed 为应用退出终态，open/connecting 无需入口
  if (state === 'open' || state === 'connecting' || state === 'closed') return false
  // 断开且后端已进入 error（多次自动重连/重启后端均失败）时提供兜底入口
  return props.backendStatus === 'error'
})

const handleReconnect = async () => {
  if (reconnecting.value) return
  reconnecting.value = true
  try {
    // manualReconnect 内部走 connect({ force: true })，可从 suspended 恢复
    await manualReconnect()
  } finally {
    reconnecting.value = false
  }
}
</script>

<style scoped>
.home-status-card {
  border-radius: var(--v6-radius-card);
  background: var(--v6-vibrancy-content);
  border: 1px solid var(--v6-color-border-subtle);
  box-shadow: var(--v6-shadow-xs);
  backdrop-filter: var(--v6-backdrop-vibrancy);
  -webkit-backdrop-filter: var(--v6-backdrop-vibrancy);
}

.home-status-card :deep(.ant-card-body) {
  display: flex;
  align-items: center;
  gap: 18px;
  padding: 13px 18px;
}

.status-heading {
  display: flex;
  align-items: center;
  flex: 0 0 auto;
}

.running-badge {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 5px 11px;
  border-radius: 999px;
  background: var(--v6-color-success-bg);
  color: var(--v6-color-success);
  font-size: 12px;
  font-weight: 500;
}

.running-badge--warning {
  background: var(--v6-color-warning-bg);
  color: var(--v6-color-warning);
}

.running-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: currentColor;
}

.status-grid {
  flex: 1;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  align-items: stretch;
}

.status-cell {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 5px;
  min-height: 42px;
  padding-inline: 16px;
  min-width: 0;
}

.status-cell + .status-cell::before {
  position: absolute;
  left: 0;
  top: 8px;
  bottom: 8px;
  width: 1px;
  content: '';
  background: var(--v6-color-border-subtle);
}

.status-value {
  max-width: 100%;
  overflow: hidden;
  color: var(--v6-color-text);
  font-size: clamp(16px, 1.5vw, 20px);
  font-weight: 700;
  line-height: 1.15;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.status-label {
  font-size: 12px;
  color: var(--v6-color-text-secondary);
  font-weight: 400;
}

.reconnect-btn {
  margin-top: var(--v6-space-0-5);
  padding: 1px 10px;
  border: 1px solid var(--v6-color-info-border);
  border-radius: 999px;
  background: var(--v6-color-info-bg);
  color: var(--v6-color-info);
  font-size: var(--v6-font-size-sm);
  font-weight: var(--v6-font-weight-medium);
  line-height: 18px;
  cursor: pointer;
  transition:
    background-color 0.15s ease,
    color 0.15s ease;
}

.reconnect-btn:hover:not(:disabled) {
  background: var(--v6-color-primary);
  color: var(--v6-color-text-inverse);
}

.reconnect-btn:disabled {
  color: var(--v6-color-text-disabled);
  cursor: default;
}

.status-hint {
  display: flex;
  align-items: center;
  gap: var(--v6-space-2);
  margin-left: auto;
  padding: var(--v6-space-2) var(--v6-space-3);
  background: var(--v6-color-warning-bg);
  border: 1px solid var(--v6-color-warning-border);
  border-radius: var(--v6-radius-md);
  font-size: 13px;
  color: var(--v6-color-warning);
}

.hint-icon {
  flex-shrink: 0;
}

@container home-layout (max-width: 560px) {
  .home-status-card :deep(.ant-card-body) {
    align-items: stretch;
    flex-direction: column;
  }

  .status-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    row-gap: 16px;
  }

  .status-cell:nth-child(3)::before {
    display: none;
  }
}
</style>
