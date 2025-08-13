<template>
  <div class="scheduler-container">
    <!-- 顶部操作栏 -->
    <div class="header-actions">
      <a-button type="primary" @click="showAddTaskModal" :icon="h(PlusOutlined)">
        添加任务
      </a-button>
    </div>

    <!-- 已创建的任务显示区域 -->
    <div v-if="createdTask" class="created-task-section">
      <a-card size="small" class="task-card">
        <div class="task-info">
          <div class="task-details">
            <h4>{{ createdTask.taskName }}</h4>
            <p class="task-meta">
              <span>WebSocket ID: {{ createdTask.websocketId }}</span>
              <span>执行模式: {{ createdTask.mode }}</span>
            </p>
          </div>
          <a-button type="primary" @click="startCreatedTask" :icon="h(PlayCircleOutlined)">
            开始执行
          </a-button>
        </div>
      </a-card>
    </div>

    <!-- 任务执行区域 -->
    <div class="execution-area">
      <div v-if="runningTasks.length === 0" class="empty-state">
        <a-empty description="暂无执行中的任务" />
      </div>

      <div v-else class="task-panels">
        <a-collapse v-model:activeKey="activeTaskPanels" ghost>
          <a-collapse-panel v-for="task in runningTasks" :key="task.websocketId"
            :header="`任务: ${task.taskName} (${task.websocketId})`">
            <template #extra>
              <a-tag :color="getTaskStatusColor(task.status)">
                {{ task.status }}
              </a-tag>
              <a-button type="text" size="small" danger @click.stop="stopTask(task.websocketId)"
                :icon="h(StopOutlined)">
                停止
              </a-button>
            </template>

            <div class="task-output">
              <div class="output-header">
                <span>输出日志</span>
                <a-button type="text" size="small" @click="clearTaskOutput(task.websocketId)" :icon="h(ClearOutlined)">
                  清空
                </a-button>
              </div>
              <div class="output-content" :ref="el => setOutputRef(el as HTMLElement, task.websocketId)"
                :key="`output-${task.websocketId}-${task.logs.length}`">
                <div v-for="(log, index) in task.logs" :key="`${task.websocketId}-${index}-${log.time}`"
                  :class="['log-line', `log-${log.type}`]">
                  <span class="log-time">{{ log.time }}</span>
                  <span class="log-message">{{ log.message }}</span>
                </div>
              </div>
            </div>
          </a-collapse-panel>
        </a-collapse>
      </div>
    </div>

    <!-- 添加任务弹窗 -->
    <a-modal v-model:open="addTaskModalVisible" title="添加任务" @ok="addTask" @cancel="cancelAddTask"
      :confirmLoading="addTaskLoading">
      <a-form :model="taskForm" layout="vertical">
        <a-form-item label="选择任务" required>
          <a-select v-model:value="taskForm.taskId" placeholder="请选择要执行的任务" :loading="taskOptionsLoading"
            :options="taskOptions" show-search :filter-option="filterTaskOption" />
        </a-form-item>
        <a-form-item label="执行模式" required>
          <a-select v-model:value="taskForm.mode" placeholder="请选择执行模式">
            <a-select-option value="自动代理">自动代理</a-select-option>
            <a-select-option value="人工排查">人工排查</a-select-option>
            <a-select-option value="设置脚本">设置脚本</a-select-option>
          </a-select>
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- 消息对话框 -->
    <a-modal v-model:open="messageModalVisible" :title="currentMessage?.title || '系统消息'" @ok="sendMessageResponse"
      @cancel="cancelMessage">
      <div v-if="currentMessage">
        <p>{{ currentMessage.content }}</p>
        <a-input v-if="currentMessage.needInput" v-model:value="messageResponse" placeholder="请输入回复内容" />
      </div>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, onUnmounted, h, nextTick, triggerRef } from 'vue'
import { message, notification } from 'ant-design-vue'
import {
  PlusOutlined,
  PlayCircleOutlined,
  StopOutlined,
  ClearOutlined
} from '@ant-design/icons-vue'
import { Service } from '@/api/services/Service'
import type { ComboBoxItem } from '@/api/models/ComboBoxItem'
import { TaskCreateIn } from '@/api/models/TaskCreateIn'

