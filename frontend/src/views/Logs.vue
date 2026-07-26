<template>
  <div class="logs-page">
    <PageHeader
      title="日志"
      subtitle="查看前后端运行日志，筛选问题并导出诊断信息"
      compact
      transparent
    />

    <section class="logs-panel" aria-label="日志查看器">
      <div class="logs-toolbar-wrap">
        <LogToolbar
          v-model:source="source"
          v-model:level="levelFilter"
          v-model:keyword="keywordFilter"
          :is-realtime="isRealtime"
          :is-paused="isPaused"
          :exporting="exporting"
          :refreshing="loading"
          :can-copy="filteredLines.length > 0"
          :can-clear="rawLines.length > 0"
          @refresh="handleRefresh"
          @toggle-realtime="toggleRealtime"
          @toggle-pause="togglePause"
          @copy="handleCopy"
          @clear="handleClear"
          @export="handleExport"
        />
      </div>

      <div class="logs-main">
        <a-spin :spinning="loading" tip="加载日志中...">
          <ErrorState
            v-if="error && !loading"
            class="logs-error-state"
            title="日志加载失败"
            :description="error"
            :on-retry="load"
          />

          <EmptyState
            v-else-if="filteredLines.length === 0 && !loading"
            class="logs-empty-state"
            title="暂无日志"
            :description="emptyDescription"
          />

          <LogLineList
            v-else
            ref="logListRef"
            :lines="filteredLines"
            :keyword="keywordFilter"
            :paused="isPaused"
            :auto-scroll="isRealtime"
          />
        </a-spin>
      </div>

      <footer class="logs-footer">
        <span class="footer-stat">源文件：{{ fileName }}</span>
        <span class="footer-stat">显示 {{ filteredLines.length }} / {{ rawLines.length }} 行</span>
        <span v-if="connectionState === 'reconnecting'" class="footer-stat footer-reconnecting">
          重连中 ({{ retryCount }}/5)...
          <a-button size="small" type="link" @click="retry">立即重试</a-button>
        </span>
        <span
          v-else-if="connectionState === 'disconnected'"
          class="footer-stat footer-disconnected"
        >
          已断开
          <a-button size="small" type="link" @click="retry">重新连接</a-button>
        </span>
        <span v-else-if="isRealtime && !isPaused" class="footer-stat footer-live">
          <span class="live-dot" aria-hidden="true" />
          实时刷新中
        </span>
        <span v-else-if="isPaused" class="footer-stat footer-paused">滚动已暂停</span>
        <span v-else-if="viewCleared" class="footer-stat">视图已清空</span>
      </footer>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { message } from 'ant-design-vue'
import LogToolbar from './Logs/components/LogToolbar.vue'
import LogLineList from './Logs/components/LogLineList.vue'
import PageHeader from '@/components/mac/PageHeader.vue'
import EmptyState from '@/components/v6/EmptyState.vue'
import ErrorState from '@/components/v6/ErrorState.vue'
import { useLogViewer } from './Logs/useLogViewer'

const logger = window.electronAPI.getLogger('日志查看')

const logListRef = ref<InstanceType<typeof LogLineList> | null>(null)
const exporting = ref(false)

const {
  source,
  loading,
  error,
  isRealtime,
  isPaused,
  viewCleared,
  keywordFilter,
  levelFilter,
  connectionState,
  retryCount,
  rawLines,
  filteredLines,
  fileName,
  load,
  retry,
  toggleRealtime,
  togglePause,
  clearView,
  exportLogs,
  copyLines,
} = useLogViewer()

const emptyDescription = computed(() => {
  if (viewCleared.value) {
    return '当前视图已清空，磁盘日志未被删除；点击刷新可重新读取。'
  }
  if (rawLines.value.length === 0) {
    return '当前日志文件为空，或尚未生成日志。'
  }
  if (keywordFilter.value || levelFilter.value) {
    return '没有匹配当前筛选条件的日志，请调整关键词或级别。'
  }
  return '暂无日志。'
})

const handleRefresh = async () => {
  await load()
  logListRef.value?.scrollToBottom()
}

const handleClear = () => {
  clearView()
  message.success('已清空当前日志视图，磁盘日志未被删除')
}

const handleCopy = async () => {
  const ok = await copyLines(filteredLines.value)
  if (ok) {
    message.success(`已复制 ${filteredLines.value.length} 行日志`)
    logger.info(`复制日志 ${filteredLines.value.length} 行`)
  } else {
    message.error('复制失败')
    logger.error('复制日志失败')
  }
}

const handleExport = async () => {
  exporting.value = true
  try {
    const result = await exportLogs()
    if (result.success) {
      message.success(result.message || '日志导出成功')
      logger.info(`日志导出成功: ${result.zipPath}`)
    } else {
      const msg = result.error || '日志导出失败'
      message.error(msg)
      logger.error(`导出日志失败: ${msg}`)
    }
  } finally {
    exporting.value = false
  }
}
</script>

<style scoped>
.logs-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
  overflow: hidden;
  background: var(--v6-color-window);
}

.logs-panel {
  display: flex;
  flex: 1;
  min-height: 0;
  flex-direction: column;
  margin: var(--v6-space-3) var(--v6-content-padding-inline) var(--v6-space-5);
  overflow: hidden;
  border: 1px solid var(--v6-color-border-subtle);
  border-radius: var(--v6-radius-card);
  background: color-mix(in srgb, var(--v6-color-surface) 88%, transparent);
  box-shadow: var(--v6-shadow-card);
  backdrop-filter: blur(18px) saturate(1.08);
}

.logs-toolbar-wrap {
  flex-shrink: 0;
  padding: var(--v6-space-3);
  border-bottom: 1px solid var(--v6-color-border-subtle);
}

.logs-main {
  display: flex;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.logs-main :deep(.ant-spin-nested-loading),
.logs-main :deep(.ant-spin-container) {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.logs-error-state,
.logs-empty-state {
  flex: 1;
  min-height: 0;
}

.logs-footer {
  display: flex;
  align-items: center;
  gap: var(--v6-space-4);
  flex-shrink: 0;
  min-height: 32px;
  padding: var(--v6-space-1) var(--v6-space-3);
  border-top: 1px solid var(--v6-color-border-subtle);
  font-size: var(--v6-font-size-xs);
  color: var(--v6-color-text-tertiary);
  flex-wrap: wrap;
}

.footer-stat {
  display: inline-flex;
  align-items: center;
  gap: var(--v6-space-1);
}

.footer-live {
  color: var(--v6-color-success);
}

.footer-paused {
  color: var(--v6-color-warning);
}

.footer-disconnected {
  color: var(--v6-color-error);
}

.footer-reconnecting {
  color: var(--v6-color-warning);
}

.live-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
  animation: log-live-pulse 1.2s ease-in-out infinite;
}

@keyframes log-live-pulse {
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

/* 低性能模式 / reduced-motion */
:root[data-perf-mode='low'] .live-dot {
  animation: none;
}

:root[data-perf-mode='low'] .logs-panel {
  background: var(--v6-color-surface);
  box-shadow: none;
  backdrop-filter: none;
}

@media (prefers-reduced-motion: reduce) {
  .live-dot {
    animation: none;
  }
}
</style>
