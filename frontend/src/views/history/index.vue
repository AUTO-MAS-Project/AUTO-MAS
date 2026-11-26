<template>
  <AppPage layout="fill" class="history-page">
    <PageHeader :title="t('core.history.title')" />

    <!-- 搜索筛选区域 -->
    <HistorySearchPanel
      :mode="searchForm.mode"
      :start-date="searchForm.startDate"
      :end-date="searchForm.endDate"
      :current-preset="currentPreset"
      :loading="searchLoading"
      @update:mode="handleModeUpdate"
      @update:start-date="searchForm.startDate = $event"
      @update:end-date="searchForm.endDate = $event"
      @quick-select="handleQuickTimeSelect"
      @search="handleSearch"
      @reset="handleReset"
      @date-change="handleDateChange"
    />

    <!-- 主内容区域 -->
    <div class="main-content">
      <StateView
        :loading="searchLoading"
        :empty="historyData.length === 0"
        :empty-title="t('core.history.emptyHistory')"
        :empty-description="t('core.history.emptyHint')"
        empty-size="lg"
        overlay-loading
      >
        <div class="content-layout">
          <!-- 左侧日期列表 -->
          <HistoryDateSidebar
            :history-data="historyData"
            :active-keys="activeKeys"
            :selected-user="selectedUser"
            @update:active-keys="activeKeys = $event"
            @select-user="handleSelectUser"
          />

          <!-- 右侧详情区域 -->
          <HistoryDetailPanel
            :has-user-selected="!!selectedUserData"
            :aggregate-errors="selectedUserData?.aggregate_errors ?? []"
            :records="selectedUserData?.index || []"
            :selected-record-index="selectedRecordIndex"
            :recruit-statistics="selectedStatistics.recruit"
            :drop-statistics="selectedStatistics.drops"
            :matrix-statistics="selectedStatistics.matrix"
            :pull-count-statistics="selectedStatistics.pulls"
            @select-record="handleSelectRecord"
          />
        </div>
      </StateView>
    </div>

    <!-- 日志弹窗 -->
    <HistoryLogModal
      :open="logModalOpen"
      :log-content="currentDetail?.log_content || null"
      :loading="detailLoading"
      :has-file="currentDetail?.log_available ?? false"
      :record-date="currentRecordDate"
      :record-status="currentRecordStatus"
      :error-message="currentErrorMessage"
      :recruit-statistics="detailStatistics.recruit"
      :drop-statistics="detailStatistics.drops"
      :matrix-statistics="detailStatistics.matrix"
      :pull-count-statistics="detailStatistics.pulls"
      :attachments="currentDetail?.attachments ?? []"
      :storage-errors="currentDetail?.storage_errors ?? []"
      :log-unavailable-reason="currentDetail?.log_unavailable_reason ?? null"
      :font-size="editorConfig.fontSize"
      :font-size-options="fontSizeOptions"
      :editor-theme="editorTheme"
      :monaco-options="monacoOptions"
      :register-log-language="registerLogLanguage"
      @close="logModalOpen = false"
      @open-file="handleOpenLogFile"
      @update:font-size="setEditorConfig({ fontSize: $event })"
    />
  </AppPage>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, ref } from 'vue'
import type { HistoryIndexItem } from '@/api'
import { AppPage, PageHeader, StateView } from '@/components/ui'
import HistoryDateSidebar from './components/HistoryDateSidebar.vue'
import HistoryDetailPanel from './components/HistoryDetailPanel.vue'
import HistoryLogModal from './components/HistoryLogModal.vue'
import HistorySearchPanel from './components/HistorySearchPanel.vue'
import { useHistoryLogic } from './useHistoryLogic'
import { historyStatistics } from './historyData'
import { formatHistoryDateTime } from '@/utils/dateDisplay'

const { t } = useI18n()

defineOptions({
  name: 'HistoryPage',
})

const {
  // 状态
  searchLoading,
  detailLoading,
  activeKeys,
  currentPreset,
  selectedUser,
  selectedUserData,
  selectedRecordIndex,
  currentDetail,
  searchForm,
  historyData,

  // 配置
  fontSizeOptions,
  editorConfig,
  editorTheme,
  monacoOptions,

  // 方法
  handleSearch,
  handleReset,
  handleQuickTimeSelect,
  handleDateChange,
  handleSelectUser,
  handleSelectRecord: selectRecord,
  handleOpenLogFile,
  registerLogLanguage,
  setEditorConfig,
} = useHistoryLogic()

// 弹窗状态
const logModalOpen = ref(false)
const currentRecordDate = ref('')
const currentRecordStatus = ref('')
const currentErrorMessage = ref('')

const selectedStatistics = computed(() => historyStatistics(selectedUserData.value?.data))
const detailStatistics = computed(() => historyStatistics(currentDetail.value?.data))

const handleModeUpdate = (mode: string) => {
  searchForm.mode = mode as typeof searchForm.mode
}

// 选择记录时打开弹窗
const handleSelectRecord = async (index: number, record: HistoryIndexItem) => {
  currentRecordDate.value = formatHistoryDateTime(record.time)
  currentRecordStatus.value = record.status
  currentErrorMessage.value = record.message
  logModalOpen.value = true
  await selectRecord(index, record)
}
</script>

<style scoped>
.main-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.content-layout {
  flex: 1;
  display: flex;
  gap: 16px;
  min-height: 0;
  overflow: hidden;
}
</style>
