<template>
  <div class="log-viewer">
    <!-- 工具栏 -->
    <a-card size="small" class="toolbar-card">
      <a-row :gutter="[12, 12]" align="middle" justify="space-between" class="toolbar-grid">
        <!-- 左侧：选择器 -->
        <a-col :xs="24" :md="14">
          <a-space :size="8" wrap>
            <a-select
              v-model:value="selectedLogFile"
              style="width: 220px"
              placeholder="选择日志文件"
              @change="onLogFileChange"
            >
              <a-select-option value="">今日日志</a-select-option>
              <a-select-option v-for="file in logFiles" :key="file" :value="file">
                {{ formatLogFileName(file) }}
              </a-select-option>
            </a-select>

            <a-select
              v-model:value="logLines"
              style="width: 140px"
              placeholder="显示行数"
              @change="refreshLogs"
            >
              <a-select-option :value="100">最近100行</a-select-option>
              <a-select-option :value="500">最近500行</a-select-option>
              <a-select-option :value="1000">最近1000行</a-select-option>
              <a-select-option :value="0">显示全部</a-select-option>
            </a-select>

            <a-checkbox
              v-model:checked="enableColorHighlight"
              @change="onColorHighlightChange"
            >
              启用颜色高亮
            </a-checkbox>

            <a-switch
              v-model:checked="useNewSystem"
              checked-children="新系统"
              un-checked-children="旧系统"
              @change="onSystemChange"
            />
          </a-space>
        </a-col>

        <!-- 右侧：操作按钮 -->
        <a-col :xs="24" :md="10">
          <div class="toolbar-actions">
            <a-space :size="8" wrap>
              <a-popconfirm
                :title="`确定要清空${selectedLogFile ? formatLogFileName(selectedLogFile) : '今日日志'}吗？`"
                ok-text="确定"
                cancel-text="取消"
                @confirm="clearLogs"
              >
                <a-button :loading="clearing" danger>
                  <template #icon>
                    <DeleteOutlined />
                  </template>
                  清空当前日志
                </a-button>
              </a-popconfirm>

              <a-button :loading="cleaning" @click="cleanOldLogs">
                <template #icon>
                  <ClearOutlined />
                </template>
                清理7日前的旧日志
              </a-button>

              <a-button @click="openLogDirectory">
                <template #icon>
                  <FolderOpenOutlined />
                </template>
                打开日志所在目录
              </a-button>

              <a-button @click="exportLogs">
                <template #icon>
                  <ExportOutlined />
                </template>
                导出日志（log格式）
              </a-button>

              <a-button @click="goToLogSystemSettings" v-if="useNewSystem">
                <template #icon>
                  <SettingOutlined />
                </template>
                日志系统设置
              </a-button>

              <a-button @click="refreshLogs" v-if="!useNewSystem">
                <template #icon>
                  <ReloadOutlined />
                </template>
                刷新日志
              </a-button>
            </a-space>
          </div>
        </a-col>
      </a-row>
    </a-card>

    <!-- 日志过滤器 - 仅在新系统显示 -->
    <a-card class="filter-card" v-if="useNewSystem">
      <template #title>
        <span><SyncOutlined /> 日志过滤器</span>
      </template>
      <a-row :gutter="16">
        <a-col :span="6">
          <a-select
            v-model:value="selectedLogLevel"
            placeholder="过滤日志级别"
            allowClear
            style="width: 100%"
            @change="applyFilters"
          >
            <a-select-option v-for="level in logLevels" :key="level" :value="level">
              {{ level }}
            </a-select-option>
          </a-select>
        </a-col>
        <a-col :span="6">
          <a-select
            v-model:value="selectedLogSource"
            placeholder="过滤日志来源"
            allowClear
            style="width: 100%"
            @change="applyFilters"
          >
            <a-select-option v-for="source in logSources" :key="source" :value="source">
              {{ source }}
            </a-select-option>
          </a-select>
        </a-col>
        <a-col :span="8">
          <a-input
            v-model:value="searchKeyword"
            placeholder="搜索关键词..."
            allowClear
            @change="applyFilters"
          />
        </a-col>
        <a-col :span="4">
          <a-switch
            v-model:checked="autoScroll"
            checked-children="自动滚动"
            un-checked-children="手动滚动"
          />
        </a-col>
      </a-row>
    </a-card>

    <!-- 日志内容 -->
    <a-card class="log-content-card">
      <template #title>
        <span>日志内容</span>
      </template>
      <template #extra v-if="useNewSystem">
        <a-space>
          <a-statistic title="总日志数" :value="stats.total" />
          <a-statistic title="过滤后" :value="stats.filtered" />
        </a-space>
      </template>

      <div class="log-content">
        <a-spin :spinning="loading" tip="加载日志中..." class="log-spin">
          <!-- 新系统显示 -->
          <div v-if="useNewSystem && hasLogs" class="new-log-container">
            <div
              v-for="(log, index) in filteredLogs"
              :key="index"
              class="log-entry"
              :class="`log-${log.level.toLowerCase()}`"
              @click="selectLog(log, index)"
            >
              <div class="log-header">
                <span class="log-timestamp">{{ formatTimestamp(log.timestamp) }}</span>
                <span class="log-level" :class="`level-${log.level.toLowerCase()}`">
                  {{ log.level }}
                </span>
                <span class="log-source">{{ log.source || 'unknown' }}</span>
                <span class="log-module">{{ log.module }}</span>
              </div>
              <div class="log-message" v-html="log.coloredLog || log.message"></div>
            </div>
            <a-empty
              v-if="useNewSystem && isEmpty"
              description="暂无日志内容"
              :image="Empty.PRESENTED_IMAGE_SIMPLE"
              class="log-empty"
            />
          </div>
          
          <!-- 旧系统显示 -->
          <div v-if="!useNewSystem && displayLogs" class="monaco-container">
            <vue-monaco-editor
              v-model:value="logs"
              :language="editorLanguage"
              :theme="isDark ? 'vs-dark' : 'vs'"
              :options="editorOptions"
              @mount="handleEditorMount"
            />
          </div>
          <a-empty
            v-if="!useNewSystem && !displayLogs"
            description="暂无日志内容"
            :image="Empty.PRESENTED_IMAGE_SIMPLE"
            class="log-empty"
          />
        </a-spin>
      </div>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { useTheme } from '@/composables/useTheme.ts'
