<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { DownloadOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { ref } from 'vue'

import { useMaaEndIssueReport } from '@/composables/useMaaEndIssueReport'
import { useOkwwIssueReport } from '@/composables/useOkwwIssueReport'

const { t } = useI18n()

const { openDevTools } = defineProps<{
  openDevTools: () => void
}>()

const logger = window.electronAPI.getLogger('日志管理')
const exportingLogs = ref(false)
const exportingDataBackup = ref(false)
const { exporting: exportingMaaEndLogs, exportMaaEndIssueReport } = useMaaEndIssueReport(logger)
const { exporting: exportingOkwwLogs, exportOkwwIssueReport } = useOkwwIssueReport(logger)

const exportLogsZip = async () => {
  exportingLogs.value = true
  try {
    const result = await window.electronAPI?.exportLogs?.()
    if (!result) {
      message.error(t('setting.toast.exportNoResponse'))
      logger.error('导出日志失败: 未收到响应')
      return
    }
    if (result.success) {
      message.success(result.message || t('setting.toast.logExported'))
      logger.info(`日志导出成功: ${result.zipPath}`)
      if (result.zipPath) await window.electronAPI?.showItemInFolder?.(result.zipPath)
    } else {
      const errorMsg = result.error || t('setting.toast.logExportFailed')
      logger.error(`导出日志失败: ${errorMsg}`)
      message.error(errorMsg)
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`导出日志失败: ${errorMsg}`)
    message.error(t('setting.toast.logExportError', { error: errorMsg }))
  } finally {
    exportingLogs.value = false
  }
}

const exportDataBackup = async () => {
  exportingDataBackup.value = true
  try {
    const result = await window.electronAPI?.exportDataBackup?.()
    if (!result) {
      message.error(t('setting.toast.backupNoResponse'))
      logger.error('导出数据备份失败: 未收到响应')
      return
    }
    if (result.success) {
      message.success(result.message || t('setting.toast.backupExported'))
      logger.info(`数据备份导出成功: ${result.zipPath || '路径未知'}`)
      if (result.zipPath) await window.electronAPI?.showItemInFolder?.(result.zipPath)
    } else if (result.error !== '用户取消') {
      const errorMsg = result.error || t('setting.toast.backupExportFailed')
      logger.error(`导出数据备份失败: ${errorMsg}`)
      message.error(errorMsg)
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`导出数据备份失败: ${errorMsg}`)
    message.error(t('setting.toast.backupExportError', { error: errorMsg }))
  } finally {
    exportingDataBackup.value = false
  }
}
</script>
<template>
  <div class="tab-content">
    <div class="form-section">
      <div class="section-header">
        <h3>{{ t('setting.advanced.backupSection') }}</h3>
      </div>
      <a-row :gutter="24">
        <a-col :span="24">
          <div class="backup-action-row">
            <a-button type="primary" :loading="exportingDataBackup" @click="exportDataBackup">
              <template #icon>
                <DownloadOutlined />
              </template>
              {{ t('setting.advanced.exportBackup') }}
            </a-button>
            <span class="backup-description">{{ t('setting.advanced.backupDesc') }}</span>
          </div>
        </a-col>
      </a-row>
    </div>

    <div class="form-section">
      <div class="section-header">
        <h3>{{ t('setting.advanced.logSection') }}</h3>
      </div>
      <a-row :gutter="24">
        <a-col :span="24">
          <a-button type="primary" :loading="exportingLogs" @click="exportLogsZip">
            <template #icon>
              <DownloadOutlined />
            </template>
            {{ t('setting.advanced.exportLog') }}
          </a-button>
        </a-col>
      </a-row>
    </div>

    <div class="form-section">
      <div class="section-header">
        <h3>{{ t('setting.advanced.maaEndSection') }}</h3>
      </div>
      <a-row :gutter="24">
        <a-col :span="24">
          <a-button type="primary" :loading="exportingMaaEndLogs" @click="exportMaaEndIssueReport">
            <template #icon>
              <DownloadOutlined />
            </template>
            {{ t('setting.advanced.exportMaaEnd') }}
          </a-button>
        </a-col>
      </a-row>
    </div>

    <div class="form-section">
      <div class="section-header">
        <h3>OK-WW 日志包导出</h3>
      </div>
      <a-row :gutter="24">
        <a-col :span="24">
          <a-button type="primary" :loading="exportingOkwwLogs" @click="exportOkwwIssueReport">
            <template #icon>
              <DownloadOutlined />
            </template>
            导出 OK-WW 问题包
          </a-button>
        </a-col>
      </a-row>
    </div>

    <div class="form-section">
      <div class="section-header">
        <h3>{{ t('setting.advanced.devSection') }}</h3>
      </div>
      <a-row :gutter="24">
        <a-col :span="24">
          <a-space size="large">
            <a-button size="large" @click="openDevTools">
              {{ t('setting.advanced.openDevTools') }}
            </a-button>
          </a-space>
        </a-col>
      </a-row>
    </div>
  </div>
</template>

<style scoped>
.backup-action-row {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}

.backup-description {
  color: var(--ant-color-text-secondary);
  font-size: 14px;
  line-height: 1.6;
  flex: 1 1 360px;
  min-width: 240px;
}
</style>
