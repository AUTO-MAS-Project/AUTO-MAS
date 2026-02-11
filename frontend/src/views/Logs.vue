<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, watch, nextTick } from 'vue'
import { message } from 'ant-design-vue'
import { DownloadOutlined, SyncOutlined } from '@ant-design/icons-vue'
import { VueMonacoEditor } from '@guolao/vue-monaco-editor'
import { useTheme } from '@/composables/useTheme'
const logger = window.electronAPI.getLogger('日志查看')
const { themeMode } = useTheme()

// 日志显示模式类型
type LogMode = 'follow' | 'browse'

const logs = ref<string>('')
const loading = ref(false)
const exporting = ref(false)
const logMode = ref<LogMode>('follow')
const selectedLogFile = ref<'app' | 'frontend'>('app')
const realTimeEnabled = ref(true)
let editorInstance: any = null
let refreshInterval: NodeJS.Timeout | null = null

// Monaco Editor 主题
const editorTheme = computed(() => {
    const mode = themeMode.value
    if (mode === 'system') {
        return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'vs-dark' : 'vs'
    }
    return mode === 'dark' ? 'vs-dark' : 'vs'
})

// Monaco Editor 配置
const editorOptions = {
    readOnly: true,
    fontSize: 13,
    lineNumbers: 'on',
    minimap: { enabled: false },
    scrollBeyondLastLine: false,
    automaticLayout: true,
    wordWrap: 'on',
    wrappingIndent: 'same',
    scrollbar: {
        vertical: 'auto',
        horizontal: 'auto',
        useShadows: false,
    },
}

// 处理编辑器挂载
const handleEditorMount = (editor: any) => {
    editorInstance = editor
    // 初始滚动到底部
    if (logMode.value === 'follow' && logs.value) {
        nextTick(() => scrollToBottom())
    }
}

// 滚动到底部
const scrollToBottom = () => {
    if (editorInstance) {
        const lineCount = editorInstance.getModel()?.getLineCount()
        if (lineCount) {
            editorInstance.revealLine(lineCount)
            editorInstance.setScrollTop(editorInstance.getScrollHeight())
        }
    }
}

// 切换日志模式
const toggleLogMode = () => {
    if (logMode.value === 'follow') {
        // 从保持最新切换到自由浏览
        logMode.value = 'browse'
    } else {
        // 从自由浏览切换到保持最新
        logMode.value = 'follow'
        setTimeout(scrollToBottom, 10)
    }
}

// 加载日志
const loadLogs = async (silent = false) => {
    if (!silent) {
        loading.value = true
    }
    try {
        const fileName = selectedLogFile.value === 'app' ? 'app.log' : 'frontend.log'
        const logContent = await (window as any).electronAPI?.getLogs?.(0, fileName)
        if (logContent) {
            logs.value = logContent
            // 只在保持最新模式下自动滚动
            if (logMode.value === 'follow') {
                nextTick(() => scrollToBottom())
            }
        } else {
            logs.value = ''
        }
    } catch (error) {
        if (!silent) {
            const errorMsg = error instanceof Error ? error.message : String(error)
            logger.error(`加载日志失败: ${errorMsg}`)
            message.error('加载日志失败')
        }
    } finally {
        if (!silent) {
            loading.value = false
        }
    }
}

// 开始实时刷新
const startRealTimeRefresh = () => {
    if (refreshInterval) {
        clearInterval(refreshInterval)
    }
    refreshInterval = setInterval(() => {
        loadLogs(true) // 静默刷新
    }, 2000) // 每2秒刷新一次
}

// 停止实时刷新
const stopRealTimeRefresh = () => {
    if (refreshInterval) {
        clearInterval(refreshInterval)
        refreshInterval = null
    }
}

// 切换实时刷新
const toggleRealTime = () => {
    realTimeEnabled.value = !realTimeEnabled.value
    if (realTimeEnabled.value) {
        startRealTimeRefresh()
        message.success('已启用自动更新')
    } else {
        stopRealTimeRefresh()
        message.info('已停止自动更新')
    }
}

