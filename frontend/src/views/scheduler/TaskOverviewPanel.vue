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
        // 根据用户状态推导脚本状态
        const userStatuses = message.data.user_list.map(u => u.status)
        let scriptStatus = '等待'
        if (userStatuses.includes('异常') || userStatuses.includes('失败')) {
          scriptStatus = '异常'
        } else if (userStatuses.includes('运行')) {
          scriptStatus = '运行'
        } else if (userStatuses.every(s => s === '已完成')) {
          scriptStatus = '已完成'
        }
        
        taskData.value = [{
          script_id: 'default-script',
          name: '新 MAA 脚本', // 使用你提供的脚本名称
          status: scriptStatus,
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
          } else if (userStatuses.includes('运行')) {
            taskData.value[0].status = '运行'
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
      
      // 如果已有任务数据，尝试合并状态更新而不是完全替换
      if (taskData.value && taskData.value.length > 0) {
        // 创建一个更新后的任务数据副本
        const updatedTaskData = taskData.value.map(existingTask => {
          const matchingTask = message.data?.task_list?.find((task: any) => 
            task.name === existingTask.name || 
            task.id === existingTask.script_id ||
            task.script_id === existingTask.script_id
          )
          
          if (matchingTask) {
            return {
              ...existingTask,
              status: matchingTask.status || existingTask.status,
              // 如果 task_list 包含 user_list，则使用新的用户列表，否则保持现有的
              user_list: matchingTask.user_list ? [...matchingTask.user_list] : existingTask.user_list,
            }
          }
          return existingTask
        })
        
        // 添加新的任务（不在现有数据中的）
        const newTasks = (message.data?.task_list || []).filter((task: any) => 
          !taskData.value.some(existingTask => 
            task.name === existingTask.name || 
            task.id === existingTask.script_id ||
            task.script_id === existingTask.script_id
          )
        )
        
        if (newTasks.length > 0) {
          const convertedNewTasks = newTasks.map((task: any) => ({
            script_id: task.id || task.script_id || `task_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
            name: task.name || '未知任务',
            status: task.status || '等待',
            user_list: task.user_list ? [...task.user_list] : [] // 使用后端提供的 user_list
          }))
          updatedTaskData.push(...convertedNewTasks)
        }
        
        taskData.value = updatedTaskData
      } else {
        // 如果没有现有数据，直接转换
        taskData.value = (message.data?.task_list || []).map((task: any) => ({
          script_id: task.id || task.script_id || `task_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
          name: task.name || '未知任务',
          status: task.status || '等待',
          user_list: task.user_list ? [...task.user_list] : [] // 使用后端提供的 user_list
        }))
      }
      
      console.log('处理后的 taskData:', taskData.value)
      
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