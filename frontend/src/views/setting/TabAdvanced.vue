<script setup lang="ts">
import { DownloadOutlined, SaveOutlined, ImportOutlined } from '@ant-design/icons-vue'
import { message, Modal } from 'ant-design-vue'
import { createVNode, ref } from 'vue'
import { ExclamationCircleOutlined } from '@ant-design/icons-vue'

const { openDevTools } = defineProps<{
  openDevTools: () => void
}>()

const logger = window.electronAPI.getLogger('数据管理')
const exportingLogs = ref(false)
const exportingBackup = ref(false)
const importingBackup = ref(false)

const exportLogsZip = async () => {
  exportingLogs.value = true
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
    exportingLogs.value = false
  }
}

// 导出数据备份（data / config / history）
const exportBackup = async () => {
  exportingBackup.value = true
  try {
    const result = await (window as any).electronAPI?.exportBackup?.()

    if (!result) {
      message.error('备份功能未响应，请检查程序')
      logger.error('导出数据备份失败: 未收到响应')
      return
    }

    if (result?.success) {
      message.success(result.message || '数据备份导出成功')
      logger.info(`数据备份导出成功: ${result.zipPath}`)
      if (result.zipPath) {
        await (window as any).electronAPI?.showItemInFolder?.(result.zipPath)
      }
    } else if (result?.error !== '用户取消') {
      const errorMsg = result?.error || '数据备份导出失败'
      logger.error(`导出数据备份失败: ${errorMsg}`)
      message.error(errorMsg)
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`导出数据备份失败: ${errorMsg}`)
    message.error(`导出数据备份异常: ${errorMsg}`)
  } finally {
    exportingBackup.value = false
  }
}

// 导入数据备份（恢复后自动重启）
const importBackup = () => {
  Modal.confirm({
    title: '恢复数据备份',
    icon: createVNode(ExclamationCircleOutlined),
    content: createVNode('div', {}, [
      '恢复将使用备份包覆盖当前的 data / config / history 文件夹，',
      createVNode('b', {}, '现有数据将被替换且无法撤销'),
      '。恢复完成后应用将自动重启。是否继续？',
    ]),
    okText: '选择备份文件并恢复',
    okType: 'danger',
    cancelText: '取消',
    async onOk() {
      importingBackup.value = true
      try {
        const result = await (window as any).electronAPI?.importBackup?.()

        if (!result) {
          message.error('恢复功能未响应，请检查程序')
          logger.error('导入数据备份失败: 未收到响应')
          return
        }

        if (result?.success) {
          message.success(result.message || '数据恢复成功，应用即将重启', 3)
          logger.info(`数据恢复成功: ${(result.restored || []).join(', ')}`)
        } else if (result?.error !== '用户取消') {
          const errorMsg = result?.error || '数据恢复失败'
          logger.error(`导入数据备份失败: ${errorMsg}`)
          message.error(errorMsg)
        }
      } catch (error) {
        const errorMsg = error instanceof Error ? error.message : String(error)
        logger.error(`导入数据备份失败: ${errorMsg}`)
        message.error(`数据恢复异常: ${errorMsg}`)
      } finally {
        importingBackup.value = false
      }
    },
  })
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
          <a-space direction="vertical" size="middle">
            <div class="section-description">
              将 data（数据库）、config（配置）、history（历史记录）打包导出为一个 zip
              文件，便于备份或迁移。
            </div>
            <a-space size="middle">
              <a-button type="primary" :loading="exportingBackup" @click="exportBackup">
                <template #icon>
                  <SaveOutlined />
                </template>
                导出数据备份
              </a-button>
              <a-button danger :loading="importingBackup" @click="importBackup">
                <template #icon>
                  <ImportOutlined />
                </template>
                恢复数据备份
              </a-button>
            </a-space>
          </a-space>
        </a-col>
      </a-row>
    </div>

    <div class="form-section">
      <div class="section-header">
        <h3>日志导出</h3>
      </div>
      <a-row :gutter="24">
        <a-col :span="24">
          <a-space direction="vertical" size="middle">
            <div class="section-description">导出当前日志压缩包，便于备份或反馈问题时提供附件。</div>
            <a-button type="primary" :loading="exportingLogs" @click="exportLogsZip">
              <template #icon>
                <DownloadOutlined />
              </template>
              导出日志压缩包
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
