<template>
  <div class="detail-panel">
    <!-- 未选择用户时的空状态 -->
    <div v-if="!hasUserSelected" class="empty-state">
      <div class="empty-content">
        <UserSwitchOutlined class="empty-icon" />
        <span class="empty-title">请选择用户</span>
        <span class="empty-desc">从左侧日期列表中选择一个用户查看详细信息</span>
      </div>
    </div>

    <!-- 已选择用户时显示详情 -->
    <div v-else class="detail-content">
      <!-- 统计信息卡片 -->
      <UserStatisticsCard :recruit-statistics="recruitStatistics" :drop-statistics="dropStatistics" />

      <!-- 记录列表 -->
      <HistoryRecordList :records="records" :selected-index="selectedRecordIndex" :error-info="errorInfo"
        @select="(index, record) => $emit('select-record', index, record)" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { UserSwitchOutlined } from '@ant-design/icons-vue'
import HistoryRecordList from './HistoryRecordList.vue'
import UserStatisticsCard from './UserStatisticsCard.vue'

interface RecordItem {
  date: string
  jsonFile: string
  status: string
}

interface Props {
  hasUserSelected: boolean
  records: RecordItem[]
  selectedRecordIndex: number
  errorInfo: Record<string, string> | null
  recruitStatistics: Record<string, number> | null
  dropStatistics: Record<string, Record<string, number>> | null
}

defineProps<Props>()

defineEmits<{
  (e: 'select-record', index: number, record: RecordItem): void
}>()
</script>

<style scoped>
.detail-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}

.empty-state {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--ant-color-bg-container);
  border-radius: 12px;
  border: 1px solid var(--ant-color-border-secondary);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
  min-height: 300px;
}

.empty-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  text-align: center;
}

.empty-icon {
  font-size: 56px;
}

.empty-title {
  font-size: 18px;
  font-weight: 500;
  color: var(--ant-color-text-secondary);
}

.empty-desc {
  font-size: 14px;
  max-width: 280px;
}

.detail-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
</style>
