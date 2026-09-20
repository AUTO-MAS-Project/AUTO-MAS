<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { DownloadOutlined, QuestionCircleOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { computed, onMounted, ref } from 'vue'
import type { RuntimeLaunchModeSetting, RuntimeLaunchModeState } from '@/types/electron'

import { useMaaEndIssueReport } from '@/composables/useMaaEndIssueReport'
import { useOkwwIssueReport } from '@/composables/useOkwwIssueReport'
import { useOkNteIssueReport } from '@/composables/useOkNteIssueReport'
import { useZzzOdIssueReport } from '@/composables/useZzzOdIssueReport'

const { t } = useI18n()

const { openDevTools } = defineProps<{
  openDevTools: () => void
}>()

const logger = window.electronAPI.getLogger('日志管理')
const exportingLogs = ref(false)
const exportingDataBackup = ref(false)
const { exporting: exportingMaaEndLogs, exportMaaEndIssueReport } = useMaaEndIssueReport(logger)
const { exporting: exportingOkwwLogs, exportOkwwIssueReport } = useOkwwIssueReport(logger)
const { exporting: exportingOkNteLogs, exportOkNteIssueReport } = useOkNteIssueReport(logger)
const { exporting: exportingZzzOdLogs, exportZzzOdIssueReport } = useZzzOdIssueReport(logger)

// Runtime 灰度开关：持久化设置 + 当前生效值（重启后生效）
const runtimeLaunchMode = ref<RuntimeLaunchModeSetting>('auto')
const runtimeLaunchModeState = ref<RuntimeLaunchModeState | null>(null)
const runtimeLaunchModeLoading = ref(false)

const runtimeLaunchModeOptions = computed(() => [
  { label: t('setting.advanced.runtimeLaunchModeAuto'), value: 'auto' },
  { label: t('setting.advanced.runtimeLaunchModeOff'), value: 'off' },
  { label: t('setting.advanced.runtimeLaunchModeManaged'), value: 'managed' },
])

const runtimeLaunchModeLabels: Record<'off' | 'development' | 'managed', string> = {
  off: 'runtimeLaunchModeOff',
  development: 'runtimeLaunchModeDevelopment',
  managed: 'runtimeLaunchModeManaged',
}

const effectiveModeLabel = computed(() => {
  const state = runtimeLaunchModeState.value
  return state ? t(`setting.advanced.${runtimeLaunchModeLabels[state.mode]}`) : ''
})

const loadRuntimeLaunchMode = async () => {
  try {
    const state = await window.electronAPI?.getRuntimeLaunchMode?.()
    if (!state) return
    runtimeLaunchModeState.value = state
    runtimeLaunchMode.value = state.persisted
    logger.info(`Runtime 启动方式: ${state.mode}（来源: ${state.source}）`)
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`读取 Runtime 启动方式失败: ${errorMsg}`)
  }
}

const handleRuntimeLaunchModeChange = async (value: unknown) => {
  if (typeof value !== 'string') return
  const mode = value as RuntimeLaunchModeSetting
  const previous = runtimeLaunchMode.value
  runtimeLaunchMode.value = mode
  runtimeLaunchModeLoading.value = true
  try {
    const state = await window.electronAPI?.setRuntimeLaunchMode?.(mode)
    if (state) {
      runtimeLaunchModeState.value = state
      logger.info(
        `Runtime 启动方式已保存: ${mode}，解析结果: ${state.mode}（来源: ${state.source}），重启后生效`
      )
    }
  } catch (error) {
    runtimeLaunchMode.value = previous
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存 Runtime 启动方式失败: ${errorMsg}`)
    message.error(t('setting.advanced.runtimeLaunchModeSaveFailed'))
  } finally {
    runtimeLaunchModeLoading.value = false
  }
}

onMounted(() => {
  void loadRuntimeLaunchMode()
})

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
        <h3>{{ t('setting.advanced.issueSection') }}</h3>
      </div>
      <a-row :gutter="24">
        <a-col :span="24">
          <a-space size="large" wrap>
            <a-button
              type="primary"
              :loading="exportingMaaEndLogs"
              @click="exportMaaEndIssueReport"
            >
              <template #icon>
                <DownloadOutlined />
              </template>
              {{ t('setting.advanced.exportMaaEnd') }}
            </a-button>
            <a-button type="primary" :loading="exportingOkwwLogs" @click="exportOkwwIssueReport">
              <template #icon>
                <DownloadOutlined />
              </template>
              {{ t('setting.advanced.exportOkww') }}
            </a-button>
            <a-button type="primary" :loading="exportingOkNteLogs" @click="exportOkNteIssueReport">
              <template #icon>
                <DownloadOutlined />
              </template>
              {{ t('setting.advanced.exportOkNte') }}
            </a-button>
            <a-button type="primary" :loading="exportingZzzOdLogs" @click="exportZzzOdIssueReport">
              <template #icon>
                <DownloadOutlined />
              </template>
              {{ t('setting.advanced.exportZzzOd') }}
            </a-button>
          </a-space>
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

    <div class="form-section">
      <div class="section-header">
        <h3>
          {{ t('setting.advanced.runtimeLaunchMode') }}
          <a-tooltip :title="t('setting.advanced.runtimeLaunchModeTip')">
            <QuestionCircleOutlined class="help-icon" />
          </a-tooltip>
        </h3>
      </div>
      <a-row :gutter="24">
        <a-col :span="12">
          <div class="form-item-vertical">
            <a-select
              :aria-label="t('setting.advanced.runtimeLaunchMode')"
              :value="runtimeLaunchMode"
              :options="runtimeLaunchModeOptions"
              :loading="runtimeLaunchModeLoading"
              size="large"
              style="width: 100%"
              @change="handleRuntimeLaunchModeChange"
            />
            <span v-if="runtimeLaunchModeState" class="runtime-mode-hint">
              {{
                t('setting.advanced.runtimeLaunchModeEffective', {
                  mode: effectiveModeLabel,
                })
              }}
              · {{ t('setting.advanced.runtimeLaunchModeRestartHint') }}
            </span>
          </div>
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

.runtime-mode-hint {
  color: var(--ant-color-text-secondary);
  font-size: 13px;
  line-height: 1.6;
}
</style>
