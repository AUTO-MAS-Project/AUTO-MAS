<template>
  <div class="history-page">
    <MacPageHeader
      title="历史记录"
      subtitle="按时间、用户与执行状态查找任务记录和运行日志"
      compact
      transparent
    />

    <!-- 搜索筛选工具栏 -->
    <HistorySearchPanel
      :mode="searchForm.mode"
      :start-date="searchForm.startDate"
      :end-date="searchForm.endDate"
      :keyword="searchKeyword"
      :current-preset="currentPreset"
      :loading="searchLoading"
      :level-filter="levelFilter"
      @update:mode="searchForm.mode = $event"
      @update:start-date="searchForm.startDate = $event"
      @update:end-date="searchForm.endDate = $event"
      @update:keyword="searchKeyword = $event"
      @update:level-filter="levelFilter = $event"
      @quick-select="handleQuickTimeSelect"
      @search="handleSearch"
      @reset="handleReset"
      @clear-filters="clearAllFilters"
      @date-change="handleDateChange"
    />

    <!-- 主内容区域 -->
    <div class="main-content">
      <a-spin :spinning="searchLoading">
        <!-- 失败状态 -->
        <ErrorState
          v-if="searchError && !searchLoading"
          class="history-error-state"
          title="搜索失败"
          :description="searchError"
          :on-retry="handleSearch"
        />

        <!-- 空状态 -->
        <EmptyState
          v-else-if="filteredHistoryData.length === 0 && !searchLoading"
          class="history-empty-state"
          title="暂无历史记录"
          :description="
            searchKeyword ? '未找到匹配的记录，请调整关键词或筛选条件' : '请调整筛选条件后重新搜索'
          "
        />

        <!-- 数据展示：筛选侧边栏 + 主内容区（日志+Inspector） -->
        <div v-else class="content-layout">
          <HistoryDateSidebar
            :current-preset="currentPreset"
            :date-options="dateFilterOptions"
            :script-options="scriptFilterOptions"
            :level-options="levelFilterOptions"
            :user-options="userFilterOptions"
            :level-filter="levelFilter"
            :selected-scripts="selectedScripts"
            :selected-user-filter="selectedUserFilter"
            @quick-select="handleQuickTimeSelect"
            @toggle-script="toggleScriptFilter"
            @select-level="levelFilter = $event"
            @toggle-user="toggleUserFilter"
          />

          <HistoryDetailPanel
            :records="filteredFlatRecords"
            :selected-record-index="selectedRecordIndex"
            :active-filter-chips="activeFilterChips"
            :show-timestamp="showTimestamp"
            :wrap-text="wrapText"
            :live-refresh="liveRefresh"
            :auto-scroll="autoScroll"
            :selected-record-detail="selectedRecordDetail"
            :inspector-visible="inspectorVisible"
            :recruit-statistics="selectedRecordStatistics"
            :drop-statistics="selectedRecordDropStatistics"
            :total-count="flatRecords.length"
            @select-record="handleSelectRecord"
            @remove-chip="removeFilterChip"
            @update:show-timestamp="showTimestamp = $event"
            @update:wrap-text="wrapText = $event"
            @update:live-refresh="liveRefresh = $event"
            @update:auto-scroll="autoScroll = $event"
            @close-inspector="handleCloseInspector"
            @view-full-log="handleOpenFullLog"
          />
        </div>
      </a-spin>
    </div>

    <!-- 日志弹窗（保留完整日志查看功能） -->
    <HistoryLogModal
      :open="logModalOpen"
      :log-content="currentDetail?.log_content || null"
      :loading="detailLoading"
      :has-file="!!currentJsonFile"
      :record-date="currentRecordDate"
      :record-status="currentRecordStatus"
      :error-message="currentErrorMessage"
      :recruit-statistics="currentDetail?.recruit_statistics || null"
      :drop-statistics="currentDetail?.drop_statistics || null"
      :font-size="editorConfig.fontSize"
      :font-size-options="fontSizeOptions"
      :editor-theme="editorTheme"
      :monaco-options="monacoOptions"
      :register-log-language="registerLogLanguage"
      @close="logModalOpen = false"
      @open-file="handleOpenLogFile"
      @open-directory="handleOpenLogDirectory"
      @update:font-size="setEditorConfig({ fontSize: $event })"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import HistoryDateSidebar from './components/HistoryDateSidebar.vue'
