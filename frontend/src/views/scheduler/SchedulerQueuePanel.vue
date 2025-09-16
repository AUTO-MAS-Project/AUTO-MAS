<template>
  <div class="queue-panel">
    <div class="section-header">
      <h3>{{ title }}</h3>
      <a-badge :count="items.length" :overflow-count="99" />
    </div>
    <div class="queue-content">
      <div v-if="items.length === 0" class="empty-state-mini">
        <img src="@/assets/NoData.png" alt="暂无数据" class="empty-image-mini" />
        <p class="empty-text-mini">{{ emptyText }}</p>
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

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.section-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--ant-color-text-heading);
}

.queue-content {
  flex: 1;
  overflow-y: auto;
}

.empty-state-mini {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 200px;
  color: var(--ant-color-text-tertiary);
}

.empty-image-mini {
  width: 48px;
  height: 48px;
  opacity: 0.5;
  margin-bottom: 8px;
  filter: var(--ant-color-scheme-dark, brightness(0.8));
}

.empty-text-mini {
  margin: 0;
  font-size: 14px;
  color: var(--ant-color-text-tertiary);
}

.queue-cards {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.queue-card {
  border-radius: 6px;
  transition: all 0.2s ease;
  background-color: var(--ant-color-bg-container);
  border-color: var(--ant-color-border);
}

.queue-card:hover {
  box-shadow: 0 2px 8px var(--ant-color-shadow);
}

.running-card {
  border-color: var(--ant-color-primary);
  box-shadow: 0 0 0 1px var(--ant-color-primary-bg);
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
  .section-header h3 {
    color: var(--ant-color-text-heading, #ffffff);
  }

  .empty-state-mini {
    color: var(--ant-color-text-tertiary, #8c8c8c);
  }

  .empty-image-mini {
    filter: brightness(0.8);
  }

  .empty-text-mini {
    color: var(--ant-color-text-tertiary, #8c8c8c);
  }

  .queue-card {
    background-color: var(--ant-color-bg-container, #1f1f1f);
    border-color: var(--ant-color-border, #424242);
  }

  .queue-card:hover {
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
  }

  .running-card {
    border-color: var(--ant-color-primary, #1890ff);
    box-shadow: 0 0 0 1px rgba(24, 144, 255, 0.2);
  }

  .item-name {
    color: var(--ant-color-text, #ffffff);
  }
}
</style>
