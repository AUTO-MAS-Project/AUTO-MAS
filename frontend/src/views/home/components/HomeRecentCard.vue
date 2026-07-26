<template>
  <a-card class="home-recent-card" :bordered="false">
    <template #title>最近活动</template>
    <template #extra>
      <a-button type="link" size="small" @click="onNavigate('/history')">
        查看全部
        <RightOutlined />
      </a-button>
    </template>
    <LoadingSkeleton v-if="loading" variant="list" :rows="3" />
    <div v-else-if="records.length === 0" class="recent-empty">
      <EmptyState title="暂无近期结果" description="最近 7 天没有运行记录" compact />
    </div>
    <div v-else class="recent-list">
      <div
        v-for="record in records"
        :key="`${record.date}-${record.username}-${record.record.date}`"
        class="recent-item"
        @click="onNavigate('/history')"
      >
        <div class="recent-status" :class="record.record.status === 'DONE' ? 'success' : 'error'" />
        <div class="recent-info">
          <div class="recent-main">
            <span class="recent-user">{{ record.username }}</span>
            <a-tag
              size="small"
              :color="record.record.status === 'DONE' ? 'success' : 'error'"
              class="recent-tag"
            >
              {{ record.record.status === 'DONE' ? '完成' : '失败' }}
            </a-tag>
          </div>
          <div class="recent-sub">
            <span>{{ formatDate(record.record.date) }}</span>
            <span class="recent-separator">·</span>
            <span class="recent-file" :title="record.record.jsonFile">{{
              record.record.jsonFile
            }}</span>
          </div>
        </div>
        <RightOutlined class="recent-arrow" />
      </div>
    </div>
  </a-card>
</template>

<script setup lang="ts">
import { RightOutlined } from '@ant-design/icons-vue'
import EmptyState from '@/components/v6/EmptyState.vue'
import LoadingSkeleton from '@/components/v6/LoadingSkeleton.vue'
import { formatBackendDateTime } from '@/utils/dateDisplay'
import type { HomeRecentRecord } from '../useHomeLogic'

interface Props {
  records: HomeRecentRecord[]
  loading: boolean
}

defineProps<Props>()

const emit = defineEmits<{
  (e: 'navigate', path: string): void
}>()

const formatDate = (value: string) => formatBackendDateTime(value)

const onNavigate = (path: string) => {
  emit('navigate', path)
}
</script>

<style scoped>
.home-recent-card {
  /* 卡片撑满所在模块高度（与并排的卫星卡等高），
     避免空态时卡片下方露出页面背景造成“背景断裂” */
  flex: 1;
  display: flex;
  flex-direction: column;
  border-radius: var(--v6-radius-card);
  background: color-mix(in srgb, var(--v6-color-surface) 84%, transparent);
  border: 1px solid var(--v6-color-border-subtle);
  box-shadow: var(--v6-shadow-card);
  backdrop-filter: blur(24px) saturate(1.18);
}

.home-recent-card :deep(.ant-card-head) {
  flex: 0 0 auto;
  border-bottom: 1px solid var(--v6-color-border-subtle);
}

.home-recent-card :deep(.ant-card-head-title) {
  font-size: 15px;
  font-weight: 600;
}

.home-recent-card :deep(.ant-card-body) {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.recent-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--v6-space-2) 0;
}

.recent-list {
  display: flex;
  flex-direction: column;
  gap: var(--v6-space-2);
}

.recent-item {
  display: flex;
  align-items: center;
  gap: var(--v6-space-3);
  padding: var(--v6-space-3);
  border-radius: var(--v6-radius-md);
  background: var(--v6-color-fill-quaternary);
  cursor: pointer;
  transition: background-color 0.16s ease;
  position: relative;
  overflow: hidden;
}

.recent-item:hover {
  background: var(--v6-color-fill-tertiary);
}

.recent-item:focus-visible {
  outline: 2px solid var(--v6-color-primary);
  outline-offset: 2px;
}

.recent-status {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 3px;
}

.recent-status.success {
  background: var(--v6-color-success);
}

.recent-status.error {
  background: var(--v6-color-error);
}

.recent-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--v6-space-1);
  padding-left: var(--v6-space-1);
}

.recent-main {
  display: flex;
  align-items: center;
  gap: var(--v6-space-2);
}

.recent-user {
  font-size: 14px;
  font-weight: 600;
  color: var(--v6-color-text);
}

.recent-tag {
  font-size: 11px;
  line-height: 16px;
}

.recent-sub {
  font-size: 12px;
  color: var(--v6-color-text-secondary);
  display: flex;
  align-items: center;
  gap: var(--v6-space-1);
  min-width: 0;
}

.recent-separator {
  color: var(--v6-color-text-tertiary);
}

.recent-file {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.recent-arrow {
  color: var(--v6-color-text-quaternary);
  font-size: 12px;
  flex-shrink: 0;
}

.recent-item:hover .recent-arrow {
  color: var(--v6-color-primary);
}
</style>
