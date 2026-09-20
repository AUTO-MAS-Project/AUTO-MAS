<template>
  <a-modal
    v-model:open="modalVisible"
    :title="`下载更新 ${latestVersion}`"
    :width="600"
    :footer="null"
    :mask-closable="false"
    :closable="status === 'completed' || status === 'failed'"
    :z-index="9999"
    class="update-download-modal"
    centered
    @cancel="handleModalCancel"
  >
    <div class="download-container">
      <!-- 下载进度区域 -->
      <div
        v-if="status === 'downloading' || status === 'cancelling' || status === 'switchingSource'"
        class="download-progress-section"
      >
        <div class="main-progress">
          <div class="progress-header">
            <div class="progress-title">
              <a-spin :spinning="true" size="small" />
              <span class="download-title">
                {{ status === 'switchingSource' ? '正在切换下载源' : '下载进度' }}
              </span>
            </div>
            <div
              class="progress-percent"
              :class="{
                'animate-pulse': progressPercent > 0 && progressPercent < 100,
              }"
            >
              {{ progressPercent.toFixed(1) }}%
            </div>
          </div>

          <a-progress
            :percent="progressPercent"
            :show-info="false"
            stroke-color="var(--ant-color-primary)"
            trail-color="var(--ant-color-fill-secondary)"
            :stroke-width="8"
            class="progress-bar"
          />

          <div v-if="sourceLabel" class="download-source">正在从 {{ sourceLabel }} 下载</div>

          <div class="progress-info-row">
            <div class="left-info">
              <span class="file-progress"
                >{{ formatBytes(downloadedSize) }} / {{ formatBytes(fileSize) }}</span
              >
              <span class="download-speed">{{ formatSpeed(speed) }}</span>
            </div>
            <div v-if="estimatedTimeRemaining" class="right-info">
              <span class="eta-label">{{ t('comp.estimatedTimeLeft') }}</span>
              <span class="eta-value">{{ estimatedTimeRemaining }}</span>
            </div>
          </div>

          <div class="download-actions">
            <a-button
              danger
              :loading="status === 'cancelling'"
              :disabled="status === 'switchingSource'"
              @click="confirmCancel"
            >
              {{ t('comp.cancelDownload') }}
            </a-button>
            <a-button type="primary" ghost @click="background">{{
              t('comp.downloadBackground')
            }}</a-button>
          </div>
        </div>
      </div>

      <!-- 下载失败区域 -->
      <div v-if="status === 'failed'" class="download-failed-section">
        <a-result status="error" :title="t('comp.downloadFailed')" :sub-title="failureReason">
          <template #extra>
            <div class="failed-actions">
              <a-button type="primary" @click="retry">{{ t('comp.retryDownload') }}</a-button>
              <a-button @click="reset">{{ t('comp.close') }}</a-button>
            </div>
          </template>
        </a-result>
      </div>

      <!-- 下载成功区域 -->
      <div v-if="status === 'completed'" class="download-success-section">
        <a-result
          status="success"
          :title="t('comp.downloadFinished')"
          :sub-title="t('comp.updateHasFinishedDownloading')"
        >
          <template #extra>
            <div class="success-actions">
              <a-button type="primary" @click="install">{{ t('comp.installNow') }}</a-button>
              <a-button @click="installLater">{{ t('comp.installLater') }}</a-button>
            </div>
          </template>
        </a-result>
      </div>
    </div>
  </a-modal>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { Modal } from 'ant-design-vue'
import { useUpdateDownload } from '@/composables/useUpdateDownload'

const { t } = useI18n()

const {
  status,
  modalVisible,
  sourceLabel,
  downloadedSize,
  fileSize,
  speed,
  progressPercent,
  estimatedTimeRemaining,
  failureReason,
  latestVersion,
  formatBytes,
  formatSpeed,
  cancel,
  background,
  retry,
  reset,
  install,
  installLater,
} = useUpdateDownload()

const confirmCancel = () => {
  Modal.confirm({
    title: t('comp.cancelUpdateDownload'),
    content: t('comp.cancellingDeletesUnfinishedDownload'),
    okText: t('comp.confirmCancellation'),
    cancelText: t('comp.continueDownload'),
    okType: 'danger',
    centered: true,
    zIndex: 10001,
    onOk: cancel,
  })
}

