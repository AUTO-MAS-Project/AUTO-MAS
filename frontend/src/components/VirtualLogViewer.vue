<template>
  <div class="virtual-log-viewer">
    <!-- 工具栏 -->
    <div class="log-toolbar">
      <div class="toolbar-left">
        <a-space>
          <a-select
            v-model:value="selectedLogLevel"
            style="width: 120px"
            placeholder="日志级别"
            @change="onLogLevelChange"
          >
            <a-select-option value="">全部级别</a-select-option>
            <a-select-option v-for="level in logLevels" :key="level" :value="level">
              {{ level }}
            </a-select-option>
          </a-select>

          <a-select
            v-model:value="selectedSource"
            style="width: 120px"
            placeholder="日志来源"
            @change="onSourceChange"
          >
            <a-select-option value="">全部来源</a-select-option>
            <a-select-option v-for="source in logSources" :key="source" :value="source">
              {{ source }}
            </a-select-option>
          </a-select>

          <a-input
            v-model:value="searchKeyword"
            style="width: 200px"
            placeholder="搜索关键词"
            @input="onSearchInput"
            allow-clear
          >
            <template #prefix>
              <SearchOutlined />
            </template>
          </a-input>

          <a-checkbox
            v-model:checked="enableColorHighlight"
            @change="onColorHighlightChange"
          >
            颜色高亮
          </a-checkbox>

          <a-checkbox
            v-model:checked="autoScroll"
            @change="onAutoScrollChange"
          >
            自动滚动
          </a-checkbox>
        </a-space>
      </div>

      <div class="toolbar-right">
        <a-space>
          <a-button @click="exportLogs" :loading="exporting">
            <template #icon>
              <ExportOutlined />
            </template>
            导出
          </a-button>

          <a-button @click="clearLogs" danger>
            <template #icon>
              <DeleteOutlined />
            </template>
            清空
          </a-button>

          <a-button @click="refreshLogs" :loading="refreshing">
            <template #icon>
              <ReloadOutlined />
            </template>
            刷新
          </a-button>
        </a-space>
      </div>
    </div>

    <!-- 虚拟滚动日志列表 -->
    <div class="log-container" ref="containerRef" @scroll="onScroll">
      <div class="log-phantom" :style="{ height: `${totalHeight}px` }"></div>
      <div class="log-content" :style="{ transform: `translateY(${offsetY}px)` }">
        <div
          v-for="(log, index) in visibleLogs"
          :key="`${log.timestamp.getTime()}-${index}`"
          class="log-item"
          :class="[
            `log-level-${log.level.toLowerCase()}`,
            { 'log-item-selected': selectedLogIndex === index }
          ]"
          @click="selectLog(index)"
          @dblclick="onLogDoubleClick(index)"
        >
          <div class="log-time">{{ formatTime(log.timestamp) }}</div>
          <div class="log-level" :style="getLevelStyle(log.level)">{{ log.level }}</div>
          <div class="log-module" :style="getModuleStyle(log.module, log.source)">{{ log.module }}</div>
          <div class="log-message" v-html="highlightSearchKeyword(log.message)"></div>
        </div>
      </div>
    </div>

    <!-- 状态栏 -->
    <div class="log-status-bar">
      <div class="status-left">
        <span>总计: {{ filteredLogs.length }} 条日志</span>
        <span>已加载: {{ logs.length }} 条</span>
        <span v-if="selectedLogIndex !== null">选中: 第 {{ selectedLogIndex + 1 }} 条</span>
      </div>
      <div class="status-right">
        <span v-if="loading">加载中...</span>
        <span v-if="error" class="error-text">{{ error }}</span>
      </div>
    </div>

    <!-- 日志详情弹窗 -->
    <a-modal
      v-model:open="detailModalVisible"
      title="日志详情"
      width="800px"
      :footer="null"
    >
      <div v-if="selectedLogForDetail" class="log-detail">
        <div class="detail-row">
          <span class="detail-label">时间戳:</span>
          <span class="detail-value">{{ formatFullTime(selectedLogForDetail.timestamp) }}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">级别:</span>
          <span class="detail-value" :style="getLevelStyle(selectedLogForDetail.level)">{{ selectedLogForDetail.level }}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">来源:</span>
          <span class="detail-value">{{ selectedLogForDetail.source }}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">模块:</span>
          <span class="detail-value" :style="getModuleStyle(selectedLogForDetail.module, selectedLogForDetail.source)">{{ selectedLogForDetail.module }}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">消息:</span>
          <pre class="detail-message">{{ selectedLogForDetail.message }}</pre>
        </div>
        <div v-if="selectedLogForDetail.originalLog" class="detail-row">
          <span class="detail-label">原始日志:</span>
          <pre class="detail-original">{{ selectedLogForDetail.originalLog }}</pre>
        </div>
        <div v-if="selectedLogForDetail.metadata" class="detail-row">
          <span class="detail-label">元数据:</span>
          <pre class="detail-metadata">{{ JSON.stringify(selectedLogForDetail.metadata, null, 2) }}</pre>
        </div>
      </div>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { message } from 'ant-design-vue'