// 导出日志压缩包
const exportLogsZip = async () => {
    exporting.value = true
    try {
        const result = await (window as any).electronAPI?.exportLogs?.()

        if (!result) {
            message.error('导出功能未响应，请检查程序')
            logger.error('导出日志失败: 未收到响应')
            return
        }

        if (result?.success) {
            message.success(result.message || '日志压缩包导出成功')
            logger.info(`日志导出成功: ${result.zipPath}`)
            // 打开文件夹并定位到压缩包
            if (result.zipPath) {
                await (window as any).electronAPI?.showItemInFolder?.(result.zipPath)
            }
        } else {
            const errorMsg = result?.error || '日志导出失败'
            logger.error(`导出日志失败: ${errorMsg}`)
            message.error(errorMsg)
        }
    } catch (error) {
        const errorMsg = error instanceof Error ? error.message : String(error)
        logger.error(`导出日志失败: ${errorMsg}`)
        message.error(`导出日志异常: ${errorMsg}`)
    } finally {
        exporting.value = false
    }
}

// 切换日志文件
const onLogFileChange = () => {
    loadLogs()
}

// 监听日志内容变化
watch(logs, () => {
    if (logMode.value === 'follow') {
        nextTick(() => scrollToBottom())
    }
})

onMounted(() => {
    loadLogs()
    if (realTimeEnabled.value) {
        startRealTimeRefresh()
    }
})

onUnmounted(() => {
    stopRealTimeRefresh()
})
</script>

<template>
    <div class="logs-container">
        <div class="logs-header">
            <h1 class="page-title">日志查看</h1>
            <div class="header-actions">
                <a-space :size="12">
                    <a-radio-group v-model:value="selectedLogFile" button-style="solid" @change="onLogFileChange">
                        <a-radio-button value="app">后端日志</a-radio-button>
                        <a-radio-button value="frontend">前端日志</a-radio-button>
                    </a-radio-group>

                    <a-button :type="logMode === 'follow' ? 'primary' : 'default'" @click="toggleLogMode">
                        {{ logMode === 'follow' ? '保持最新' : '自由浏览' }}
                    </a-button>

                    <a-button :type="realTimeEnabled ? 'primary' : 'default'" @click="toggleRealTime">
                        <template #icon>
                            <SyncOutlined :spin="realTimeEnabled" />
                        </template>
                        {{ realTimeEnabled ? '自动更新' : '停止更新' }}
                    </a-button>

                    <a-button @click="exportLogsZip" :loading="exporting" type="primary">
                        <template #icon>
                            <DownloadOutlined />
                        </template>
                        导出压缩包
                    </a-button>
                </a-space>
            </div>
        </div>

        <div class="logs-content">
            <a-spin :spinning="loading" tip="加载日志中...">
                <div class="editor-container" :class="{ 'log-locked': logMode === 'follow' }">
                    <vue-monaco-editor v-model:value="logs" language="log" :theme="editorTheme" :options="editorOptions"
                        class="log-editor" @mount="handleEditorMount" />
                </div>
            </a-spin>
        </div>
    </div>
</template>

<style scoped>
.logs-container {
    width: 100%;
    height: 100%;
    display: flex;
    flex-direction: column;
    padding: 20px;
    box-sizing: border-box;
}

.logs-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
    flex-shrink: 0;
}

.page-title {
    margin: 0;
    font-size: 32px;
    font-weight: 700;
    background: linear-gradient(135deg, var(--ant-color-primary), var(--ant-color-primary-hover));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}

.header-actions {
    display: flex;
    gap: 12px;
}

.logs-content {
    flex: 1;
    background: var(--ant-color-bg-container);
    border-radius: 12px;
    padding: 20px;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    min-height: 0;
}

.editor-container {
    flex: 1;
    border: 1px solid var(--ant-color-border);
    border-radius: 8px;
    overflow: hidden;
    transition: all 0.3s ease;
    min-height: 0;
    display: flex;
    flex-direction: column;
}

/* 保持最新模式：添加视觉提示 */
.log-locked {
    border-color: var(--ant-color-primary);
    box-shadow: 0 0 0 2px var(--ant-color-primary-bg);
}

.log-editor {
    flex: 1;
    min-height: 0;
}

:deep(.monaco-editor) {
    border-radius: 8px;
}

:deep(.ant-spin-nested-loading),
:deep(.ant-spin-container) {
    height: 100%;
    display: flex;
    flex-direction: column;
}
</style>
