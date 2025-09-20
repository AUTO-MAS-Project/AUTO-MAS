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
        <div v-else class="queue-tree">
          <a-tree
            :tree-data="treeData"
            :expanded-keys="expandedKeys"
            @expand="handleExpand"
            :show-line="showLine"
            :selectable="false"
            :show-icon="false"
            class="queue-tree-view"
          >
            <template #title="{ title, status, type }">
              <div class="tree-item-content">
                <span class="item-name">{{ title }}</span>
                <a-tag 
                  v-if="status" 
                  :color="getStatusColor(status)" 
                  size="small" 
                  class="status-tag"
                >
                  {{ status }}
                </a-tag>
              </div>
            </template>
          </a-tree>
        </div>
      </div>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { getQueueStatusColor, type QueueItem } from './schedulerConstants';

interface Props {
  title: string
  items: QueueItem[]
  type: 'task' | 'user'
  emptyText?: string
}

const props = withDefaults(defineProps<Props>(), {
  emptyText: '暂无数据',
})

// 树形数据结构
const treeData = computed(() => {
  // 为任务队列构建树形结构
  if (props.type === 'task') {
    return props.items.map((item, index) => ({
      key: `task-${index}`,
      title: item.name,
      status: item.status,
      type: 'task'
    }));
  } 
  // 为用户队列构建树形结构
  else {
    // 按照名称前缀分组
    const groups: Record<string, any[]> = {};
    props.items.forEach((item, index) => {
      const prefix = item.name.split('-')[0] || '默认分组';
      if (!groups[prefix]) {
        groups[prefix] = [];
      }
      groups[prefix].push({
        key: `user-${index}`,
        title: item.name,
        status: item.status,
        type: 'user'
      });
    });

    // 构建树形结构
    return Object.entries(groups).map(([groupName, groupItems]) => {
      if (groupItems.length === 1) {
        // 如果组内只有一个项目，直接返回该项目
        return groupItems[0];
      } else {
        // 如果组内有多个项目，创建一个父节点
        return {
          key: `group-${groupName}`,
          title: groupName,
          type: 'group',
          children: groupItems
        };
      }
    });
  }
});

const expandedKeys = ref<string[]>([]);
const showLine = computed(() => ({ showLeafIcon: false }));

const getStatusColor = (status: string) => getQueueStatusColor(status);

// 处理展开/收起事件
const handleExpand = (keys: string[]) => {
  expandedKeys.value = keys;
};

// 监听items变化，自动展开所有节点
watch(() => props.items, () => {
  // 默认展开所有节点
  expandedKeys.value = treeData.value
    .filter(node => node.children)
    .map(node => node.key as string);
}, { immediate: true });
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

.queue-tree {
  height: 100%;
}

.queue-tree-view {
  background: transparent;
}

.queue-tree-view :deep(.ant-tree-treenode) {
  padding: 2px 0;
}

.queue-tree-view :deep(.ant-tree-node-content-wrapper) {
  display: flex;
  align-items: center;
  padding: 6px 8px;
  border-radius: 6px;
  transition: all 0.2s;
}

.queue-tree-view :deep(.ant-tree-node-content-wrapper:hover) {
  background-color: var(--ant-color-fill-secondary);
}

.tree-item-content {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.item-name {
  flex: 1;
  margin: 0;
  font-size: 14px;
  font-weight: 500;
  color: var(--ant-color-text);
  word-break: break-word;
  padding-right: 8px;
}

.status-tag {
  flex-shrink: 0;
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

  .queue-tree-view :deep(.ant-tree-node-content-wrapper:hover) {
    background-color: var(--ant-color-fill);
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