import { getLogger } from '@/utils/logger'
import {
  ClearOutlined,
  DeleteOutlined,
  ExportOutlined,
  FolderOpenOutlined,
  SettingOutlined,
  ReloadOutlined,
  SyncOutlined,
} from '@ant-design/icons-vue'
import { VueMonacoEditor } from '@guolao/vue-monaco-editor'
import { Empty, message } from 'ant-design-vue'
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import type { ParsedLogEntry, LogLevel, LogSource } from '@/types/log'
import { useLogViewer } from '@/composables/useLogViewer'

// 导入日志处理工具类型
interface ParsedBackendLog {
  timestamp?: Date
  level?: string
  module?: string
  message?: string
  coloredLog?: string
  isValid: boolean
  originalLog: string
}

const { isDark } = useTheme()
const router = useRouter()
const moduleLogger = getLogger('日志查看器')
// 导入全局logger实例以访问日志文件操作方法
import logger from '@/utils/logger'

// 系统切换
const useNewSystem = ref(true)

// 使用新的日志查看器组合式函数
const {
  refresh,
  clear,
  export: exportLogsFromComposable,
  filteredLogs,
  stats,
  hasLogs,
  isEmpty,
  logLevels,
  logSources,
  config: logViewerConfig
} = useLogViewer({
  enableVirtualScroll: true,
  autoRefresh: true,
  refreshInterval: 2000,
  maxLogs: 10000
})

// 响应式数据
const logs = ref('')
const logPath = ref('')
const logFiles = ref<string[]>([])
const selectedLogFile = ref('')
const logLines = ref(500)
const loading = ref(false)
const clearing = ref(false)
const cleaning = ref(false)
const wordWrap = ref(true)
const enableColorHighlight = ref(true)
const selectedLogLevel = ref<string>('')
const selectedLogSource = ref<string>('')
const searchKeyword = ref('')
const autoScroll = ref(true)

// Monaco Editor 实例
let editorInstance: any = null

// 日志颜色处理 - 使用IPC调用后端处理
const processLogColors = async (logContent: string): Promise<string> => {
  if (!enableColorHighlight.value || !logContent) {
    return logContent
  }
  
  try {
    // 通过IPC调用后端的日志颜色处理
    return await window.electronAPI.processLogColors(logContent, enableColorHighlight.value)
  } catch (error) {
    console.error('处理日志颜色失败:', error)
    return logContent
  }
}


