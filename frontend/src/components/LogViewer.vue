<template>
    <div class="log-viewer">
        <div class="log-controls">
            <a-space wrap>
                <a-button @click="refreshLogs" :loading="loading">
                    <template #icon>
                        <ReloadOutlined />
                    </template>
                    刷新日志
                </a-button>

                <a-select v-model:value="logLines" @change="refreshLogs" style="width: 120px">
                    <a-select-option :value="100">最近100行</a-select-option>
                    <a-select-option :value="500">最近500行</a-select-option>
                    <a-select-option :value="1000">最近1000行</a-select-option>
                    <a-select-option :value="0">全部日志</a-select-option>
                </a-select>

                <a-button @click="clearLogs" :loading="clearing" type="primary" danger>
                    <template #icon>
                        <DeleteOutlined />
                    </template>
                    清空日志
                </a-button>

                <a-button @click="cleanOldLogs" :loading="cleaning">
                    <template #icon>
                        <ClearOutlined />
                    </template>
                    清理旧日志
                </a-button>

                <a-button @click="openLogDirectory">
                    <template #icon>
                        <FolderOpenOutlined />
                    </template>
                    打开日志目录
                </a-button>
            </a-space>
        </div>

        <div class="log-info">
            <a-space>
                <span>日志文件: {{ logPath }}</span>
                <span>总行数: {{ totalLines }}</span>
            </a-space>
        </div>

        <div class="log-content">
            <a-textarea v-model:value="logs" :rows="25" readonly class="log-textarea" placeholder="暂无日志内容" />
        </div>
    </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import {
    ReloadOutlined,
    DeleteOutlined,
    ClearOutlined,
    FolderOpenOutlined
} from '@ant-design/icons-vue'
import { logger } from '@/utils/logger'

const logs = ref('')
const logPath = ref('')
const logLines = ref(500)
const totalLines = ref(0)
const loading = ref(false)
const clearing = ref(false)
const cleaning = ref(false)

// 刷新日志
const refreshLogs = async () => {
    loading.value = true
    try {
        const logContent = await logger.getLogs(logLines.value || undefined)
        logs.value = logContent
        totalLines.value = logContent.split('\n').filter(line => line.trim()).length

        // 自动滚动到底部
        setTimeout(() => {
            const textarea = document.querySelector('.log-textarea textarea') as HTMLTextAreaElement
            if (textarea) {
                textarea.scrollTop = textarea.scrollHeight
            }
        }, 100)
    } catch (error) {
        message.error('获取日志失败: ' + error)
        logger.error('获取日志失败:', error)
    } finally {
        loading.value = false
    }
}

// 清空日志
const clearLogs = async () => {
    clearing.value = true
    try {
        await logger.clearLogs()
        logs.value = ''
        totalLines.value = 0
        message.success('日志已清空')
    } catch (error) {
        message.error('清空日志失败: ' + error)
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
    } catch (error) {
        message.error('清理旧日志失败: ' + error)
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
            await window.electronAPI.openUrl(`file://${logDir}`)
        }
    } catch (error) {
        message.error('打开日志目录失败: ' + error)
        logger.error('打开日志目录失败:', error)
    }
}

// 获取日志文件路径
const getLogPath = async () => {
    try {
        logPath.value = await logger.getLogPath()
    } catch (error) {
        logger.error('获取日志路径失败:', error)
    }
}

onMounted(() => {
    getLogPath()
    refreshLogs()
})
</script>

<style scoped>
.log-viewer {
    padding: 16px;
}

.log-controls {
    margin-bottom: 16px;
}

.log-info {
    margin-bottom: 12px;
    font-size: 12px;
    color: #666;
}

.log-content {
    border: 1px solid #d9d9d9;
    border-radius: 6px;
}

.log-textarea :deep(.ant-input) {
    font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
    font-size: 12px;
    line-height: 1.4;
    border: none;
    resize: none;
}

.log-textarea :deep(.ant-input:focus) {
    box-shadow: none;
}
</style>