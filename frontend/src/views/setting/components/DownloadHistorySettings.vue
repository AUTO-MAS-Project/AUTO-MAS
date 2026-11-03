<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import type { GlobalConfig, FluxdownRecord } from '@/api'
import { useSettingsApi } from '@/composables/useSettingsApi'
import SettingRow from '@/components/ui/SettingRow.vue'

const props = defineProps<{ settings: GlobalConfig }>()
const { t } = useI18n()
const logger = window.electronAPI.getLogger('设置-下载历史')
const { getSettings } = useSettingsApi()

// 下载历史：后端按追加顺序保存，展示时倒序（最新在上）。
// 父页面只在挂载时读取一次设置，下载终态后快照不会自动更新；打开面板时
// 拉取一次最新配置，避免刚产生的失败记录要离页重进才能看到/导出
const fetchedHistory = ref<FluxdownRecord[] | null>(null)
const historyLoading = ref(false)

const updateHistory = computed(() =>
  [...(fetchedHistory.value ?? props.settings.Update?.LastUpdateHistory ?? [])].reverse()
)

const openUpdateHistory = async () => {
  showUpdateHistory.value = true
  historyLoading.value = true
  try {
    const data = await getSettings()
    // 读取失败时 getSettings 返回 null（基础层已提示），此时保留原快照，
    // 不能把已有历史清成空
    const history = data?.Update?.LastUpdateHistory
    if (history) fetchedHistory.value = history
  } finally {
    historyLoading.value = false
  }
}

// 历史记录的状态是后端英文枚举，展示时按当前语言映射，未知值原样显示
const historyStatusLabels = computed<Record<string, string>>(() => ({
  success: t('core.setting.others.historyStatusSuccess'),
  failed: t('core.setting.others.historyStatusFailed'),
  checksum_fail: t('core.setting.others.historyStatusChecksumFail'),
  interrupted: t('core.setting.others.historyStatusInterrupted'),
  fluxdown_fallback: t('core.setting.others.historyStatusFluxdownFallback'),
}))

const formatHistoryStatus = (status?: string | null) =>
  (status && historyStatusLabels.value[status]) || status || t('core.common.unknown')

const formatHistorySize = (size?: number | null) =>
  size ? `${(size / 1024 / 1024).toFixed(1)} MB` : '-'

const formatHistoryDuration = (ms?: number | null) => (ms ? `${(ms / 1000).toFixed(1)}s` : '-')

// 失败/回退记录可导出：把这条下载记录存成 JSON 文件
const handleExportHistory = async (item: FluxdownRecord) => {
  try {
    const fileName = `fluxdown-download-${(item.timestamp ?? '').replace(/[: ]/g, '-')}.json`
    const result = await window.electronAPI.saveTextFile(
      fileName,
      JSON.stringify(item, null, 2),
      [{ name: 'JSON', extensions: ['json'] }],
      {
        dialogTitle: t('core.setting.others.historyExportDialogTitle'),
        buttonLabel: t('core.setting.others.historyExportSaveLabel'),
      }
    )
    if (result.success) {
      message.success(t('core.setting.others.historyExportSuccess'))
    } else if (result.error && result.error !== '用户取消') {
      message.error(result.error)
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`导出下载日志失败: ${errorMsg}`)
    message.error(t('core.setting.others.historyExportFailed'))
  }
}

const showUpdateHistory = ref(false)
</script>

<template>
  <SettingRow
    :label="t('core.setting.others.lastUpdateHistory')"
    :hint="t('core.setting.others.lastUpdateHistoryTip')"
  >
    <span class="history-count">
      {{ t('core.setting.others.historyCount', { count: updateHistory.length }) }}
    </span>
    <a-button type="link" size="small" :loading="historyLoading" @click="openUpdateHistory">
      {{ t('core.setting.others.viewHistory') }}
    </a-button>
  </SettingRow>

  <a-modal
    v-model:open="showUpdateHistory"
    :title="t('core.setting.others.lastUpdateHistory')"
    :width="700"
    :footer="null"
    class="update-history-modal"
  >
    <a-spin :spinning="historyLoading" class="history-loading">
      <a-timeline v-if="updateHistory.length">
        <a-timeline-item
          v-for="(item, idx) in updateHistory"
          :key="idx"
          :color="
            item.status === 'success'
              ? 'green'
              : item.status === 'checksum_fail'
                ? 'red'
                : item.status === 'fluxdown_fallback'
                  ? 'orange'
                  : 'red'
          "
        >
          <div class="history-item-title">
            {{ item.timestamp }} — {{ formatHistoryStatus(item.status) }}
          </div>
          <div class="history-item-path">{{ item.destination || item.url?.slice(0, 80) }}</div>
          <div class="history-item-meta">
            {{ formatHistorySize(item.size) }} ·
            {{ formatHistoryDuration(item.duration_ms) }}
            <span v-if="item.error" class="history-item-error"> — {{ item.error }}</span>
            <a-button
              v-if="item.status && item.status !== 'success'"
              type="link"
              size="small"
              class="history-export-button"
              @click="handleExportHistory(item)"
            >
              {{ t('core.setting.others.historyExport') }}
            </a-button>
          </div>
        </a-timeline-item>
      </a-timeline>
      <NoData v-else :description="t('core.setting.others.noHistory')" />
    </a-spin>
  </a-modal>
</template>

<style scoped>
.history-loading {
  display: block;
  min-height: 120px;
}

.history-count {
  color: var(--ant-color-text-secondary);
  font-size: 13px;
  font-variant-numeric: tabular-nums;
}

:global(.update-history-modal .ant-modal-body) {
  padding: 24px;
}

.history-item-title {
  font-weight: 500;
  color: var(--ant-color-text);
}

.history-item-path {
  margin-top: 2px;
  font-size: 12px;
  color: var(--ant-color-text-secondary);
  word-break: break-all;
}

.history-item-meta {
  margin-top: 2px;
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
}

.history-item-error {
  color: var(--ant-color-error);
}

.history-export-button {
  padding: 0 0 0 8px;
  height: auto;
  font-size: 12px;
}
</style>
