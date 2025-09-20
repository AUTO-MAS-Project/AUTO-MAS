<template>
  <div class="overview-panel">
    <div class="section-header">
      <h3>任务总览</h3>
    </div>
    <div class="overview-content">
      <div v-if="treeData.length === 0" class="empty-state-mini">
        <a-empty description="暂无任务" />
      </div>
      <div v-else class="overview-tree">
        <a-tree
          :tree-data="treeData"
          :expanded-keys="expandedKeys"
          @expand="handleExpand"
          :show-line="showLine"
          :selectable="false"
          :show-icon="false"
          class="overview-tree-view"
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
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { getQueueStatusColor, type QueueItem } from './schedulerConstants';

interface Props {
  taskQueue: QueueItem[];
  userQueue: QueueItem[];
}

const props = defineProps<Props>();

// 树形数据结构
const treeData = computed(() => {
  // 构建脚本节点
  const scriptNodes = props.taskQueue.map((task, index) => {
    // 查找相关的用户
    const relatedUsers = props.userQueue.filter(user => 
      user.name.startsWith(`${task.name}-`)
    );
    
    // 构建用户子节点
    const userChildren = relatedUsers.map((user, userIndex) => ({
      key: `user-${index}-${userIndex}`,
      title: user.name.replace(`${task.name}-`, ''), // 移除前缀以避免重复
      status: user.status,
      type: 'user'
    }));
    
    // 构建脚本节点
    const scriptNode: any = {
      key: `script-${index}`,
      title: task.name,
      status: task.status,
      type: 'script'
    };
    
    // 如果有相关用户，添加为子节点
    if (userChildren.length > 0) {
      scriptNode.children = userChildren;
    }
    
    return scriptNode;
  });
  
  return scriptNodes;
});

const expandedKeys = ref<string[]>([]);
const showLine = computed(() => ({ showLeafIcon: false }));

const getStatusColor = (status: string) => getQueueStatusColor(status);

// 处理展开/收起事件
const handleExpand = (keys: string[]) => {
  expandedKeys.value = keys;
};

// 监听任务队列变化，自动展开所有节点
watch(() => props.taskQueue, (newTaskQueue) => {
  // 默认展开所有脚本节点
  expandedKeys.value = newTaskQueue.map((_, index) => `script-${index}`);
}, { immediate: true });

// 监听用户队列变化，更新展开状态
watch(() => props.userQueue, () => {
  // 重新计算展开状态，确保新增的节点能正确显示
  expandedKeys.value = props.taskQueue.map((_, index) => `script-${index}`);
});
</script>

<style scoped>
.overview-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  background-color: var(--ant-color-bg-container);
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  border: 1px solid var(--ant-color-border-secondary);
  overflow: hidden;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
  padding: 12px 16px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
  flex-shrink: 0;
}

.section-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--ant-color-text-heading);
}

.overview-content {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.empty-state-mini {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
}

.overview-tree {
  height: 100%;
}

.overview-tree-view {
  background: transparent;
}

.overview-tree-view :deep(.ant-tree-treenode) {
  padding: 4px 0;
}

.overview-tree-view :deep(.ant-tree-node-content-wrapper) {
  display: flex;
  align-items: center;
  padding: 8px 12px;
  border-radius: 6px;
  transition: all 0.2s;
  height: auto;
}

.overview-tree-view :deep(.ant-tree-node-content-wrapper:hover) {
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
  .overview-panel {
    background: var(--ant-color-bg-container, #1f1f1f);
    border: 1px solid var(--ant-color-border, #424242);
  }
  
  .section-header {
    border-bottom: 1px solid var(--ant-color-border, #424242);
  }
  
  .section-header h3 {
    color: var(--ant-color-text-heading, #ffffff);
  }

  .overview-tree-view :deep(.ant-tree-node-content-wrapper:hover) {
    background-color: var(--ant-color-fill);
  }

  .item-name {
    color: var(--ant-color-text, #ffffff);
  }
}

@media (max-width: 768px) {
  .overview-panel {
    border-radius: 8px;
  }
  
  .section-header {
    padding: 12px;
  }
}
</style>