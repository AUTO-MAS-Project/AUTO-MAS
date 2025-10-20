<template>
  <div class="overview-panel">
    <div class="section-header">
      <h3>任务总览</h3>
      <!--      <a-badge :count="totalTaskCount" :overflow-count="99" />-->
    </div>
    <div class="overview-content">
      <TaskTree ref="taskTreeRef" :task-data="taskData" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import TaskTree from '@/components/TaskTree.vue'

interface User {
  user_id: string
  status: string
  name: string
}

interface Script {
  script_id: string
  status: string
  name: string
  user_list: User[]
}

interface WSMessage {
  type: string
  id: string
  data: {
    task_info?: any[]
  }
  fullMessage?: any
}

// 任务数据
const taskData = ref<Script[]>([])
const taskTreeRef = ref()

// 处理 WebSocket 消息
const handleWSMessage = (message: WSMessage) => {
  console.log('TaskOverviewPanel 收到 WebSocket 消息:', message)

  if (message.type === 'Update') {
    // 处理 task_info 数据（完整的脚本和用户数据）
    if (message.data?.task_info && Array.isArray(message.data.task_info)) {
      console.log('更新任务数据 (task_info):', message.data.task_info)
      
      // 转换后端的 task_info 格式到前端的 Script 格式
      taskData.value = message.data.task_info.map((task: any, index: number) => ({
        script_id: task.script_id || `script_${index}`,
        name: task.name || '未知脚本',
        status: task.status || '等待',
        user_list: task.userList ? [...task.userList] : [], // 注意：后端使用 userList，前端使用 user_list
      }))
      
      console.log('设置后的 taskData:', taskData.value)

      // 更新展开状态
      if (taskTreeRef.value) {
        taskTreeRef.value.updateExpandedScripts()
      }
    } else {
      console.log('收到未识别格式的更新数据:', message.data)
    }
  }
}

// 暴露方法供父组件调用
defineExpose({
  handleWSMessage,
  expandAll: () => taskTreeRef.value?.expandAll(),
  collapseAll: () => taskTreeRef.value?.collapseAll(),
})
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
  color: var(--ant-color-text);
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

/* 暗色模式适配 */
@media (prefers-color-scheme: dark) {
  .overview-panel {
    background: var(--ant-color-bg-container, #1f1f1f);
    border: 1px solid var(--ant-color-border, #424242);
  }

  .section-header {
    border-bottom: 1px solid var(--ant-color-border, #424242);
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
