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
            </a-space>
          </div>
        </a-col>
      </a-row>
    </a-card>

    <!-- 日志内容 -->
    <a-card class="log-content-card">
      <template #title>
        <span>日志内容</span>
      </template>

      <div class="log-content">
        <a-spin :spinning="loading" tip="加载日志中..." class="log-spin">
          <div v-if="displayLogs" class="monaco-container">
            <vue-monaco-editor
              v-model:value="logs"
              :language="editorLanguage"
              :theme="isDark ? 'vs-dark' : 'vs'"
              :options="editorOptions"
              @mount="handleEditorMount"
            />
          </div>
          <a-empty
            v-else
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
import { logger } from '@/utils/logger'
import {
  ClearOutlined,
  DeleteOutlined,
  ExportOutlined,
  FolderOpenOutlined,
} from '@ant-design/icons-vue'
import { VueMonacoEditor } from '@guolao/vue-monaco-editor'
import { Empty, message } from 'ant-design-vue'
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'

const { isDark } = useTheme()

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

// Monaco Editor 实例
let editorInstance: any = null

// Monaco Editor 配置
const editorOptions = computed(() => ({
  readOnly: true,
  minimap: { enabled: true },
  scrollBeyondLastLine: false,
  fontSize: 13,
  fontFamily: 'Consolas, Monaco, Courier New, monospace',
  lineNumbers: 'on',
  wordWrap: wordWrap.value ? 'on' : 'off',
  automaticLayout: true,
  scrollbar: {
    vertical: 'visible',
    horizontal: 'visible',
    useShadows: false,
    verticalScrollbarSize: 10,
    horizontalScrollbarSize: 10,
  },
  renderWhitespace: 'none',
  contextmenu: true,
  folding: true,
}))
const editorLanguage = computed(() => {
  // 如果你的日志很多是 JSON 行，可以自动切换
  const s = logs.value?.trim()
  return s && (s.startsWith('{') || s.startsWith('[')) ? 'json' : 'log'
})

// 自动刷新定时器
let autoRefreshTimer: NodeJS.Timeout | null = null

// 计算属性
const displayLogs = computed(() => {
  const hasContent = logs.value && logs.value.trim().length > 0
  console.log('displayLogs computed:', {
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
  const match = fileName.match(/^frontendlog-(\d{4}-\d{2}-\d{2})\.log$/)
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

// 刷新日志
const refreshLogs = async () => {
  loading.value = true
  try {
    console.log('开始获取日志，文件:', selectedLogFile.value, '行数限制:', logLines.value)
    const logContent = await logger.getLogs(
      logLines.value || undefined,
      selectedLogFile.value || undefined
    )
    console.log('获取到的日志内容:', {
      type: typeof logContent,
      length: logContent?.length || 0,
      isNull: logContent === null,
      isUndefined: logContent === undefined,
      isEmpty: logContent === '',
      preview: logContent?.substring(0, 200) || 'no content',
    })

    logs.value = logContent || ''

    // 日志内容已更新
    // 自动滚动到底部
    await nextTick()
    scrollToBottom()
  } catch (error) {
    console.error('获取日志失败:', error)
    message.error(`获取日志失败: ${error}`)
    logger.error('获取日志失败:', error)
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

/* 响应式调整 */
@media (max-width: 768px) {
  .log-viewer {
    padding: 8px;
    gap: 8px;
  }
}
</style>
