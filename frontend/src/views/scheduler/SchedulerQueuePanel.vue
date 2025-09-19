<template>
  <div class="queue-panel">
    <a-card class="section-card" :bordered="false">
      <template #title>
        <div class="section-header">
          <h3>{{ title }}</h3>
          <a-badge :count="items.length" :overflow-count="99" />
        </div>
      </template>
      <div class="queue-content">
        <div v-if="items.length === 0" class="empty-state-mini">
          <a-empty :description="emptyText" />
        </div>
        <div v-else class="queue-cards">
          <a-card
            v-for="(item, index) in items"
            :key="`${type}-${index}`"
            size="small"
            class="queue-card"
            :class="{ 'running-card': item.status === '运行' }"
          >
            <template #title>
              <div class="card-title-row">
                <a-tag :color="getStatusColor(item.status)" size="small">
                  {{ item.status }}
                </a-tag>
              </div>
            </template>
            <div class="card-content">
              <p class="item-name">{{ item.name }}</p>
            </div>
          </a-card>
        </div>
      </div>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { getQueueStatusColor, type QueueItem } from './schedulerConstants'

interface Props {
  title: string
  items: QueueItem[]
  type: 'task' | 'user'
  emptyText?: string
}

const props = withDefaults(defineProps<Props>(), {
  emptyText: '暂无数据',
})

const getStatusColor = (status: string) => getQueueStatusColor(status)
</script>

<style scoped>
.queue-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.section-card {
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  border: 1px solid var(--ant-color-border-secondary);
  height: 100%;
}

.section-card :deep(.ant-card-head) {
  border-bottom: 1px solid var(--ant-color-border-secondary);
  padding: 0 16px;
  border-radius: 12px 12px 0 0;
}

.section-card :deep(.ant-card-body) {
  padding: 16px;
  height: calc(100% - 52px);
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.section-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--ant-color-text-heading);
}

.queue-content {
  height: 100%;
  overflow-y: auto;
}

.empty-state-mini {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
}

.queue-cards {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.queue-card {
  border-radius: 8px;
  transition: all 0.2s ease;
  background-color: var(--ant-color-bg-layout);
  border: 1px solid var(--ant-color-border);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.queue-card:hover {
  box-shadow: 0 4px 12px var(--ant-color-shadow);
  transform: translateY(-2px);
}

.running-card {
  border-color: var(--ant-color-primary);
  box-shadow: 0 0 0 2px var(--ant-color-primary-bg);
}

.card-title-row {
  display: flex;
  justify-content: flex-end;
}

.card-content {
  padding-top: 8px;
}

.item-name {
  margin: 0;
  font-size: 14px;
  font-weight: 500;
  color: var(--ant-color-text);
  word-break: break-word;
}

/* 暗色模式适配 */
@media (prefers-color-scheme: dark) {
  .section-card {
    background: var(--ant-color-bg-container, #1f1f1f);
    border: 1px solid var(--ant-color-border, #424242);
  }
  
  .section-card :deep(.ant-card-head) {
    background: var(--ant-color-bg-layout, #141414);
    border-bottom: 1px solid var(--ant-color-border, #424242);
  }
  
  .section-card :deep(.ant-card-body) {
    background: var(--ant-color-bg-container, #1f1f1f);
  }
  
  .section-header h3 {
    color: var(--ant-color-text-heading, #ffffff);
  }

  .queue-card {
    background-color: var(--ant-color-bg-layout, #141414);
    border: 1px solid var(--ant-color-border, #424242);
  }

  .queue-card:hover {
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
  }

  .running-card {
    border-color: var(--ant-color-primary, #1890ff);
    box-shadow: 0 0 0 2px rgba(24, 144, 255, 0.2);
  }

  .item-name {
    color: var(--ant-color-text, #ffffff);
  }
}

@media (max-width: 768px) {
  .section-card :deep(.ant-card-head) {
    padding: 0 16px;
  }
  
  .section-card :deep(.ant-card-body) {
    padding: 12px;
  }
}
</style>