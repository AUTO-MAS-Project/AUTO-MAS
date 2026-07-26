<template>
  <a-card class="home-queue-card" :bordered="false" title="队列概览">
    <LoadingSkeleton v-if="loading" variant="card" :rows="2" />
    <div v-else-if="!summary" class="queue-empty">
      <EmptyState title="暂无队列数据" description="无法获取队列概览" compact />
    </div>
    <div v-else class="queue-stats">
      <div class="queue-stat">
        <span class="stat-value">{{ summary.queueCount }}</span>
        <span class="stat-label">队列总数</span>
      </div>
      <div class="queue-stat">
        <span class="stat-value">{{ summary.enabledQueueCount }}</span>
        <span class="stat-label">已启用</span>
      </div>
      <div class="queue-stat">
        <span class="stat-value">{{ summary.itemCount }}</span>
        <span class="stat-label">队列项</span>
      </div>
      <a-button type="primary" ghost class="queue-action" @click="onNavigate('/queue')">
        查看队列
        <RightOutlined />
      </a-button>
    </div>
  </a-card>
</template>

<script setup lang="ts">
import { RightOutlined } from '@ant-design/icons-vue'
import EmptyState from '@/components/v6/EmptyState.vue'
import LoadingSkeleton from '@/components/v6/LoadingSkeleton.vue'
import type { HomeQueueSummary } from '../useHomeLogic'

interface Props {
  summary: HomeQueueSummary | null
  loading: boolean
}

defineProps<Props>()

const emit = defineEmits<{
  (e: 'navigate', path: string): void
}>()

const onNavigate = (path: string) => {
  emit('navigate', path)
}
</script>

<style scoped>
.home-queue-card {
  border-radius: var(--v6-radius-card);
  background: var(--v6-vibrancy-content);
  border: 1px solid var(--v6-color-border-subtle);
  box-shadow: var(--v6-shadow-xs);
  backdrop-filter: var(--v6-backdrop-vibrancy);
  -webkit-backdrop-filter: var(--v6-backdrop-vibrancy);
}

.home-queue-card :deep(.ant-card-head) {
  border-bottom: 1px solid var(--v6-color-border-subtle);
}

.home-queue-card :deep(.ant-card-head-title) {
  font-size: 15px;
  font-weight: 600;
}

.queue-empty {
  padding: var(--v6-space-2) 0;
}

.queue-stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr) auto;
  gap: var(--v6-space-4);
  align-items: center;
}

.queue-stat {
  display: flex;
  flex-direction: column;
  gap: var(--v6-space-1);
  padding: var(--v6-space-3);
  background: var(--v6-color-fill-quaternary);
  border-radius: var(--v6-radius-md);
  text-align: center;
}

.stat-value {
  font-size: 24px;
  font-weight: 700;
  color: var(--v6-color-text);
  line-height: 1.2;
}

.stat-label {
  font-size: 12px;
  color: var(--v6-color-text-secondary);
}

.queue-action {
  justify-self: end;
}

@container home-layout (max-width: 640px) {
  .queue-stats {
    grid-template-columns: repeat(3, 1fr);
  }

  .queue-action {
    grid-column: 1 / -1;
    justify-self: stretch;
  }
}
</style>
