<script setup lang="ts">
import { DownloadOutlined, ToolOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { ref } from 'vue'
import SettingTabHeader from './SettingTabHeader.vue'

const { openDevTools } = defineProps<{
  openDevTools: () => void
}>()

const logger = window.electronAPI.getLogger('日志管理')
const exportingLogs = ref(false)
const exportError = ref<string | null>(null)

const exportLogsZip = async () => {
  exportingLogs.value = true
  exportError.value = null
  try {
    const result = await window.electronAPI?.exportLogs?.()

    if (!result) {
      exportError.value = '导出功能未响应，请检查程序'
      message.error(exportError.value)
      logger.error('导出日志失败: 未收到响应')
      return
    }

    if (result?.success) {
      message.success(result.message || '日志压缩包导出成功')
      logger.info(`日志导出成功: ${result.zipPath}`)
      if (result.zipPath) {
        await window.electronAPI?.showItemInFolder?.(result.zipPath)
      }
    } else {
      exportError.value = result?.error || '日志导出失败'
      logger.error(`导出日志失败: ${exportError.value}`)
      message.error(exportError.value)
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    exportError.value = `导出日志异常: ${errorMsg}`
    logger.error(`导出日志失败: ${errorMsg}`)
    message.error(exportError.value)
  } finally {
    exportingLogs.value = false
  }
}

const onClearError = () => {
  exportError.value = null
}
</script>

<template>
  <div class="tab-content">
    <!-- 统一 Tab 状态条：说明与错误 -->
    <SettingTabHeader
      description="导出当前日志压缩包或打开开发者工具，便于备份或反馈问题。"
      :error="exportError"
      :can-restore-defaults="false"
      @clear-error="onClearError"
    />

    <!-- ── 日志导出 ── -->
    <section class="form-section">
      <header class="section-header">
        <h3>日志导出</h3>
      </header>
      <div class="setting-row setting-row-multiline">
        <div class="row-label">
          <span class="row-title">导出日志压缩包</span>
          <span class="row-help">
            打包当前运行日志为 zip 压缩包，便于备份或在反馈问题时作为附件提供。
          </span>
        </div>
        <div class="row-control">
          <a-button
            type="primary"
            :loading="exportingLogs"
            class="section-update-button"
            @click="exportLogsZip"
          >
            <template #icon>
              <DownloadOutlined />
            </template>
            导出日志压缩包
          </a-button>
        </div>
      </div>
    </section>

    <!-- ── 开发者选项 ── -->
    <section class="form-section">
      <header class="section-header">
        <h3>开发者选项</h3>
      </header>
      <div class="setting-row setting-row-multiline">
        <div class="row-label">
          <span class="row-title">开发者工具</span>
          <span class="row-help">
            打开 Electron 内置的 Chromium 开发者工具，用于调试渲染进程、查看控制台与网络请求。
          </span>
        </div>
        <div class="row-control">
          <a-button class="section-update-button" @click="openDevTools">
            <template #icon>
              <ToolOutlined />
            </template>
            打开开发者工具
          </a-button>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.help-icon {
  color: var(--v6-color-text-tertiary);
  font-size: var(--v6-font-size-sm);
}
</style>