// 响应式数据
const addTaskModalVisible = ref(false)
const messageModalVisible = ref(false)
const taskOptionsLoading = ref(false)
const addTaskLoading = ref(false)
const activeTaskPanels = ref<string[]>([])
const outputRefs = ref<Map<string, HTMLElement>>(new Map())

// 任务选项
const taskOptions = ref<ComboBoxItem[]>([])

// 任务表单
const taskForm = reactive({
  taskId: null,
  mode: '自动代理' as TaskCreateIn.mode
})

// 已创建的任务
interface CreatedTask {
  websocketId: string
  taskName: string
  mode: string
  originalTaskId: string
}

const createdTask = ref<CreatedTask | null>(null)

// 运行中的任务
interface RunningTask {
  websocketId: string
  taskName: string
  status: string
  websocket: WebSocket | null
  logs: Array<{
    time: string
    message: string
    type: 'info' | 'error' | 'warning' | 'success'
  }>
}

const runningTasks = reactive<RunningTask[]>([])

// 消息处理
interface TaskMessage {
  title: string
  content: string
  needInput: boolean
  messageId?: string
  taskId?: string
}

const currentMessage = ref<TaskMessage | null>(null)
const messageResponse = ref('')

// 设置输出容器引用
const setOutputRef = (el: HTMLElement | null, websocketId: string) => {
  if (el) {
    outputRefs.value.set(websocketId, el)
  } else {
    outputRefs.value.delete(websocketId)
  }
}

// 获取任务选项
const loadTaskOptions = async () => {
  try {
    taskOptionsLoading.value = true
    const response = await Service.getTaskComboxApiInfoComboxTaskPost()
    if (response.code === 200) {
      taskOptions.value = response.data
    } else {
      message.error('获取任务列表失败')
    }
  } catch (error) {
    console.error('获取任务列表失败:', error)
    message.error('获取任务列表失败')
  } finally {
    taskOptionsLoading.value = false
  }
}

// 显示添加任务弹窗
const showAddTaskModal = () => {
  addTaskModalVisible.value = true
  if (taskOptions.value.length === 0) {
    loadTaskOptions()
  }
}

// 添加任务
const addTask = async () => {
  if (!taskForm.taskId || !taskForm.mode) {
    message.error('请填写完整的任务信息')
    return
  }
  if (
    taskForm.taskId === ''
  ) {
    message.error('请选择要执行的任务')
    return
  }

  try {
    addTaskLoading.value = true
    const response = await Service.addTaskApiDispatchStartPost({
      taskId: taskForm.taskId,
      mode: taskForm.mode
    })

    if (response.code === 200) {
      // 查找任务名称
      const selectedOption = taskOptions.value.find(option => option.value === taskForm.taskId)
      const taskName = selectedOption?.label || '未知任务'

      // 保存创建的任务信息
      createdTask.value = {
        websocketId: response.websocketId,
        taskName,
        mode: taskForm.mode,
        originalTaskId: taskForm.taskId
      }

      message.success('任务创建成功')
      addTaskModalVisible.value = false

      // 重置表单
      taskForm.taskId = null
      taskForm.mode = '自动代理'
    } else {
      message.error(response.message || '创建任务失败')
    }
  } catch (error) {
    console.error('创建任务失败:', error)
    message.error('创建任务失败')
  } finally {
    addTaskLoading.value = false
  }
}

// 取消添加任务
const cancelAddTask = () => {
  addTaskModalVisible.value = false
  taskForm.taskId = null
  taskForm.mode = '自动代理'
}

// 开始已创建的任务
const startCreatedTask = () => {
  if (!createdTask.value) {
    message.error('没有可执行的任务')
    return
  }

  // 创建任务对象
  const task: RunningTask = {
    websocketId: createdTask.value.websocketId,
    taskName: createdTask.value.taskName,
    status: '连接中',
    websocket: null,
    logs: []
  }

  // 添加到运行任务列表
  runningTasks.push(task)
  activeTaskPanels.value.push(task.websocketId)

  // 连接WebSocket
  connectWebSocket(task)

  // 清空已创建的任务
  createdTask.value = null
}

