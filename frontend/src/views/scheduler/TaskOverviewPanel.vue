<template>
  <div class="overview-panel">
    <div class="section-header">
      <h3>任务总览</h3>
      <!--      <a-badge :count="totalTaskCount" :overflow-count="99" />-->
    </div>
    <div v-if="cycleQueueId" class="cycle-preview">
      <div class="cycle-preview-heading">
        <a-tag color="processing">循环运行</a-tag>
        <span v-if="cycleCurrentItemId">正在执行 {{ currentCycleName }}</span>
        <span v-else-if="cycleNextRunAt">下次运行 {{ cycleNextRunAt }}</span>
        <span v-else>等待可运行项目</span>
        <span v-if="cycleWaitingReason" class="cycle-waiting">{{ cycleWaitingReason }}</span>
      </div>
      <div v-if="cycleNextList.length" class="cycle-preview-list">
        <span
          v-for="item in cycleNextList"
          :key="item.queueItemId"
          class="cycle-preview-item"
          :class="{ due: item.isDue, running: item.isRunning }"
        >
          {{ item.scriptName }} ·
          {{ item.isRunning ? '运行中' : item.isDue ? '已到期' : item.nextRunAt }}
        </span>
      </div>
    </div>
    <div class="overview-content">
      <TaskTree ref="taskTreeRef" :task-data="taskData" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, shallowRef } from 'vue'
import TaskTree from '@/components/TaskTree.vue'
import type { WSCyclePreviewItem } from '@/services/websocket/types'
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

interface WSMessage {
  type: string
  id: string
  data: {
    task_info?: any[]
    cycleQueueId?: string | null
    cycleNextRunAt?: string | null
    cycleWaitingReason?: string | null
    cycleCurrentItemId?: string | null
    cycleNextList?: WSCyclePreviewItem[]
  }
  fullMessage?: any
}

// 任务数据只在 WebSocket 快照实际变化时整体替换，避免深层响应式递归开销。
const taskData = shallowRef<Script[]>([])
const taskTreeRef = ref()
const lastTaskSignature = ref('')
const cycleQueueId = ref<string | null>(null)
const cycleNextRunAt = ref<string | null>(null)
const cycleWaitingReason = ref<string | null>(null)
const cycleCurrentItemId = ref<string | null>(null)
const cycleNextList = shallowRef<WSCyclePreviewItem[]>([])
const currentCycleName = computed(
  () =>
    cycleNextList.value.find(item => item.queueItemId === cycleCurrentItemId.value)?.scriptName ||
    cycleCurrentItemId.value ||
    ''
)

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
  const taskSignature = taskInfo
    .map((task, index) => {
      const users = Array.isArray(task.userList)
        ? task.userList.map((user: any) => `${user.name || ''}:${user.status || ''}`).join(',')
        : ''
      return `${task.script_id || index}:${task.name || ''}:${task.status || ''}[${users}]`
    })
    .join('|')
  return `${taskSignature}#${JSON.stringify(cycleNextList.value)}`
}

// 处理 WebSocket 消息
const handleWSMessage = (message: WSMessage) => {
  if (message.type === 'Update') {
    if ('cycleQueueId' in message.data) {
      cycleQueueId.value = message.data.cycleQueueId ?? null
      cycleNextRunAt.value = message.data.cycleNextRunAt ?? null
      cycleWaitingReason.value = message.data.cycleWaitingReason ?? null
      cycleCurrentItemId.value = message.data.cycleCurrentItemId ?? null
      cycleNextList.value = [...(message.data.cycleNextList ?? [])]
    }

    // 处理 task_info 数据（完整的脚本和用户数据）
    if (message.data?.task_info && Array.isArray(message.data.task_info)) {
      const signature = buildTaskInfoSignature(message.data.task_info)
      if (signature === lastTaskSignature.value) {
        return
      }
      lastTaskSignature.value = signature

      const { scriptCount, userCount } = getTaskInfoStats(message.data.task_info)
      logger.debug(`更新任务数据 : 脚本数=${scriptCount}, 用户数=${userCount}`)

      // 转换后端的 task_info 格式到前端的 Script 格式
      const newTaskData = message.data.task_info.map((task: any, index: number) => ({
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
  container: scheduler-overview / inline-size;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--v6-color-surface-transparent);
  border-radius: var(--v6-radius-card);
  box-shadow: var(--v6-shadow-card);
  border: 1px solid var(--v6-color-border-subtle);
  backdrop-filter: blur(18px) saturate(1.08);
  overflow: hidden;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
  padding: var(--v6-space-3) var(--v6-space-4);
  border-bottom: 1px solid var(--v6-color-border-subtle);
  flex-shrink: 0;
}

.section-header h3 {
  margin: 0;
  font-size: var(--v6-font-size-lg);
  font-weight: var(--v6-font-weight-semibold);
  color: var(--v6-color-text);
}

.overview-content {
  flex: 1;
  overflow-y: auto;
  padding: var(--v6-space-4);
}

.cycle-preview {
  padding: var(--v6-space-2) var(--v6-space-4);
  border-bottom: 1px solid var(--v6-color-border-subtle);
  background: var(--v6-color-info-bg);
}

.cycle-preview-heading,
.cycle-preview-list {
  display: flex;
  align-items: center;
  gap: var(--v6-space-2);
  flex-wrap: wrap;
}

.cycle-preview-list {
  margin-top: var(--v6-space-2);
}

.cycle-waiting {
  color: var(--v6-color-text-secondary);
}

.cycle-preview-item {
  padding: var(--v6-space-0-5) var(--v6-space-2);
  border: 1px solid var(--v6-color-border);
  border-radius: var(--v6-radius-full);
  color: var(--v6-color-text-secondary);
  font-size: var(--v6-font-size-sm);
}

.cycle-preview-item.due {
  border-color: var(--v6-color-warning-border);
  color: var(--v6-color-warning);
}

.cycle-preview-item.running {
  border-color: var(--v6-color-info-border);
  color: var(--v6-color-info);
}

/* 滚动条样式 - 浅色 */
.overview-content::-webkit-scrollbar {
  width: 8px;
}

.overview-content::-webkit-scrollbar-track {
  background: transparent;
}

.overview-content::-webkit-scrollbar-thumb {
  background: var(--v6-color-border-strong);
  border-radius: var(--v6-radius-sm);
}

.overview-content::-webkit-scrollbar-thumb:hover {
  background: var(--v6-color-text-tertiary);
}

.empty-state-mini {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
}

/* .overview-panel 自身规则须由外层 scheduler/index.vue 的 scheduler-overview-host
   宿主容器驱动(@container 不能命中声明容器的元素自身) */
@container scheduler-overview-host (max-width: 768px) {
  .overview-panel {
    border-radius: var(--v6-radius-md);
  }
}

@container scheduler-overview (max-width: 768px) {
  .section-header {
    padding: var(--v6-space-3);
  }
}
</style>
