<template>
  <div class="overview-panel">
    <div class="scheduler-panel-header">
      <h3>任务总览</h3>
      <!--      <a-badge :count="totalTaskCount" :overflow-count="99" />-->
    </div>
    <div class="overview-content">
      <TaskTree ref="taskTreeRef" :task-data="taskData" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, shallowRef } from 'vue'
import TaskTree from '@/components/TaskTree.vue'
const logger = window.electronAPI.getLogger('任务总览面板')

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

// 任务数据只在 WebSocket 快照实际变化时整体替换，避免深层响应式递归开销。
const taskData = shallowRef<Script[]>([])
const taskTreeRef = ref()
const lastTaskSignature = ref('')

const getTaskInfoStats = (taskInfo: any[]) => {
  const scriptCount = taskInfo.length
  const userCount = taskInfo.reduce((total, task) => total + (task.userList?.length || 0), 0)
  return { scriptCount, userCount }
}

const getScriptStats = (scripts: Script[]) => {
  const scriptCount = scripts.length
  const userCount = scripts.reduce((total, script) => total + (script.user_list?.length || 0), 0)
  return { scriptCount, userCount }
}

const buildTaskInfoSignature = (taskInfo: any[]) => {
  return taskInfo
    .map((task, index) => {
      const users = Array.isArray(task.userList)
        ? task.userList.map((user: any) => `${user.name || ''}:${user.status || ''}`).join(',')
        : ''
      return `${task.script_id || index}:${task.name || ''}:${task.status || ''}[${users}]`
    })
    .join('|')
}

// 应用任务信息快照（来自 task.info.updated / task.completed 消息）
const applyTaskInfo = (taskInfo: any[] | undefined) => {
  if (!taskInfo || !Array.isArray(taskInfo)) return

  const signature = buildTaskInfoSignature(taskInfo)
  if (signature === lastTaskSignature.value) {
    return
  }
  lastTaskSignature.value = signature

  const { scriptCount, userCount } = getTaskInfoStats(taskInfo)
  logger.debug(`更新任务数据 : 脚本数=${scriptCount}, 用户数=${userCount}`)

  // 转换后端的 task_info 格式到前端的 Script 格式
  const newTaskData = taskInfo.map((task: any, index: number) => ({
    script_id: task.script_id || `script_${index}`,
    name: task.name || '未知脚本',
    status: task.status || '等待',
    user_list: task.userList ? [...task.userList] : [], // 注意：后端使用 userList，前端使用 user_list
  }))

  logger.debug('数据发生实际变化，更新组件')
  taskData.value = newTaskData
  const stats = getScriptStats(taskData.value)
  logger.debug(`设置后的 taskData: 脚本数=${stats.scriptCount}, 用户数=${stats.userCount}`)
}

// 暴露方法供父组件调用
defineExpose({
  applyTaskInfo,
  expandAll: () => taskTreeRef.value?.expandAll(),
  collapseAll: () => taskTreeRef.value?.collapseAll(),
})
</script>

<style scoped>
.overview-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  background-color: var(--app-background-card-bg, var(--ant-color-bg-container));
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  border: 1px solid var(--ant-color-border-secondary);
  overflow: hidden;
}

.scheduler-panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
  padding: 12px 16px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
  flex-shrink: 0;
}

.scheduler-panel-header h3 {
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

/* 滚动条样式 - 浅色 */
.overview-content::-webkit-scrollbar {
  width: 8px;
}

.overview-content::-webkit-scrollbar-track {
  background: transparent;
}

.overview-content::-webkit-scrollbar-thumb {
  background: rgba(0, 0, 0, 0.15);
  border-radius: 4px;
}

.overview-content::-webkit-scrollbar-thumb:hover {
  background: rgba(0, 0, 0, 0.25);
}

.empty-state-mini {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
}

@media (max-width: 768px) {
  .overview-panel {
    border-radius: 8px;
  }

  .scheduler-panel-header {
    padding: 12px;
  }
}
</style>

<style>
/* 深色模式滚动条 - 需要全局样式 */
.dark .overview-content::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.15) !important;
}

.dark .overview-content::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.25) !important;
}
</style>
