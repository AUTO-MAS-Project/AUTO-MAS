<script setup lang="ts">
import { DownloadOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { ref } from 'vue'

import { useMaaEndIssueReport } from '@/composables/useMaaEndIssueReport'

const { openDevTools } = defineProps<{
  openDevTools: () => void
}>()

const logger = window.electronAPI.getLogger('日志管理')
const exportingLogs = ref(false)
const exportingDataBackup = ref(false)
const { exporting: exportingMaaEndLogs, exportMaaEndIssueReport } = useMaaEndIssueReport(logger)

const exportLogsZip = async () => {
  exportingLogs.value = true
  try {
    const result = await window.electronAPI?.exportLogs?.()
    if (!result) {
      message.error('导出功能未响应，请检查程序')
      logger.error('导出日志失败: 未收到响应')
      return
    }
    if (result.success) {
      message.success(result.message || '日志压缩包导出成功')
      logger.info(`日志导出成功: ${result.zipPath}`)
      if (result.zipPath) await window.electronAPI?.showItemInFolder?.(result.zipPath)
    } else {
      const errorMsg = result.error || '日志导出失败'
      logger.error(`导出日志失败: ${errorMsg}`)
      message.error(errorMsg)
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`导出日志失败: ${errorMsg}`)
    message.error(`导出日志异常: ${errorMsg}`)
  } finally {
    exportingLogs.value = false
  }
}

const exportDataBackup = async () => {
  exportingDataBackup.value = true
  try {
    const result = await window.electronAPI?.exportDataBackup?.()
    if (!result) {
      message.error('备份功能未响应，请检查程序')
      logger.error('导出数据备份失败: 未收到响应')
      return
    }
    if (result.success) {
      message.success(result.message || '数据备份导出成功')
      logger.info(`数据备份导出成功: ${result.zipPath || '路径未知'}`)
      if (result.zipPath) await window.electronAPI?.showItemInFolder?.(result.zipPath)
    } else if (result.error !== '用户取消') {
      const errorMsg = result.error || '数据备份导出失败'
      logger.error(`导出数据备份失败: ${errorMsg}`)
      message.error(errorMsg)
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`导出数据备份失败: ${errorMsg}`)
    message.error(`导出数据备份异常: ${errorMsg}`)
  } finally {
    exportingDataBackup.value = false
  }
}
</script>
<template>
  <div class="tab-content">
    <div class="form-section">
      <div class="section-header">
        <h3>数据备份</h3>
      </div>
      <a-row :gutter="24">
        <a-col :span="24">
          <a-button type="primary" :loading="exportingDataBackup" @click="exportDataBackup">
            <template #icon>
              <DownloadOutlined />
            </template>
            导出数据备份
          </a-button>
        </a-col>
      </a-row>
    </div>

    <div class="form-section">
      <div class="section-header">
        <h3>MAS 本体日志导出</h3>
      </div>
      <a-row :gutter="24">
        <a-col :span="24">
          <a-button type="primary" :loading="exportingLogs" @click="exportLogsZip">
            <template #icon>
              <DownloadOutlined />
            </template>
            导出日志压缩包
          </a-button>
        </a-col>
      </a-row>
    </div>

    <div class="form-section">
      <div class="section-header">
        <h3>MaaEnd 日志包导出</h3>
      </div>
      <a-row :gutter="24">
        <a-col :span="24">
          <a-button type="primary" :loading="exportingMaaEndLogs" @click="exportMaaEndIssueReport">
            <template #icon>
              <DownloadOutlined />
            </template>
            导出 MaaEnd 问题包
          </a-button>
        </a-col>
      </a-row>
    </div>

    <div class="form-section">
      <div class="section-header">
        <h3>开发者选项</h3>
      </div>
      <a-row :gutter="24">
        <a-col :span="24">
          <a-space size="large">
            <a-button size="large" @click="openDevTools"> 打开开发者工具 </a-button>
          </a-space>
        </a-col>
      </a-row>
    </div>
  </div>
</template>
