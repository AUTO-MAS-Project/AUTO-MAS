<template>
  <div class="record-list-panel">
    <div class="panel-header">
      <div class="header-left">
        <UnorderedListOutlined />
        <span>{{ t('core.history.recordList') }}</span>
      </div>
      <div class="header-right">
        <span class="record-count">{{
          t('core.history.recordCount', { count: records.length })
        }}</span>
        <a-popover placement="bottomRight">
          <template #content>
            <p style="margin: 0">{{ t('core.history.timeRule') }}</p>
          </template>
          <HistoryOutlined class="info-icon" />
        </a-popover>
      </div>
    </div>

    <div class="records-container">
      <div v-if="records.length === 0" class="empty-records">
        <NoData :image-style="{ height: '80px' }" :description="t('core.history.emptyRecords')" />
      </div>

      <div v-else class="records-scroll">
        <div
          v-for="(record, index) in records"
          :key="record.id"
          class="record-item"
          :class="{
            active: selectedIndex === index,
            success: record.status === 'success',
            skip: record.status === 'skipped' || record.status === 'cancelled',
            error: record.status === 'error',
          }"
          @click="$emit('select', index, record)"
        >
          <div class="record-status-bar" :class="statusClass(record.status)" />
          <div class="record-content">
            <div class="record-main">
              <span class="record-time">{{ formatRecordTime(record.time) }}</span>
              <a-tag :color="statusTagColor(record.status)" size="small" class="status-tag">
                <CheckCircleOutlined v-if="record.status === 'success'" />
                <MinusCircleOutlined
                  v-else-if="record.status === 'skipped' || record.status === 'cancelled'"
                />
                <CloseCircleOutlined v-else />
                {{ record.message || t(statusLabelKey(record.status)) }}
              </a-tag>
            </div>
            <div class="record-file">
              {{ record.script_name }}
              <span v-if="record.storage_error_count">
                ·
                {{
                  t('core.history.storageWarningCount', { count: record.storage_error_count })
                }}</span
              >
            </div>
          </div>
          <RightOutlined v-if="selectedIndex === index" class="record-arrow" />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  HistoryOutlined,
  MinusCircleOutlined,
  RightOutlined,
  UnorderedListOutlined,
} from '@ant-design/icons-vue'
import type { HistoryIndexItem } from '@/api'
import { formatHistoryDateTime } from '@/utils/dateDisplay'
import { statusClass, statusTagColor, statusLabelKey } from '../historyStatus'

const { t } = useI18n()

interface Props {
  records: HistoryIndexItem[]
  selectedIndex: number
}

defineProps<Props>()

defineEmits<{
  (e: 'select', index: number, record: HistoryIndexItem): void
}>()

const formatRecordTime = (date: string) => formatHistoryDateTime(date)
</script>

<style scoped>
.record-list-panel {
  display: flex;
  flex-direction: column;
  background: var(--ant-color-bg-container);
  border-radius: 12px;
  border: 1px solid var(--ant-color-border-secondary);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
  overflow: hidden;
  flex: 1;
  min-height: 200px;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 16px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.header-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.record-count {
  font-size: 12px;
  color: var(--ant-color-text-secondary);
  background: var(--ant-color-fill-quaternary);
  padding: 2px 8px;
  border-radius: 10px;
}

.info-icon {
  color: var(--ant-color-text-quaternary);
  cursor: pointer;
  transition: color 0.2s;
}

.info-icon:hover {
  color: var(--ant-color-primary);
}

.records-container {
  flex: 1;
  overflow: hidden;
}

.records-scroll {
  height: 100%;
  overflow-y: auto;
  padding: 8px;
}

.empty-records {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
  gap: 12px;
}

.record-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  margin-bottom: 6px;
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s ease;
  background: var(--ant-color-fill-quaternary);
  position: relative;
  overflow: hidden;
}

.record-item:last-child {
  margin-bottom: 0;
}

.record-item:hover {
  background: var(--ant-color-fill-tertiary);
  transform: translateX(2px);
}

.record-item.active {
  background: var(--ant-color-fill-tertiary);
  box-shadow: inset 0 0 0 1px var(--ant-color-border);
}

.record-status-bar {
  width: 4px;
  height: 100%;
  position: absolute;
  left: 0;
  top: 0;
  border-radius: 4px 0 0 4px;
}

.record-status-bar.success {
  background: var(--ant-color-success);
}

.record-status-bar.skip,
.record-status-bar.cancelled {
  background: var(--ant-color-text-quaternary);
}

.record-status-bar.error {
  background: var(--ant-color-error);
}

.record-content {
  flex: 1;
  min-width: 0;
  padding-left: 4px;
}

.record-main {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.record-time {
  font-size: 14px;
  font-weight: 500;
  color: var(--ant-color-text);
}

.status-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  max-width: 100%;
  white-space: normal;
  word-break: break-word;
}

.record-file {
  font-size: 11px;
  color: var(--ant-color-text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.record-arrow {
  color: var(--ant-color-primary);
  font-size: 12px;
  flex-shrink: 0;
}
</style>
