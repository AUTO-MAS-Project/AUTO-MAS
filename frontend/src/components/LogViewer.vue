<template>
    <div class="log-viewer">
        <!-- 工具栏 -->
        <a-card size="small" class="toolbar-card">
            <a-row :gutter="[12, 12]" align="middle" justify="space-between" class="toolbar-grid">
                <!-- 左侧：选择器 -->
                <a-col :xs="24" :md="14">
                    <a-space :size="8" wrap>

                        <a-select v-model:value="selectedLogFile" @change="onLogFileChange" style="width: 220px"
                            placeholder="选择日志文件">
                            <a-select-option value="">今日日志</a-select-option>
                            <a-select-option v-for="file in logFiles" :key="file" :value="file">
                                {{ formatLogFileName(file) }}
                            </a-select-option>
                        </a-select>

                        <a-select v-model:value="logLines" @change="refreshLogs" style="width: 140px"
                            placeholder="显示行数">
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
                                ok-text="确定" cancel-text="取消" @confirm="clearLogs">
                                <a-button :loading="clearing" danger>
                                    <template #icon>
                                        <DeleteOutlined />
                                    </template>
                                    清空当前日志
                                </a-button>
                            </a-popconfirm>

                            <a-button @click="cleanOldLogs" :loading="cleaning">
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
                                导出日志（txt格式）
                            </a-button>
                            <!--                <a-button @click="scrollToBottom" :disabled="!logs">-->
                            <!--                  <template #icon><DownOutlined /></template>-->
                            <!--                  跳转底部-->
                            <!--                </a-button>-->
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



            <div class="log-content" :class="{ 'word-wrap': wordWrap }">
                <a-spin :spinning="loading" tip="加载日志中..." class="log-spin">
                    <div ref="logContainer" class="log-container" v-if="displayLogs">
                        <pre class="log-text" v-html="displayContent"></pre>
                    </div>
                    <a-empty v-else description="暂无日志内容" :image="Empty.PRESENTED_IMAGE_SIMPLE" class="log-empty" />
                </a-spin>
            </div>
        </a-card>
    </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { message, Empty } from 'ant-design-vue'
import {
    DeleteOutlined,
    ClearOutlined,
    FolderOpenOutlined,
    ExportOutlined,
} from '@ant-design/icons-vue'
import { logger } from '@/utils/logger'

// 响应式数据
const logs = ref('')
const logPath = ref('')
const logFiles = ref<string[]>([])
const selectedLogFile = ref('')
const logLines = ref(500)
const loading = ref(false)
const clearing = ref(false)
const cleaning = ref(false)
const autoRefresh = ref(true)
const wordWrap = ref(true)
const logContainer = ref<HTMLElement>()

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

const displayContent = computed(() => {
    if (!logs.value) return ''
    // 转义HTML特殊字符
    return logs.value.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
})

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
        a.download = `${fileName}.txt`

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
    if (logContainer.value) {
        // 使用 nextTick 确保DOM已更新
        nextTick(() => {
            if (logContainer.value) {
                logContainer.value.scrollTop = logContainer.value.scrollHeight
                // 添加平滑滚动效果
                logContainer.value.scrollTo({
                    top: logContainer.value.scrollHeight,
                    behavior: 'smooth',
                })
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
    /* 减少整体高度 */
    display: flex;
    flex-direction: column;
    gap: 12px;
    /* 减少间距 */
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
    /* 减少内边距 */
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

.log-container {
    flex: 1;
    overflow: auto;
    padding: 12px;
    background: var(--ant-color-bg-elevated);
    border-radius: 4px;
    min-height: 0;
}

.log-empty {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
}

.log-text {
    font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
    font-size: 12px;
    line-height: 1.5;
    margin: 0;
    white-space: pre;
    color: var(--ant-color-text);
    word-break: break-all;
}

.word-wrap .log-text {
    white-space: pre-wrap;
    word-break: break-word;
}





/* 滚动条样式 - 适配深色模式 */
.log-container::-webkit-scrollbar {
    width: 8px;
    height: 8px;
}

.log-container::-webkit-scrollbar-track {
    background: var(--ant-color-bg-container);
    border-radius: 4px;
}

.log-container::-webkit-scrollbar-thumb {
    background: var(--ant-color-border);
    border-radius: 4px;
}

.log-container::-webkit-scrollbar-thumb:hover {
    background: var(--ant-color-border-secondary);
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

[data-theme='dark'] .log-container {
    background: #141414;
}

[data-theme='dark'] .log-text {
    color: #e6e6e6;
}

[data-theme='dark'] .log-container::-webkit-scrollbar-track {
    background: #262626;
}

[data-theme='dark'] .log-container::-webkit-scrollbar-thumb {
    background: #434343;
}

[data-theme='dark'] .log-container::-webkit-scrollbar-thumb:hover {
    background: #595959;
}

/* 响应式调整 */
@media (max-width: 768px) {
    .log-viewer {
        padding: 8px;
        gap: 8px;
    }

    .log-text {
        font-size: 11px;
    }
}

/* 日志级别颜色 - 适配深色模式 */
.log-text {
    /* ERROR 级别 - 红色 */
    --log-error-color: #ff4d4f;
    --log-error-bg: rgba(255, 77, 79, 0.1);

    /* WARN 级别 - 橙色 */
    --log-warn-color: #fa8c16;
    --log-warn-bg: rgba(250, 140, 22, 0.1);

    /* INFO 级别 - 蓝色 */
    --log-info-color: #1890ff;
    --log-info-bg: rgba(24, 144, 255, 0.1);

    /* DEBUG 级别 - 绿色 */
    --log-debug-color: #52c41a;
    --log-debug-bg: rgba(82, 196, 26, 0.1);
}

[data-theme='dark'] .log-text {
    --log-error-color: #ff7875;
    --log-error-bg: rgba(255, 120, 117, 0.15);

    --log-warn-color: #ffa940;
    --log-warn-bg: rgba(255, 169, 64, 0.15);

    --log-info-color: #40a9ff;
    --log-info-bg: rgba(64, 169, 255, 0.15);

    --log-debug-color: #73d13d;
    --log-debug-bg: rgba(115, 209, 61, 0.15);
}
</style>
