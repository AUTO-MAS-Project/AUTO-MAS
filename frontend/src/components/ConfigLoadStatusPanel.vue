<template>
  <a-card :title="t('setting.configLoad.title')" size="small" class="config-load-status-panel">
    <p class="config-load-desc">{{ t('setting.configLoad.description') }}</p>

    <!-- 失败给可执行动作；技术原文只进诊断信息，不做主文案 -->
    <RetryableErrorState
      v-if="loadError"
      :error="loadError"
      message-key="setting.configLoad.loadFailed"
      @retry="loadReports"
    />

    <template v-else>
      <OperationStatusBanner
        v-if="loading"
        state="loading"
        message-key="setting.configLoad.loading"
      />
      <OperationStatusBanner v-else state="success" message-key="setting.configLoad.loaded" />

      <a-list v-if="reports.length" :data-source="reports" size="small" row-key="path">
        <template #renderItem="{ item }">
          <a-list-item>
            <div class="config-load-report">
              <div class="config-load-report-head">
                <span class="config-load-file">{{ item.file }}</span>
                <a-tag :color="configLoadStatusColor(item.status)">
                  {{ t(configLoadStatusKey(item.status)) }}
                </a-tag>
                <span class="config-load-time">
                  {{ t('setting.configLoad.readAt', { time: formatConfigLoadTime(item.time) }) }}
                </span>
              </div>

              <a-descriptions size="small" :column="1" class="config-load-meta">
                <a-descriptions-item :label="t('setting.configLoad.path')">
                  {{ item.path }}
                </a-descriptions-item>
                <!-- 文件写入时间：恢复备份会覆写该文件，所以这就是恢复时间 -->
                <a-descriptions-item v-if="item.fileTime" :label="t('setting.configLoad.fileTime')">
                  {{ formatConfigLoadTime(item.fileTime) }}
                </a-descriptions-item>
                <a-descriptions-item
                  v-if="item.backupPath"
                  :label="t('setting.configLoad.backupPath')"
                >
                  <span class="config-load-backup">{{ item.backupPath }}</span>
                </a-descriptions-item>
              </a-descriptions>

              <div
                v-if="hasNormalizationEvents(item.normalizationEvents)"
                class="config-load-events"
              >
                <div class="config-load-events-title">{{ t('setting.configLoad.events') }}</div>
                <div
                  v-for="(event, index) in item.normalizationEvents"
                  :key="`${event.field}-${event.time}-${index}`"
                  class="config-load-event"
                >
                  <span>{{ eventSummary(event) }}</span>
                  <a-tag color="orange">{{ event.reason }}</a-tag>
                  <span class="config-load-time">{{ formatConfigLoadTime(event.time) }}</span>
                </div>
              </div>
            </div>
          </a-list-item>
        </template>
      </a-list>

      <a-empty v-else-if="!loading" :description="t('setting.configLoad.empty')" />
    </template>
  </a-card>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { GetService, type ConfigLoadEventOut, type ConfigLoadReportOut } from '@/api'
import OperationStatusBanner from '@/components/OperationStatusBanner.vue'
import RetryableErrorState from '@/components/RetryableErrorState.vue'
import { AppRequestError, toAppError } from '@/utils/appError'
import {
  configLoadEventSummary,
  configLoadStatusColor,
  configLoadStatusKey,
  formatConfigLoadTime,
  hasNormalizationEvents,
} from '@/utils/configLoadReport'

defineOptions({ name: 'ConfigLoadStatusPanel' })

const { t } = useI18n()
const logger = window.electronAPI.getLogger('配置加载状态')

const reports = ref<ConfigLoadReportOut[]>([])
const loading = ref(false)
const loadError = ref<AppRequestError | null>(null)

// 后端信封里的技术原文只进 detail 与日志，主文案走 setting.configLoad.loadFailed。
const envelopeError = (code: number | undefined, responseMessage?: string) =>
  new AppRequestError('unknown', {
    detail: `code ${code ?? 'unknown'} | ${responseMessage ?? ''}`,
  })

const eventSummary = (event: ConfigLoadEventOut) =>
  configLoadEventSummary((key, named) => t(key, named ?? {}), event)

const loadReports = async () => {
  loading.value = true
  try {
    const response = await GetService.getConfigLoadReportsApiSettingConfigLoadGet()
    if (response.code !== 200) {
      const failure = envelopeError(response.code, response.message)
      loadError.value = failure
      logger.error(`读取配置加载状态失败: ${failure.detail}`)
      return
    }
    reports.value = response.data || []
    loadError.value = null
  } catch (error) {
    const failure = toAppError(error)
    loadError.value = failure
    logger.error(`读取配置加载状态时出错: ${failure.detail}`)
  } finally {
    loading.value = false
  }
}

onMounted(loadReports)
</script>

<style scoped>
.config-load-status-panel {
  margin-top: 16px;
}

.config-load-desc {
  margin-bottom: 12px;
  color: var(--ant-color-text-secondary);
}

.config-load-report {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}

.config-load-report-head {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.config-load-file {
  font-weight: 600;
}

.config-load-time {
  color: var(--ant-color-text-secondary);
  font-size: 12px;
}

.config-load-meta :deep(.ant-descriptions-item-label) {
  width: 180px;
  color: var(--ant-color-text-secondary);
}

.config-load-backup {
  word-break: break-all;
}

.config-load-events {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px;
  border-radius: 6px;
  background: var(--ant-color-fill-quaternary, transparent);
}

.config-load-events-title {
  font-weight: 600;
}

.config-load-event {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}
</style>
