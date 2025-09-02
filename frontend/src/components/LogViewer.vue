<template>
  <div class="log-viewer">
    <div class="log-header">
      <div class="log-controls">
        <a-select v-model:value="selectedLevel" style="width: 120px" @change="filterLogs">
          <a-select-option value="all">所有级别</a-select-option>
          <a-select-option value="debug">Debug</a-select-option>
          <a-select-option value="info">Info</a-select-option>
          <a-select-option value="warn">Warn</a-select-option>
          <a-select-option value="error">Error</a-select-option>
        </a-select>

        <a-input-search
          v-model:value="searchText"
          placeholder="搜索日志..."
          style="width: 200px"
          @search="filterLogs"
          @change="filterLogs"
        />

        <a-button @click="clearLogs" danger>
          <template #icon>
            <DeleteOutlined />
          </template>
          清空日志
        </a-button>

        <a-button @click="downloadLogs" type="primary">
          <template #icon>
            <DownloadOutlined />
          </template>
          导出日志
        </a-button>

        <a-button @click="toggleAutoScroll" :type="autoScroll ? 'primary' : 'default'">
          <template #icon>
            <VerticalAlignBottomOutlined />
          </template>
          自动滚动
        </a-button>
      </div>

      <div class="log-stats">总计: {{ filteredLogs.length }} 条日志</div>
    </div>

    <div ref="logContainer" class="log-container" @scroll="handleScroll">
      <div
        v-for="(log, index) in filteredLogs"
        :key="index"
        class="log-entry"
        :class="[`log-${log.level}`, { 'log-highlight': highlightedIndex === index }]"
      >
        <div class="log-timestamp">{{ log.timestamp }}</div>
        <div class="log-level">{{ log.level.toUpperCase() }}</div>
        <div v-if="log.component" class="log-component">[{{ log.component }}]</div>
        <div class="log-message">{{ log.message }}</div>
        <div v-if="log.data" class="log-data">
          <a-button size="small" type="link" @click="toggleDataVisibility(index)">
            {{ expandedData.has(index) ? '隐藏数据' : '显示数据' }}
          </a-button>
          <pre v-if="expandedData.has(index)" class="log-data-content">{{
            JSON.stringify(log.data, null, 2)
          }}</pre>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, onMounted, onUnmounted } from 'vue'
import {
  DeleteOutlined,
  DownloadOutlined,
  VerticalAlignBottomOutlined,
} from '@ant-design/icons-vue'
import { logger, type LogEntry, type LogLevel } from '@/utils/logger'

const logContainer = ref<HTMLElement>()
const selectedLevel = ref<LogLevel | 'all'>('all')
const searchText = ref('')
const autoScroll = ref(true)
const expandedData = ref(new Set<number>())
const highlightedIndex = ref(-1)

const logs = logger.getLogs()

const filteredLogs = computed(() => {
  let filtered = logs.value

  // 按级别过滤
  if (selectedLevel.value !== 'all') {
    filtered = filtered.filter(log => log.level === selectedLevel.value)
  }

  // 按搜索文本过滤
  if (searchText.value) {
    const search = searchText.value.toLowerCase()
    filtered = filtered.filter(
      log =>
        log.message.toLowerCase().includes(search) ||
        log.component?.toLowerCase().includes(search) ||
        (log.data && JSON.stringify(log.data).toLowerCase().includes(search))
    )
  }

  return filtered
})

function filterLogs() {
  // 过滤逻辑已在computed中处理
  nextTick(() => {
    if (autoScroll.value) {
      scrollToBottom()
    }
  })
}

function clearLogs() {
  logger.clearLogs()
  expandedData.value.clear()
}

function downloadLogs() {
  logger.downloadLogs()
}

function toggleAutoScroll() {
  autoScroll.value = !autoScroll.value
  if (autoScroll.value) {
    scrollToBottom()
  }
}

function toggleDataVisibility(index: number) {
  if (expandedData.value.has(index)) {
    expandedData.value.delete(index)
  } else {
    expandedData.value.add(index)
  }
}

function scrollToBottom() {
  if (logContainer.value) {
    logContainer.value.scrollTop = logContainer.value.scrollHeight
  }
}

function handleScroll() {
  if (!logContainer.value) return

  const { scrollTop, scrollHeight, clientHeight } = logContainer.value
  const isAtBottom = scrollTop + clientHeight >= scrollHeight - 10

  if (!isAtBottom) {
    autoScroll.value = false
  }
}

// 监听新日志添加
let unwatchLogs: (() => void) | null = null

onMounted(() => {
  // 初始滚动到底部
  nextTick(() => {
    scrollToBottom()
  })

  // 监听日志变化
  unwatchLogs =
    logs.value && typeof logs.value === 'object' && 'length' in logs.value
      ? () => {} // 如果logs是响应式的，Vue会自动处理
      : null
})

onUnmounted(() => {
  if (unwatchLogs) {
    unwatchLogs()
  }
})

// 监听日志变化，自动滚动
const prevLogsLength = ref(logs.value.length)
const checkForNewLogs = () => {
  if (logs.value.length > prevLogsLength.value) {
    prevLogsLength.value = logs.value.length
    if (autoScroll.value) {
      nextTick(() => {
        scrollToBottom()
      })
    }
  }
}

// 定期检查新日志
const logCheckInterval = setInterval(checkForNewLogs, 100)

onUnmounted(() => {
  clearInterval(logCheckInterval)
})
</script>

<style scoped>
.log-viewer {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--ant-color-bg-container);
  border-radius: 8px;
  overflow: hidden;
}

.log-header {
  padding: 16px;
  border-bottom: 1px solid var(--ant-color-border);
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}

.log-controls {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.log-stats {
  font-size: 14px;
  color: var(--ant-color-text-secondary);
}

.log-container {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 12px;
  line-height: 1.4;
}

.log-entry {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 4px 8px;
  border-radius: 4px;
  margin-bottom: 2px;
  word-break: break-all;
}

.log-entry:hover {

}

.log-highlight {
  background: var(--ant-color-primary-bg) !important;
}

.log-timestamp {
  color: var(--ant-color-text-tertiary);
  white-space: nowrap;
  min-width: 140px;
}

.log-level {
  font-weight: bold;
  min-width: 50px;
  text-align: center;
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 10px;
}

.log-debug .log-level {
  background: var(--ant-color-fill-secondary);
  color: var(--ant-color-text-secondary);
}

.log-info .log-level {
  background: var(--ant-color-info-bg);
  color: var(--ant-color-info);
}

.log-warn .log-level {
  background: var(--ant-color-warning-bg);
  color: var(--ant-color-warning);
}

.log-error .log-level {
  background: var(--ant-color-error-bg);
  color: var(--ant-color-error);
}

.log-component {
  color: var(--ant-color-primary);
  font-weight: 500;
  white-space: nowrap;
}

.log-message {
  flex: 1;
  color: var(--ant-color-text);
}

.log-data {
  margin-top: 4px;
  width: 100%;
}

.log-data-content {

  padding: 8px;
  border-radius: 4px;
  margin-top: 4px;
  font-size: 11px;
  overflow-x: auto;
}

@media (max-width: 768px) {
  .log-header {
    flex-direction: column;
    align-items: stretch;
  }

  .log-controls {
    justify-content: center;
  }

  .log-entry {
    flex-direction: column;
    align-items: stretch;
    gap: 4px;
  }

  .log-timestamp,
  .log-level,
  .log-component {
    min-width: auto;
  }
}
</style>