// Monaco Editor 配置
const editorOptions = computed(() => ({
  readOnly: true,
  minimap: { enabled: true },
  scrollBeyondLastLine: false,
  fontSize: 13,
  fontFamily: 'Consolas, Monaco, Courier New, monospace',
  lineNumbers: 'on' as any,
  wordWrap: (wordWrap.value ? 'on' : 'off') as any,
  automaticLayout: true,
  scrollbar: {
    vertical: 'visible' as any,
    horizontal: 'visible' as any,
    useShadows: false,
    verticalScrollbarSize: 10,
    horizontalScrollbarSize: 10,
  },
  renderWhitespace: 'none' as any,
  contextmenu: true,
  folding: true,
  // 启用HTML内联渲染以支持颜色显示
  renderControlCharacters: false,
  renderLineHighlight: 'none' as any,
  // 禁用一些可能影响颜色显示的功能
  occurrencesHighlight: 'off' as any,
  codeLens: false,
  lightbulb: { enabled: 'off' as any },
  // 优化性能
  smoothScrolling: true,
  cursorBlinking: 'smooth' as any,
  // 确保颜色正确显示
  experimental: {
    async: true,
  },
}))
const editorLanguage = computed(() => {
  // 如果启用了颜色高亮，使用HTML模式以支持自定义颜色
  if (enableColorHighlight.value) {
    return 'html'
  }
  
  // 如果日志内容包含HTML标签，也使用HTML模式
  if (logs.value && logs.value.includes('<')) {
    return 'html'
  }
  
  // 如果你的日志很多是 JSON 行，可以自动切换
  const s = logs.value?.trim()
  return s && (s.startsWith('{') || s.startsWith('[')) ? 'json' : 'log'
})

// 自动刷新定时器
let autoRefreshTimer: NodeJS.Timeout | null = null

// 计算属性
const displayLogs = computed(() => {
  const hasContent = logs.value && logs.value.trim().length > 0
  moduleLogger.debug('displayLogs computed:', {
    hasLogs: !!logs.value,
    logsLength: logs.value?.length || 0,
    trimmedLength: logs.value?.trim().length || 0,
    hasContent,
    firstChars: logs.value?.substring(0, 100) || 'empty',
  })
  return hasContent
})

// 处理编辑器挂载
const handleEditorMount = (editor: any) => {
  editorInstance = editor
  // 滚动到底部
  nextTick(() => {
    scrollToBottom()
  })
}

// 格式化日志文件名显示
const formatLogFileName = (fileName: string) => {
  // 支持新格式: frontend.log.YYYY-MM-DD.gz
  const match = fileName.match(/^frontend\.log\.(\d{4}-\d{2}-\d{2})\.gz$/)
  if (match) {
    const [, dateStr] = match
    // 转换为更友好的中文显示
    const date = new Date(dateStr + 'T00:00:00')
    const options: Intl.DateTimeFormatOptions = {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
      weekday: 'short',
    }
    return date.toLocaleDateString('zh-CN', options)
  }
  
  // 兼容旧格式: frontendlog-YYYY-MM-DD.log
  const oldMatch = fileName.match(/^frontendlog-(\d{4}-\d{2}-\d{2})\.log$/)
  if (oldMatch) {
    const [, dateStr] = oldMatch
    const date = new Date(dateStr + 'T00:00:00')
    const options: Intl.DateTimeFormatOptions = {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
      weekday: 'short',
    }
    return date.toLocaleDateString('zh-CN', options)
  }
  
  return fileName
}

// 获取日志文件列表
const getLogFiles = async () => {
  try {
    const files = await logger.getLogFiles()
    logFiles.value = files
  } catch (error) {
    logger.error('获取日志文件列表失败:', error)
    logFiles.value = []
  }
}

// 日志文件选择变化
const onLogFileChange = () => {
  refreshLogs()
}

// 颜色高亮开关变化
const onColorHighlightChange = () => {
  // 重新获取并处理日志内容
  if (useNewSystem.value) {
    refresh()
  } else {
    refreshLogs()
  }
}

// 系统切换
const onSystemChange = (useNew: boolean) => {
  if (useNew) {
    message.info('已切换到新日志系统')
    refresh()
  } else {
    message.info('已切换到旧日志系统')
    refreshLogs()
  }
}