const handleModalCancel = () => {
  if (status.value === 'failed') {
    reset()
  }
}
</script>

<style scoped>
.update-download-modal :deep(.ant-modal-header) {
  border-bottom: 1px solid var(--ant-color-border-secondary);
  padding: 20px 24px 16px;
}

.update-download-modal :deep(.ant-modal-title) {
  font-size: 18px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.update-download-modal :deep(.ant-modal-body) {
  padding: 16px 24px;
  background: var(--ant-color-bg-container);
}

.update-download-modal :deep(.ant-modal-content) {
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 6px 30px rgba(0, 0, 0, 0.12);
}

.download-container {
  display: flex;
  flex-direction: column;
}

.download-progress-section {
  padding: 0;
}

.main-progress {
  padding: 12px 0;
}

.progress-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.progress-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.download-title {
  font-size: 16px;
  font-weight: 500;
  color: var(--ant-color-text);
}

.progress-percent {
  font-size: 24px;
  font-weight: 700;
  color: var(--ant-color-primary);
  font-family:
    'SF Pro Display',
    -apple-system,
    BlinkMacSystemFont,
    'Segoe UI',
    'Roboto',
    sans-serif;
}

.progress-bar {
  margin-bottom: 6px;
}

.progress-bar :deep(.ant-progress-bg) {
  border-radius: 4px;
  background: linear-gradient(90deg, var(--ant-color-primary), var(--ant-color-primary-active));
  box-shadow: 0 1px 4px rgba(22, 119, 255, 0.15);
}

.progress-bar :deep(.ant-progress-outer) {
  border-radius: 4px;
}

.download-source {
  font-size: 13px;
  color: var(--ant-color-text-secondary);
  margin-bottom: 8px;
}

.progress-info-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 14px;
  line-height: 1.4;
  margin-top: 2px;
}

.left-info {
  display: flex;
  align-items: center;
  gap: 16px;
}

.file-progress {
  color: var(--ant-color-text);
  font-weight: 500;
  font-family: 'SF Mono', 'Monaco', 'Consolas', monospace;
}

.download-speed {
  color: var(--ant-color-success);
  font-weight: 600;
  font-family: 'SF Mono', 'Monaco', 'Consolas', monospace;
  padding: 2px 8px;
  background: var(--ant-color-success-bg);
  border-radius: 4px;
  border: 1px solid var(--ant-color-success-border);
  font-size: 13px;
}

.right-info {
  display: flex;
  align-items: center;
  gap: 6px;
}

.eta-label {
  color: var(--ant-color-text-tertiary);
  font-size: 13px;
}

.eta-value {
  color: var(--ant-color-warning);
  font-weight: 600;
  font-family: 'SF Mono', 'Monaco', 'Consolas', monospace;
  padding: 2px 8px;
  background: var(--ant-color-warning-bg);
  border-radius: 4px;
  border: 1px solid var(--ant-color-warning-border);
  font-size: 13px;
}

.download-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid var(--ant-color-border-secondary);
}

.animate-pulse {
  animation: pulse 2s ease-in-out infinite;
}

@keyframes pulse {
  0%,
  100% {
    opacity: 1;
    transform: scale(1);
  }

  50% {
    opacity: 0.8;
    transform: scale(1.05);
  }
}

.download-failed-section,
.download-success-section {
  text-align: center;
  padding: 20px 0;
}

.download-failed-section :deep(.ant-result-title) {
  color: var(--ant-color-error) !important;
  font-size: 20px;
  margin-bottom: 8px;
}

.download-success-section :deep(.ant-result-title) {
  color: var(--ant-color-success) !important;
  font-size: 20px;
  margin-bottom: 8px;
}

.failed-actions,
.success-actions {
  display: flex;
  justify-content: center;
  gap: 16px;
  margin-top: 24px;
}

.failed-actions .ant-btn,
.success-actions .ant-btn {
  min-width: 120px;
  height: 40px;
  border-radius: 8px;
  font-weight: 500;
}
</style>