import {
  SearchOutlined,
  ExportOutlined,
  DeleteOutlined,
  ReloadOutlined
} from '@ant-design/icons-vue'
import type { ParsedLogEntry } from '@/types/log'
import { LogLevel, LogSource } from '@/types/log'
import { LogFormatter } from '../../electron/utils/logFormatter'

// Props
interface Props {
  logs?: ParsedLogEntry[]
  loading?: boolean
  error?: string
  itemHeight?: number
  bufferSize?: number
  enableVirtualScroll?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  logs: () => [],
  loading: false,
  error: '',
  itemHeight: 30,
  bufferSize: 5,
  enableVirtualScroll: true
})

// Emits
const emit = defineEmits<{
  'refresh': []
  'clear': []
  'export': [logs: ParsedLogEntry[]]
  'log-selected': [log: ParsedLogEntry, index: number]
}>()

// 响应式数据
const containerRef = ref<HTMLElement>()
const selectedLogLevel = ref<string>('')
const selectedSource = ref<string>('')
const searchKeyword = ref<string>('')
const enableColorHighlight = ref<boolean>(true)
const autoScroll = ref<boolean>(true)
const selectedLogIndex = ref<number | null>(null)
const selectedLogForDetail = ref<ParsedLogEntry | null>(null)
const detailModalVisible = ref<boolean>(false)
const exporting = ref<boolean>(false)
const refreshing = ref<boolean>(false)

// 虚拟滚动相关
const scrollTop = ref<number>(0)
const containerHeight = ref<number>(0)
const visibleStartIndex = ref<number>(0)
const visibleEndIndex = ref<number>(0)

// 日志级别和来源选项
const logLevels = Object.values(LogLevel)
const logSources = Object.values(LogSource)

// 内部日志数据
const internalLogs = ref<ParsedLogEntry[]>([])

// 监听外部日志变化
watch(() => props.logs, (newLogs) => {
  internalLogs.value = [...newLogs]
  if (autoScroll.value) {
    scrollToBottom()
  }
}, { immediate: true, deep: true })

// 计算属性
const filteredLogs = computed(() => {
  let result = internalLogs.value

  // 按级别过滤
  if (selectedLogLevel.value) {
    result = result.filter(log => log.level === selectedLogLevel.value)
  }

  // 按来源过滤
  if (selectedSource.value) {
    result = result.filter(log => log.source === selectedSource.value)
  }

  // 按关键词搜索
  if (searchKeyword.value) {
    const keyword = searchKeyword.value.toLowerCase()
    result = result.filter(log => 
      log.message.toLowerCase().includes(keyword) ||
      log.module.toLowerCase().includes(keyword) ||
      log.level.toLowerCase().includes(keyword)
    )
  }

  return result
})

// 虚拟滚动计算
const totalHeight = computed(() => {
  return filteredLogs.value.length * props.itemHeight
})

const visibleLogs = computed(() => {
  if (!props.enableVirtualScroll) {
    return filteredLogs.value
  }

  const startIndex = visibleStartIndex.value
  const endIndex = visibleEndIndex.value
  return filteredLogs.value.slice(startIndex, endIndex)
})

const offsetY = computed(() => {
  if (!props.enableVirtualScroll) {
    return 0
  }
  return visibleStartIndex.value * props.itemHeight
})