// 应用过滤器
const applyFilters = () => {
  // 过滤逻辑已在useLogViewer中处理
  moduleLogger.debug('应用过滤器', {
    level: selectedLogLevel.value,
    source: selectedLogSource.value,
    keyword: searchKeyword.value
  })
}

// 选择日志
const selectLog = (log: ParsedLogEntry, index: number) => {
  moduleLogger.debug('选中日志:', log, index)
  // 可以在这里实现日志详情显示
}

// 格式化时间戳
const formatTimestamp = (timestamp: Date) => {
  return timestamp.toLocaleTimeString('zh-CN', {
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  })
}

// 跳转到日志系统设置
const goToLogSystemSettings = () => {
  // 使用路由跳转到设置页面的日志系统标签
  try {
    router.push('/setting?tab=logsystem')
  } catch (error) {
    moduleLogger.error('路由跳转失败:', error)
    // 降级方案
    message.info('请手动前往设置页面的日志系统标签')
  }
}

// 刷新日志
const refreshLogs = async () => {
  loading.value = true
  try {
    logger.debug('开始获取日志，文件:', selectedLogFile.value, '行数限制:', logLines.value)
    const logContent = await logger.getLogs(
      logLines.value || undefined,
      selectedLogFile.value || undefined
    )
    logger.debug('获取到的日志内容:', {
      type: typeof logContent,
      length: logContent?.length || 0,
      isNull: logContent === null,
      isUndefined: logContent === undefined,
      isEmpty: logContent === '',
      preview: logContent?.substring(0, 200) || 'no content',
    })

    // 应用颜色处理
    if (logContent) {
      logs.value = await processLogColors(logContent)
    } else {
      logs.value = ''
    }
    
    // 日志内容已更新
    // 自动滚动到底部
    await nextTick()
    scrollToBottom()
  } catch (error) {
    logger.error('获取日志失败:', error)
    message.error(`获取日志失败: ${error}`)
    logs.value = ''
  } finally {
    loading.value = false
  }
}

// 清空日志
const clearLogs = async () => {
  clearing.value = true
  try {
    await logger.clearLogs(selectedLogFile.value || undefined)
    logs.value = ''
    const fileName = selectedLogFile.value ? formatLogFileName(selectedLogFile.value) : '今日日志'
    message.success(`${fileName}已清空`)
  } catch (error) {
    message.error(`清空日志失败: ${error}`)
    logger.error('清空日志失败:', error)
  } finally {
    clearing.value = false
  }
}

// 清理旧日志
const cleanOldLogs = async () => {
  cleaning.value = true
  try {
    await logger.cleanOldLogs(7)
    message.success('已清理7天前的旧日志文件')
    // 清理后刷新日志文件列表和当前日志
    await getLogFiles()
    await refreshLogs()
  } catch (error) {
    message.error(`清理旧日志失败: ${error}`)
    logger.error('清理旧日志失败:', error)
  } finally {
    cleaning.value = false
  }
}

// 打开日志目录
const openLogDirectory = async () => {
  try {
    const path = await logger.getLogPath()
    // 获取日志目录路径
    const logDir = path.substring(0, path.lastIndexOf('\\') || path.lastIndexOf('/'))

    if (window.electronAPI?.openUrl) {
      const result = await window.electronAPI.openUrl(`file://${logDir}`)
      if (!result.success) {
        throw new Error(result.error || '打开目录失败')
      }
    } else {
      throw new Error('Electron API 不可用')
    }
  } catch (error) {
    message.error(`打开日志目录失败: ${error}`)
    logger.error('打开日志目录失败:', error)
  }
}

// 导出日志
const exportLogs = async () => {
  try {
    if (!logs.value) {
      message.warning('没有日志内容可导出')
      return
    }

    const blob = new Blob([logs.value], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url

    // 使用当前选择的日志文件名或默认名称
    let fileName = 'logs'
    if (selectedLogFile.value) {
      fileName = selectedLogFile.value.replace('.log', '')
    } else {
      fileName = `logs_${new Date().toISOString().slice(0, 10)}`
    }
    a.download = `${fileName}.log`

    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)

    message.success('日志导出成功')
  } catch (error) {
    message.error(`导出日志失败: ${error}`)
    logger.error('导出日志失败:', error)
  }
}

