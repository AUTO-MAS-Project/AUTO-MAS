<template>
  <div class="history-page">
    <!-- 页面头部 -->
    <div class="page-header">
      <h1 class="page-title">历史记录</h1>
    </div>

    <!-- 搜索筛选区域 -->
    <HistorySearchPanel
      :mode="searchForm.mode"
      :start-date="searchForm.startDate"
      :end-date="searchForm.endDate"
      :current-preset="currentPreset"
      :loading="searchLoading"
      @update:mode="searchForm.mode = $event"
      @update:start-date="searchForm.startDate = $event"
      @update:end-date="searchForm.endDate = $event"
      @quick-select="handleQuickTimeSelect"
      @search="handleSearch"
      @reset="handleReset"
      @date-change="handleDateChange"
    />

    <!-- 主内容区域 -->
    <div class="main-content">
      <a-spin :spinning="searchLoading">
        <!-- 空状态 -->
        <div v-if="historyData.length === 0 && !searchLoading" class="empty-state">
          <img src="@/assets/NoData.png" alt="无数据" class="empty-image" />
          <span class="empty-text">暂无历史记录</span>
          <span class="empty-hint">请调整筛选条件后重新搜索</span>
        </div>

        <!-- 数据展示 -->
        <div v-else class="content-layout">
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
            :records="selectedUserData?.index || []"
            :selected-record-index="selectedRecordIndex"
            :error-info="selectedUserData?.error_info || null"
            @select-record="handleSelectRecord"
          />
        </div>
      </a-spin>
    </div>

    <!-- 日志弹窗 -->
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
import { ref } from 'vue'
import HistoryDateSidebar from './components/HistoryDateSidebar.vue'
import HistoryDetailPanel from './components/HistoryDetailPanel.vue'
import HistoryLogModal from './components/HistoryLogModal.vue'
import HistorySearchPanel from './components/HistorySearchPanel.vue'
import { useHistoryLogic } from './useHistoryLogic'

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
  currentJsonFile,
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
  handleOpenLogDirectory,
  registerLogLanguage,
  setEditorConfig,
} = useHistoryLogic()

// 弹窗状态
const logModalOpen = ref(false)
const currentRecordDate = ref('')
const currentRecordStatus = ref('')
const currentErrorMessage = ref('')

// 选择记录时打开弹窗
const handleSelectRecord = async (index: number, record: any) => {
  currentRecordDate.value = record.date
  currentRecordStatus.value = record.status
  // 获取错误信息
  const errorInfo = selectedUserData.value?.error_info
  currentErrorMessage.value = errorInfo?.[record.date] || ''
  logModalOpen.value = true
  await selectRecord(index, record)
}
</script>

<style scoped>
.history-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.page-header {
  margin-bottom: 24px;
  padding: 0 4px;
}

.page-title {
  margin: 0;
  font-size: 32px;
  font-weight: 700;
  color: var(--ant-color-text);
  background: linear-gradient(135deg, var(--ant-color-primary), var(--ant-color-primary-hover));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.main-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.main-content :deep(.ant-spin-nested-loading),
.main-content :deep(.ant-spin-container) {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.empty-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  gap: 12px;
}

.empty-image {
  width: 120px;
  height: auto;
  opacity: 0.7;
}

.empty-text {
  font-size: 18px;
  font-weight: 500;
  color: var(--ant-color-text-secondary);
}

.empty-hint {
  font-size: 14px;
  color: var(--ant-color-text-quaternary);
}

.content-layout {
  flex: 1;
  display: flex;
  gap: 16px;
  min-height: 0;
  overflow: hidden;
}

@media (max-width: 900px) {
  .content-layout {
    flex-direction: column;
    overflow-y: auto;
  }
}
</style>
