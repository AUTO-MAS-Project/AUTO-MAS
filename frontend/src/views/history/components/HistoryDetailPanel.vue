<template>
  <div class="detail-panel">
    <!-- 未选择用户时的空状态 -->
    <div v-if="!hasUserSelected" class="empty-state">
      <NoData :image-style="{ height: '56px' }">
        <template #description>
          <div>{{ t('core.history.selectUser') }}</div>
          <div>{{ t('core.history.selectUserDesc') }}</div>
        </template>
      </NoData>
    </div>

    <!-- 已选择用户时显示详情 -->
    <div v-else class="detail-content">
      <a-alert
        v-if="aggregateErrors.length"
        type="warning"
        show-icon
        class="aggregate-warning"
        :message="t('core.history.aggregateWarning')"
        :description="aggregateErrors.map(error => `${error.key}: ${error.message}`).join('; ')"
      />
      <!-- 统计信息卡片 -->
      <UserStatisticsCard
        :recruit-statistics="recruitStatistics"
        :drop-statistics="dropStatistics"
        :matrix-statistics="matrixStatistics"
        :pull-count-statistics="pullCountStatistics"
      />

      <!-- 记录列表 -->
      <HistoryRecordList
        :records="records"
        :selected-index="selectedRecordIndex"
        @select="(index, record) => $emit('select-record', index, record)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import HistoryRecordList from './HistoryRecordList.vue'
import UserStatisticsCard from './UserStatisticsCard.vue'
import type { PullCountStatistics } from '@/types/history'
import type { HistoryIndexItem, HistoryAggregateError } from '@/api'

const { t } = useI18n()

interface Props {
  hasUserSelected: boolean
  aggregateErrors: HistoryAggregateError[]
  records: HistoryIndexItem[]
  selectedRecordIndex: number
  recruitStatistics: Record<string, number> | null
  dropStatistics: Record<string, Record<string, number>> | null
  matrixStatistics: Record<string, string> | null
  pullCountStatistics: PullCountStatistics | null
}

defineProps<Props>()

defineEmits<{
  'select-record': [number, HistoryIndexItem]
}>()
</script>

<style scoped>
.aggregate-warning {
  margin-bottom: 12px;
  flex-shrink: 0;
}

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

.detail-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
</style>