// 连接WebSocket
const connectWebSocket = (task: RunningTask) => {
  const wsUrl = `ws://localhost:8000/api/dispatch/ws/${task.websocketId}`


  try {
    const ws = new WebSocket(wsUrl)
    task.websocket = ws

    ws.onopen = () => {
      task.status = '运行中'
      addTaskLog(task, '已连接到任务服务器', 'success')
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        handleWebSocketMessage(task, data)
      } catch (error) {
        console.error('解析WebSocket消息失败:', error)
        addTaskLog(task, `收到无效消息: ${event.data}`, 'error')
      }
    }

    ws.onclose = () => {
      task.status = '已断开'
      addTaskLog(task, '与服务器连接已断开', 'warning')
      task.websocket = null
    }

    ws.onerror = (error) => {
      task.status = '连接错误'
      addTaskLog(task, '连接发生错误', 'error')
      console.error('WebSocket错误:', error)
    }
  } catch (error) {
    task.status = '连接失败'
    addTaskLog(task, '无法连接到服务器', 'error')
    console.error('WebSocket连接失败:', error)
  }
}

// 处理WebSocket消息
const handleWebSocketMessage = (task: RunningTask, data: any) => {
  switch (data.type) {
    case 'Update':
      // 界面更新信息
      if (data.data) {
        for (const [key, value] of Object.entries(data.data)) {
          addTaskLog(task, `${key}: ${value}`, 'info')
        }
      }
      break

    case 'Message':
      // 需要用户输入的消息
      currentMessage.value = {
        title: '任务消息',
        content: data.message || '任务需要您的输入',
        needInput: true,
        messageId: data.messageId,
        taskId: task.websocketId
      }
      messageModalVisible.value = true
      break

    case 'Info':
      // 通知信息
      const level = data.key || 'info'
      const content = data.val || data.message || '未知通知'

      addTaskLog(task, content, level as any)

      // 显示系统通知
      if (level === 'error') {
        notification.error({ message: '任务错误', description: content })
      } else if (level === 'warning') {
        notification.warning({ message: '任务警告', description: content })
      } else if (level === 'success') {
        notification.success({ message: '任务成功', description: content })
      } else {
        notification.info({ message: '任务信息', description: content })
      }
      break

    case 'Signal':
      // 状态信号
      if (data.data?.Accomplish !== undefined) {
        task.status = data.data.Accomplish ? '已完成' : '已失败'
        addTaskLog(task, `任务${task.status}`, data.data.Accomplish ? 'success' : 'error')

        // 断开连接
        if (task.websocket) {
          task.websocket.close()
          task.websocket = null
        }
      }
      break

    default:
      addTaskLog(task, `收到未知消息类型: ${data.type}`, 'warning')
  }
}

// 添加任务日志
const addTaskLog = (task: RunningTask, message: string, type: 'info' | 'error' | 'warning' | 'success' = 'info') => {
  const now = new Date()
  const time = now.toLocaleTimeString()

  // 找到任务在数组中的索引
  const taskIndex = runningTasks.findIndex(t => t.websocketId === task.websocketId)
  if (taskIndex >= 0) {
    // 直接修改 reactive 数组中的任务对象
    runningTasks[taskIndex].logs.push({
      time,
      message,
      type
    })

    // 更新任务状态（如果有变化）
    if (runningTasks[taskIndex].status !== task.status) {
      runningTasks[taskIndex].status = task.status
    }
  }

  // 自动滚动到底部
  nextTick(() => {
    const outputElement = outputRefs.value.get(task.websocketId)
    if (outputElement) {
      outputElement.scrollTop = outputElement.scrollHeight
    }
  })
}

// 发送消息响应
const sendMessageResponse = () => {
  if (!currentMessage.value || !currentMessage.value.taskId) {
    return
  }

  const task = runningTasks.find(t => t.websocketId === currentMessage.value?.taskId)
  if (task && task.websocket) {
    const response = {
      type: 'MessageResponse',
      messageId: currentMessage.value.messageId,
      response: messageResponse.value
    }

    task.websocket.send(JSON.stringify(response))
    addTaskLog(task, `用户回复: ${messageResponse.value}`, 'info')
  }

  messageModalVisible.value = false
  messageResponse.value = ''
  currentMessage.value = null
}

