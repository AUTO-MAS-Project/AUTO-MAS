<template>
  <div class="record-list-panel">
    <div class="panel-header">
      <div class="header-left">
        <UnorderedListOutlined />
        <span>记录条目</span>
      </div>
      <div class="header-right">
        <span class="record-count">{{ records.length }} 条记录</span>
        <a-popover placement="bottomRight">
          <template #content>
            <p style="margin: 0">计时规则：4:00-28:00</p>
          </template>
          <HistoryOutlined class="info-icon" />
        </a-popover>
      </div>
    </div>

    <div class="records-container">
      <div v-if="records.length === 0" class="empty-records">
        <img src="../../../assets/NoData.png" alt="无数据" class="empty-image" />
        <span class="empty-text">暂无记录</span>
      </div>

      <div v-else class="records-scroll">
        <div v-for="(record, index) in records" :key="record.jsonFile" class="record-item" :class="{
          active: selectedIndex === index,
          success: record.status === 'DONE',
          error: record.status === 'ERROR',
        }" @click="$emit('select', index, record)">
          <div class="record-status-bar" :class="record.status === 'DONE' ? 'success' : 'error'" />
          <div class="record-content">
            <div class="record-main">
              <span class="record-time">{{ record.date }}</span>
              <a-tag :color="record.status === 'DONE' ? 'success' : 'error'" size="small" class="status-tag">
                <CheckCircleOutlined v-if="record.status === 'DONE'" />
                <CloseCircleOutlined v-else />
                {{
                  record.status === 'DONE'
                    ? '完成'
                    : record.status === 'ERROR' && errorInfo && errorInfo[record.date]
                      ? `失败: ${errorInfo[record.date]}`
                      : '失败'
                }}
              </a-tag>
            </div>
            <div class="record-file">{{ record.jsonFile }}</div>
          </div>
          <RightOutlined v-if="selectedIndex === index" class="record-arrow" />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  HistoryOutlined,
  RightOutlined,
  UnorderedListOutlined,
} from '@ant-design/icons-vue'

interface RecordItem {
  date: string
  jsonFile: string
  status: string
}

interface Props {
  records: RecordItem[]
  selectedIndex: number
  errorInfo?: Record<string, string> | null
}

defineProps<Props>()

defineEmits<{
  (e: 'select', index: number, record: RecordItem): void
}>()
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

/* 滚动条样式 - 浅色 */
.records-scroll::-webkit-scrollbar {
  width: 8px;
}

.records-scroll::-webkit-scrollbar-track {
  background: transparent;
}

.records-scroll::-webkit-scrollbar-thumb {
  background: rgba(0, 0, 0, 0.15);
  border-radius: 4px;
}

.records-scroll::-webkit-scrollbar-thumb:hover {
  background: rgba(0, 0, 0, 0.25);
}

.empty-records {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
  gap: 12px;
}

.empty-image {
  width: 60px;
  height: auto;
  opacity: 0.6;
}

.empty-text {
  font-size: 13px;
  color: var(--ant-color-text-secondary);
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

<style>
/* 深色模式滚动条 - 需要全局样式 */
.dark .records-scroll::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.15) !important;
}

.dark .records-scroll::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.25) !important;
}
</style>