// 方法
const onScroll = (event: Event) => {
  if (!props.enableVirtualScroll) return

  const target = event.target as HTMLElement
  scrollTop.value = target.scrollTop

  // 计算可见区域
  const startIndex = Math.floor(scrollTop.value / props.itemHeight)
  const visibleCount = Math.ceil(containerHeight.value / props.itemHeight)
  const endIndex = Math.min(startIndex + visibleCount + props.bufferSize, filteredLogs.value.length)

  visibleStartIndex.value = Math.max(0, startIndex - props.bufferSize)
  visibleEndIndex.value = endIndex
}

const onLogLevelChange = () => {
  resetVirtualScroll()
}

const onSourceChange = () => {
  resetVirtualScroll()
}

const onSearchInput = () => {
  resetVirtualScroll()
}

const onColorHighlightChange = () => {
  // 触发重新渲染
}

const onAutoScrollChange = () => {
  if (autoScroll.value) {
    scrollToBottom()
  }
}

const selectLog = (index: number) => {
  selectedLogIndex.value = index
  const actualIndex = visibleStartIndex.value + index
  const selectedLog = filteredLogs.value[actualIndex]
  if (selectedLog) {
    emit('log-selected', selectedLog, actualIndex)
  }
}

const showLogDetail = () => {
  if (selectedLogIndex.value !== null) {
    const actualIndex = visibleStartIndex.value + selectedLogIndex.value
    const selectedLog = filteredLogs.value[actualIndex]
    if (selectedLog) {
      selectedLogForDetail.value = selectedLog
      detailModalVisible.value = true
    }
  }
}

const exportLogs = async () => {
  exporting.value = true
  try {
    emit('export', filteredLogs.value)
    message.success('日志导出成功')
  } catch (error) {
    message.error(`导出失败: ${error}`)
  } finally {
    exporting.value = false
  }
}

const clearLogs = () => {
  emit('clear')
  internalLogs.value = []
  selectedLogIndex.value = null
}

const refreshLogs = async () => {
  refreshing.value = true
  try {
    emit('refresh')
  } finally {
    refreshing.value = false
  }
}

const scrollToBottom = () => {
  nextTick(() => {
    if (containerRef.value) {
      containerRef.value.scrollTop = containerRef.value.scrollHeight
    }
  })
}

const resetVirtualScroll = () => {
  if (containerRef.value) {
    containerRef.value.scrollTop = 0
    scrollTop.value = 0
  }
  visibleStartIndex.value = 0
  updateVisibleRange()
}

const updateVisibleRange = () => {
  if (!props.enableVirtualScroll) return

  const startIndex = Math.floor(scrollTop.value / props.itemHeight)
  const visibleCount = Math.ceil(containerHeight.value / props.itemHeight)
  const endIndex = Math.min(startIndex + visibleCount + props.bufferSize, filteredLogs.value.length)

  visibleStartIndex.value = Math.max(0, startIndex - props.bufferSize)
  visibleEndIndex.value = endIndex
}

const formatTime = (timestamp: Date) => {
  return timestamp.toLocaleTimeString()
}

const formatFullTime = (timestamp: Date) => {
  return timestamp.toLocaleString()
}

const getLevelStyle = (level: string) => {
  return LogFormatter.getLevelStyle(level)
}

const getModuleStyle = (module: string, source?: LogSource) => {
  return LogFormatter.getModuleStyle(module, source)
}

const highlightSearchKeyword = (text: string) => {
  if (!searchKeyword.value) {
    return enableColorHighlight.value ? text : escapeHtml(text)
  }

  const keyword = searchKeyword.value
  const regex = new RegExp(`(${keyword})`, 'gi')
  const escapedText = escapeHtml(text)
  return escapedText.replace(regex, '<mark>$1</mark>')
}

const escapeHtml = (text: string) => {
  const div = document.createElement('div')
  div.textContent = text
  return div.innerHTML
}

const updateContainerHeight = () => {
  if (containerRef.value) {
    containerHeight.value = containerRef.value.clientHeight
  }
}

// 生命周期
onMounted(() => {
  updateContainerHeight()
  window.addEventListener('resize', updateContainerHeight)
  updateVisibleRange()
})