import HistoryDetailPanel from './components/HistoryDetailPanel.vue'
import HistoryLogModal from './components/HistoryLogModal.vue'
import HistorySearchPanel from './components/HistorySearchPanel.vue'
import EmptyState from '@/components/v6/EmptyState.vue'
import ErrorState from '@/components/v6/ErrorState.vue'
import MacPageHeader from '@/components/mac/PageHeader.vue'
import { useHistoryLogic } from './useHistoryLogic'
import { formatBackendDateTime } from '@/utils/dateDisplay'
import type { FlatLogRecord } from './useHistoryLogic'

const {
  // 状态
  searchLoading,
  detailLoading,
  searchError,
  currentPreset,
  selectedRecordIndex,
  currentDetail,
  currentJsonFile,
  searchForm,
  searchKeyword,
  filteredHistoryData,

  // Console.app 风格筛选状态
  levelFilter,
  selectedScripts,
  selectedUserFilter,
  inspectorVisible,
  showTimestamp,
  wrapText,
  liveRefresh,
  autoScroll,

  // Console.app 风格派生数据
  flatRecords,
  filteredFlatRecords,
  scriptFilterOptions,
  levelFilterOptions,
  userFilterOptions,
  dateFilterOptions,
  selectedRecordDetail,
  activeFilterChips,

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
  handleSelectRecord: selectRecord,
  handleOpenLogFile,
  handleOpenLogDirectory,
  registerLogLanguage,
  setEditorConfig,

  // Console.app 风格筛选方法
  toggleScriptFilter,
  toggleUserFilter,
  removeFilterChip,
  clearAllFilters,
} = useHistoryLogic()

// 弹窗状态
const logModalOpen = ref(false)
const currentRecordDate = ref('')
const currentRecordStatus = ref('')
const currentErrorMessage = ref('')

// 选中记录所属用户的统计数据（供 Inspector 展示）
const selectedRecordStatistics = computed<Record<string, number> | null>(() => {
  if (!selectedRecordDetail.value) return null
  const username = selectedRecordDetail.value.username
  const groupDate = selectedRecordDetail.value.groupDate
  const group = filteredHistoryData.value.find(g => g.date === groupDate)
  if (!group) return null
  const userData = group.users[username]
  return userData?.recruit_statistics ?? null
})

const selectedRecordDropStatistics = computed<Record<string, Record<string, number>> | null>(() => {
  if (!selectedRecordDetail.value) return null
  const username = selectedRecordDetail.value.username
  const groupDate = selectedRecordDetail.value.groupDate
  const group = filteredHistoryData.value.find(g => g.date === groupDate)
  if (!group) return null
  const userData = group.users[username]
  return userData?.drop_statistics ?? null
})

// 选择记录：展示 Inspector 并在后台加载完整日志数据
const handleSelectRecord = async (index: number, record: FlatLogRecord) => {
  // 展示 Inspector
  inspectorVisible.value = true
  // 后台加载完整日志（用于弹窗和统计）
  currentRecordDate.value = formatBackendDateTime(record.record.date)
  currentRecordStatus.value = record.record.status
  currentErrorMessage.value = record.errorMessage || ''
  await selectRecord(index, record.record)
}

// 关闭 Inspector
const handleCloseInspector = () => {
  inspectorVisible.value = false
}

// 打开完整日志弹窗
const handleOpenFullLog = () => {
  if (!currentJsonFile.value) return
  logModalOpen.value = true
}
</script>

<style scoped>
.history-page {
  height: 100%;
  min-width: 0;
  container: history-page / inline-size;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.main-content {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
  padding: 0 var(--v6-content-padding-inline) var(--v6-space-3);
}

.main-content :deep(.ant-spin-nested-loading),
.main-content :deep(.ant-spin-container) {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.history-empty-state,
.history-error-state {
  flex: 1;
  min-height: 0;
}

.content-layout {
  /* 声明容器:驱动三栏布局内部(日期侧栏/记录列表)的窄容器降级 */
  container: history-content / inline-size;
  flex: 1;
  min-width: 0;
  display: flex;
  gap: 0;
  min-height: 0;
  overflow: hidden;
  background: var(--v6-color-surface);
  border: 1px solid var(--v6-color-border-subtle);
  border-radius: var(--v6-radius-card);
  box-shadow: var(--v6-shadow-card);
}

/* 窄容器:折叠 220px 日期侧栏,记录区独占宽度
   (inspector 已由 HistoryDetailPanel 内 history-detail 1100px 规则兜底) */
@container history-content (max-width: 860px) {
  .content-layout :deep(.history-sidebar) {
    display: none;
  }
}
</style>
