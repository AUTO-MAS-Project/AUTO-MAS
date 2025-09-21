<template>
  <div class="overview-panel">
    <div class="section-header">
      <h3>任务总览</h3>
<!--      <a-badge :count="totalTaskCount" :overflow-count="99" />-->
    </div>
    <div class="overview-content">
      <TaskTree :task-data="taskData" ref="taskTreeRef" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
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
    task_dict?: Script[]
    user_list?: User[]
    task_list?: any[]
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
    // 处理 task_dict 数据（完整的脚本和用户数据）
    if (message.data?.task_dict) {
      console.log('更新任务数据 (task_dict):', message.data.task_dict)
      taskData.value = message.data.task_dict
      console.log('设置后的 taskData:', taskData.value)
      
      // 更新展开状态
      if (taskTreeRef.value) {
        taskTreeRef.value.updateExpandedScripts()
      }
    }
    
    // 处理 user_list 数据（只有用户状态更新）
    else if (message.data?.user_list && Array.isArray(message.data.user_list)) {
      console.log('更新用户列表 (user_list):', message.data.user_list)
      
      // 如果还没有脚本数据，创建一个默认脚本来包含这些用户
      if (taskData.value.length === 0) {
        taskData.value = [{
          script_id: 'default-script',
          name: '新 MAA 脚本', // 使用你提供的脚本名称
          status: '运行中',
          user_list: message.data.user_list
        }]
      } else {
        // 更新现有脚本的用户列表
        // 假设所有用户都属于第一个脚本（根据你的使用场景）
        if (taskData.value[0]) {
          taskData.value[0].user_list = message.data.user_list
          // 根据用户状态更新脚本状态
          const userStatuses = message.data.user_list.map(u => u.status)
          if (userStatuses.includes('异常') || userStatuses.includes('失败')) {
            taskData.value[0].status = '异常'
          } else if (userStatuses.includes('运行中')) {
            taskData.value[0].status = '运行中'
          } else if (userStatuses.every(s => s === '已完成')) {
            taskData.value[0].status = '已完成'
          } else {
            taskData.value[0].status = '等待'
          }
        }
      }
      
      console.log('更新后的 taskData:', taskData.value)
      
      // 更新展开状态
      if (taskTreeRef.value) {
        taskTreeRef.value.updateExpandedScripts()
      }
    }
    
    // 处理 task_list 数据
    else if (message.data?.task_list && Array.isArray(message.data.task_list)) {
      console.log('更新任务列表 (task_list):', message.data.task_list)
      const convertedData = message.data.task_list.map((task: any) => ({
        script_id: task.id || task.script_id || `task_${Date.now()}`,
        name: task.name || '未知任务',
        status: task.status || '等待',
        user_list: task.user_list || []
      }))
      taskData.value = convertedData
      console.log('转换后的 taskData:', taskData.value)
      
      // 更新展开状态
      if (taskTreeRef.value) {
        taskTreeRef.value.updateExpandedScripts()
      }
    }
    
    else {
      console.log('收到未识别格式的更新数据:', message.data)
    }
  }
}

// 暴露方法供父组件调用
defineExpose({
  handleWSMessage,
  expandAll: () => taskTreeRef.value?.expandAll(),
  collapseAll: () => taskTreeRef.value?.collapseAll()
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