// 滚动到底部
const scrollToBottom = () => {
  if (editorInstance) {
    nextTick(() => {
      if (editorInstance) {
        const lineCount = editorInstance.getModel()?.getLineCount()
        if (lineCount) {
          editorInstance.revealLine(lineCount)
          editorInstance.setScrollTop(editorInstance.getScrollHeight())
        }
      }
    })
  }
}

// 启动自动刷新
const startAutoRefresh = () => {
  if (autoRefreshTimer) {
    clearInterval(autoRefreshTimer)
  }
  autoRefreshTimer = setInterval(() => {
    refreshLogs()
  }, 2000) // 每2秒刷新一次
}

// 获取日志文件路径
const getLogPath = async () => {
  try {
    logPath.value = await logger.getLogPath()
  } catch (error) {
    logger.error('获取日志路径失败:', error)
    logPath.value = ''
  }
}

// 生命周期
onMounted(async () => {
  await getLogPath()
  await getLogFiles()
  await refreshLogs()
  // 启动自动刷新
  startAutoRefresh()
})

onUnmounted(() => {
  if (autoRefreshTimer) {
    clearInterval(autoRefreshTimer)
  }
})
</script>

<style scoped>
.log-viewer {
  padding: 16px;
  height: 85vh;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.toolbar-card {
  flex-shrink: 0;
}

.toolbar-content {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 16px;
}

.toolbar-left,
.toolbar-right {
  flex-wrap: wrap;
}

/* 响应式处理 */
@media (max-width: 1400px) {
  .toolbar-content {
    flex-direction: column;
    align-items: stretch;
  }

  .toolbar-left,
  .toolbar-right {
    justify-content: center;
  }
}

.log-content-card {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.log-content-card :deep(.ant-card-body) {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  padding: 12px;
}

.log-content {
  flex: 1;
  min-height: 0;
  border: 1px solid var(--ant-color-border);
  border-radius: 6px;
  background: var(--ant-color-bg-container);
  display: flex;
  flex-direction: column;
}

.log-spin {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.monaco-container {
  flex: 1;
  min-height: 0;
  height: 100%;
  width: 100%;
}

.monaco-container :deep(.monaco-editor) {
  height: 100% !important;
}

.log-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* 空状态样式 */
:deep(.ant-empty) {
  padding: 40px 20px;
}

:deep(.ant-empty-description) {
  color: var(--ant-color-text-secondary);
}

/* 加载状态 */
:deep(.ant-spin-container) {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

:deep(.ant-spin-nested-loading) {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

/* 深色模式特定样式 */
[data-theme='dark'] .log-content {
  border-color: #434343;
  background: #1f1f1f;
}

/* 新日志系统样式 */
.filter-card {
  margin-bottom: 12px;
}

.new-log-container {
  height: 100%;
  overflow-y: auto;
  padding: 8px;
}

.log-entry {
  padding: 8px 12px;
  border-bottom: 1px solid var(--ant-color-border);
  cursor: pointer;
  transition: background-color 0.2s;
}

.log-entry:hover {
  background-color: var(--ant-color-bg-layout);
}

.log-entry:last-child {
  border-bottom: none;
}

.log-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 4px;
  font-size: 12px;
  color: var(--ant-color-text-secondary);
}

.log-timestamp {
  font-family: monospace;
}

.log-level {
  padding: 2px 6px;
  border-radius: 4px;
  font-weight: bold;
  font-size: 10px;
  color: white;
}

.level-debug {
  background-color: #999;
}

.level-info {
  background-color: #1890ff;
}

.level-warn {
  background-color: #fa8c16;
}

.level-error {
  background-color: #f5222d;
}

.level-critical {
  background-color: #722ed1;
}

.log-source {
  background-color: var(--ant-color-bg-layout);
  padding: 2px 6px;
  border-radius: 4px;
}

.log-module {
  font-weight: bold;
}

.log-message {
  font-family: monospace;
  font-size: 13px;
  line-height: 1.4;
  white-space: pre-wrap;
  word-break: break-all;
}

/* 响应式调整 */
@media (max-width: 768px) {
  .log-viewer {
    padding: 8px;
    gap: 8px;
  }
  
  .log-header {
    flex-wrap: wrap;
    gap: 6px;
  }
}
</style>