// 取消消息
const cancelMessage = () => {
  messageModalVisible.value = false
  messageResponse.value = ''
  currentMessage.value = null
}

// 停止任务
const stopTask = (taskId: string) => {
  const taskIndex = runningTasks.findIndex(t => t.websocketId === taskId)
  if (taskIndex >= 0) {
    const task = runningTasks[taskIndex]

    // 关闭WebSocket连接
    if (task.websocket) {
      task.websocket.close()
      task.websocket = null
    }

    // 从列表中移除
    runningTasks.splice(taskIndex, 1)

    // 从展开面板中移除
    const panelIndex = activeTaskPanels.value.indexOf(taskId)
    if (panelIndex >= 0) {
      activeTaskPanels.value.splice(panelIndex, 1)
    }

    message.success('任务已停止')
  }
}

// 清空任务输出
const clearTaskOutput = (taskId: string) => {
  const task = runningTasks.find(t => t.websocketId === taskId)
  if (task) {
    task.logs = []
  }
}

// 获取任务状态颜色
const getTaskStatusColor = (status: string) => {
  switch (status) {
    case '运行中': return 'processing'
    case '已完成': return 'success'
    case '已失败': return 'error'
    case '连接中': return 'default'
    case '已断开': return 'warning'
    case '连接错误': return 'error'
    case '连接失败': return 'error'
    default: return 'default'
  }
}

// 任务选项过滤
const filterTaskOption = (input: string, option: any) => {
  return option.label.toLowerCase().includes(input.toLowerCase())
}

// 组件挂载时加载任务选项
onMounted(() => {
  loadTaskOptions()
})

// 组件卸载时清理WebSocket连接
onUnmounted(() => {
  runningTasks.forEach(task => {
    if (task.websocket) {
      task.websocket.close()
    }
  })
})
</script>

<style scoped>
.scheduler-container {
  padding: 24px;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.header-actions {
  display: flex;
  gap: 12px;
  margin-bottom: 24px;
}

.execution-area {
  flex: 1;
  overflow: hidden;
}

.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 300px;
}

.task-panels {
  height: 100%;
  overflow-y: auto;
}

.task-output {
  border: 1px solid var(--ant-color-border);
  border-radius: 6px;
  overflow: hidden;
}

.output-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background-color: var(--ant-color-fill-quaternary);
  border-bottom: 1px solid var(--ant-color-border);
  font-size: 12px;
  font-weight: 500;
}

.output-content {
  height: 300px;
  overflow-y: auto;
  padding: 8px;
  background-color: var(--ant-color-bg-container);
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 12px;
  line-height: 1.4;
}

.log-line {
  display: flex;
  margin-bottom: 2px;
  word-break: break-all;
}

.log-time {
  color: var(--ant-color-text-tertiary);
  margin-right: 8px;
  flex-shrink: 0;
  min-width: 80px;
}

.log-message {
  flex: 1;
}

.log-info .log-message {
  color: var(--ant-color-text);
}

.log-success .log-message {
  color: var(--ant-color-success);
}

.log-warning .log-message {
  color: var(--ant-color-warning);
}

.log-error .log-message {
  color: var(--ant-color-error);
}

/* 已创建任务区域样式 */
.created-task-section {
  margin-bottom: 24px;
}

.task-card {
  border: 1px solid var(--ant-color-border);
  border-radius: 8px;
}

.task-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.task-details h4 {
  margin: 0 0 8px 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.task-meta {
  margin: 0;
  font-size: 12px;
  color: var(--ant-color-text-secondary);
  display: flex;
  gap: 16px;
}

.task-meta span {
  display: inline-block;
}

/* 深色模式适配 */
@media (prefers-color-scheme: dark) {
  .output-content {
    background-color: var(--ant-color-bg-elevated);
  }

  .task-card {
    background-color: var(--ant-color-bg-elevated);
  }
}
</style>