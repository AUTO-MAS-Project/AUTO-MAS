<script setup lang="ts">
import { DownloadOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { ref } from 'vue'
import { showMaaEndIssueReportGuide } from '@/utils/maaEndIssueReport'

const { openDevTools } = defineProps<{
  openDevTools: () => void
}>()

const logger = window.electronAPI.getLogger('日志管理')
const exportingLogs = ref(false)

const exportMaaEndIssueReport = async () => {
  exportingLogs.value = true
  try {
    const result = await window.electronAPI?.exportMaaEndIssueReport?.()

    if (!result) {
      message.error('导出功能未响应，请检查程序')
      logger.error('导出 MaaEnd 问题包失败: 未收到响应')
      return
    }

    if (result?.success) {
      message.success(result.message || 'MaaEnd 问题包导出成功')
      logger.info(`MaaEnd 问题包导出成功: ${result.zipPath}`)
      if (result.zipPath) {
        await window.electronAPI?.showItemInFolder?.(result.zipPath)
      }
      showMaaEndIssueReportGuide(result.zipPath)
    } else {
      const errorMsg = result?.error || 'MaaEnd 问题包导出失败'
      logger.error(`导出 MaaEnd 问题包失败: ${errorMsg}`)
      message.error(errorMsg)
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`导出 MaaEnd 问题包失败: ${errorMsg}`)
    message.error(`导出问题包异常: ${errorMsg}`)
  } finally {
    exportingLogs.value = false
  }
}
</script>
<template>
  <div class="tab-content">
    <div class="form-section">
      <div class="section-header">
        <h3>日志导出</h3>
      </div>
      <a-row :gutter="24">
        <a-col :span="24">
          <a-space direction="vertical" size="middle">
            <div class="section-description">
              按 MaaEnd Issue 要求收集日志、诊断文件、脱敏配置和版本信息，并生成可直接作为附件的
              ZIP。导出后请将 ZIP 原文件发送到 AUTO-MAS 官方 QQ 群。
            </div>
            <a-button type="primary" :loading="exportingLogs" @click="exportMaaEndIssueReport">
              <template #icon>
                <DownloadOutlined />
              </template>
              导出 MaaEnd 问题包
            </a-button>
          </a-space>
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

<style scoped>
.section-description {
  color: var(--ant-color-text-description);
}
</style>