onUnmounted(() => {
  window.removeEventListener('resize', updateContainerHeight)
})

// 监听滚动位置变化
watch(scrollTop, updateVisibleRange)

// 监听容器高度变化
watch(containerHeight, updateVisibleRange)

// 监听过滤结果变化
watch(filteredLogs, () => {
  if (props.enableVirtualScroll) {
    resetVirtualScroll()
  }
})

// 双击显示详情
const onLogDoubleClick = (index: number) => {
  selectedLogIndex.value = index
  showLogDetail()
}

// 暴露方法给父组件
defineExpose({
  scrollToBottom,
  resetVirtualScroll,
  selectLog,
  showLogDetail
})
</script>

<style scoped>
.virtual-log-viewer {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--ant-color-bg-container);
  border: 1px solid var(--ant-color-border);
  border-radius: 6px;
}

.log-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--ant-color-border);
  background: var(--ant-color-bg-layout);
  flex-shrink: 0;
}

.toolbar-left,
.toolbar-right {
  display: flex;
  align-items: center;
}

.log-container {
  flex: 1;
  overflow-y: auto;
  position: relative;
  background: var(--ant-color-bg-container);
}

.log-phantom {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  z-index: -1;
}

.log-content {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
}

.log-item {
  display: flex;
  align-items: center;
  height: 30px;
  padding: 0 12px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
  cursor: pointer;
  transition: background-color 0.2s;
}

.log-item:hover {
  background: var(--ant-color-bg-layout);
}

.log-item-selected {
  background: var(--ant-color-primary-bg);
}

.log-time {
  width: 100px;
  flex-shrink: 0;
  font-size: 12px;
  color: var(--ant-color-text-secondary);
  font-family: monospace;
}

.log-level {
  width: 80px;
  flex-shrink: 0;
  font-size: 12px;
  text-align: center;
  margin: 0 8px;
  padding: 2px 6px;
  border-radius: 3px;
  font-weight: bold;
}

.log-module {
  width: 120px;
  flex-shrink: 0;
  font-size: 12px;
  margin: 0 8px;
  padding: 2px 6px;
  border-radius: 3px;
  font-weight: bold;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.log-message {
  flex: 1;
  font-size: 12px;
  font-family: monospace;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 日志级别颜色 */
.log-level-trace {
  color: #666666;
}

.log-level-debug {
  color: #666666;
}

.log-level-info {
  color: #52c41a;
}

.log-level-warn {
  color: #faad14;
}

.log-level-error {
  color: #ff4d4f;
}

.log-level-critical {
  color: #ff4d4f;
}

.log-status-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 16px;
  border-top: 1px solid var(--ant-color-border);
  background: var(--ant-color-bg-layout);
  font-size: 12px;
  color: var(--ant-color-text-secondary);
  flex-shrink: 0;
}

.status-left,
.status-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.error-text {
  color: var(--ant-color-error);
}

.log-detail {
  font-family: monospace;
  font-size: 13px;
}

.detail-row {
  display: flex;
  margin-bottom: 12px;
}

.detail-label {
  width: 100px;
  flex-shrink: 0;
  font-weight: bold;
  color: var(--ant-color-text-secondary);
}

.detail-value {
  flex: 1;
  word-break: break-all;
}

.detail-message,
.detail-original,
.detail-metadata {
  flex: 1;
  background: var(--ant-color-bg-layout);
  padding: 8px;
  border-radius: 4px;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 200px;
  overflow-y: auto;
}

/* 高亮样式 */
:deep(mark) {
  background-color: #fffb8f;
  padding: 1px 2px;
  border-radius: 2px;
}

/* 响应式调整 */
@media (max-width: 768px) {
  .log-toolbar {
    flex-direction: column;
    gap: 12px;
    align-items: stretch;
  }

  .toolbar-left,
  .toolbar-right {
    justify-content: center;
  }

  .log-item {
    padding: 0 8px;
  }

  .log-time {
    width: 80px;
  }

  .log-level {
    width: 60px;
    margin: 0 4px;
  }

  .log-module {
    width: 80px;
    margin: 0 4px;
  }
}
</style>