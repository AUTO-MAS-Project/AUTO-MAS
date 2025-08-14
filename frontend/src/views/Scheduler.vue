<template>
  <div class="scheduler-container">
    <!-- 调度台标签页 -->
    <div class="scheduler-tabs">
      <a-tabs
        v-model:activeKey="activeSchedulerTab"
        type="editable-card"
        @edit="onSchedulerTabEdit"
      >
        <a-tab-pane
          v-for="tab in schedulerTabs"
          :key="tab.key"
          :tab="tab.title"
          :closable="tab.closable"
        >
          <!-- 顶部操作栏 -->
          <div class="header-actions">
            <div class="left-actions">
              <!-- 任务完成后操作设置 -->
              <span class="completion-label">任务全部完成后操作：</span>
              <a-select v-model:value="currentTab.completionAction" style="width: 150px">
                <a-select-option value="none">无动作</a-select-option>
                <a-select-option value="exit">退出软件</a-select-option>
                <a-select-option value="sleep">睡眠</a-select-option>
                <a-select-option value="hibernate">休眠</a-select-option>
                <a-select-option value="shutdown">关机</a-select-option>
                <a-select-option value="force-shutdown">关机（强制）</a-select-option>
              </a-select>
              <!--              <a-button type="primary" @click="showAddTaskModal" :icon="h(PlusOutlined)">-->
              <!--                添加任务-->
              <!--              </a-button>-->
            </div>

            <div class="right-actions">
              <a-select
                v-model:value="quickTaskForm.taskId"
                placeholder="选择任务"
                style="width: 200px"
                :loading="taskOptionsLoading"
                :options="taskOptions"
                show-search
                :filter-option="filterTaskOption"
              />
              <a-select
                v-model:value="quickTaskForm.mode"
                placeholder="执行模式"
                style="width: 120px"
              >
                <a-select-option value="自动代理">自动代理</a-select-option>
                <a-select-option value="人工排查">人工排查</a-select-option>
              </a-select>
              <a-button type="primary" @click="startQuickTask" :icon="h(PlayCircleOutlined)">
                开始任务
              </a-button>
            </div>
          </div>

          <!-- 任务执行区域 -->
          <div class="execution-area">
            <div v-if="currentTab.runningTasks.length === 0" class="empty-state">
              <a-empty description="暂无执行中的任务" />
            </div>

            <div v-else class="task-panels">
              <a-collapse v-model:activeKey="currentTab.activeTaskPanels">
                <a-collapse-panel
                  v-for="task in currentTab.runningTasks"
                  :key="task.websocketId"
                  :header="`任务: ${task.taskName}`"
                  style="font-size: 16px; margin-left: 8px"
                >
                  <template #extra>
                    <a-tag :color="getTaskStatusColor(task.status)">
                      {{ task.status }}
                    </a-tag>
                    <a-button
                      type="text"
                      size="small"
                      danger
                      @click.stop="stopTask(task.websocketId)"
                      :icon="h(StopOutlined)"
                    >
                      停止
                    </a-button>
                  </template>

                  <!--                  <div class="task-detail-layout">-->
                  <a-row gutter="16" style="height: 100%">
                    <!-- 任务队列 (20%) -->

                    <a-col :span="5">
                      <a-card title="任务队列" size="small" style="height: 100%">
                        <template :style="{ height: 'calc(100% - 40px)', padding: '8px' }">
                          <a-list
                            :data-source="task.taskQueue"
                            size="small"
                            :locale="{ emptyText: '暂无任务队列' }"
                            style="height: 100%; overflow-y: auto"
                          >
                            <template #renderItem="{ item }">
                              <a-list-item>
                                <a-list-item-meta>
                                  <template #title>
                                    <span class="queue-item-title">{{ item.name }}</span>
                                  </template>
                                  <template #description>
                                    <a-tag
                                      :color="getQueueItemStatusColor(item.status)"
                                      size="small"
                                    >
                                      {{ item.status }}
                                    </a-tag>
                                  </template>
                                </a-list-item-meta>
                              </a-list-item>
                            </template>
                          </a-list>
                        </template>
                      </a-card>
                    </a-col>

                    <!-- 用户队列 (20%) -->
                    <a-col :span="5">
                      <a-card title="用户队列" size="small" style="height: 100%">
                        <template :style="{ height: 'calc(100% - 40px)', padding: '8px' }">
                          <a-list
                            :data-source="task.userQueue"
                            size="small"
                            :locale="{ emptyText: '暂无用户队列' }"
                            style="height: 100%; overflow-y: auto"
                          >
                            <template #renderItem="{ item }">
                              <a-list-item>
                                <a-list-item-meta>
                                  <template #title>
                                    <span class="queue-item-title">{{ item.name }}</span>
                                  </template>
                                  <template #description>
                                    <a-tag
                                      :color="getQueueItemStatusColor(item.status)"
                                      size="small"
                                    >
                                      {{ item.status }}
                                    </a-tag>
                                  </template>
                                </a-list-item-meta>
                              </a-list-item>
                            </template>
                          </a-list>
                        </template>
                      </a-card>
                    </a-col>

                    <!-- 实时日志 (60%) -->
                    <a-col :span="14">
                      <a-card size="small" style="height: 100%" title="实时日志">

                        <div class="realtime-logs-panel">
<!--                          <a-row justify="space-between" align="middle" style="margin-bottom: 8px">-->
<!--                            &lt;!&ndash; 左侧标题 &ndash;&gt;-->
<!--                            <a-col :span="12">-->
<!--                              <div class="log-title">实时日志</div>-->
<!--                            </a-col>-->

<!--                            &lt;!&ndash; 右侧清空按钮 &ndash;&gt;-->
<!--                            <a-col :span="12" style="text-align: right">-->
<!--                              <div class="clear-button">-->
<!--                                <a-button-->
<!--                                  type="default"-->
<!--                                  size="small"-->
<!--                                  @click="clearTaskOutput(task.websocketId)"-->
<!--                                  :icon="h(ClearOutlined)"-->
<!--                                >-->
<!--                                  清空-->
<!--                                </a-button>-->
<!--                              </div>-->
<!--                            </a-col>-->
<!--                          </a-row>-->
                          <div
                            class="panel-content log-content"
                            :ref="el => setOutputRef(el as HTMLElement, task.websocketId)"
                            :key="`output-${task.websocketId}-${task.logs.length}`"
                          >
                            <div
                              v-for="(log, index) in task.logs"
                              :key="`${task.websocketId}-${index}-${log.time}`"
                              :class="['log-line', `log-${log.type}`]"
                            >
                              <span class="log-time">{{ log.time }}</span>
                              <span class="log-message">{{ log.message }}</span>
                            </div>
                          </div>
                        </div>
                      </a-card>
                    </a-col>
                  </a-row>
                </a-collapse-panel>
              </a-collapse>
            </div>
          </div>
        </a-tab-pane>
      </a-tabs>
    </div>

    <!-- 添加任务弹窗 -->
    <a-modal
      v-model:open="addTaskModalVisible"
      title="添加任务"
      @ok="addTask"
      @cancel="cancelAddTask"
      :confirmLoading="addTaskLoading"
    >
      <a-form :model="taskForm" layout="vertical">
        <a-form-item label="选择任务" required>
          <a-select
            v-model:value="taskForm.taskId"
            placeholder="请选择要执行的任务"
            :loading="taskOptionsLoading"
            :options="taskOptions"
            show-search
            :filter-option="filterTaskOption"
          />
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
    <!-- 消息
对话框 -->
    <a-modal
      v-model:open="messageModalVisible"
      :title="currentMessage?.title || '系统消息'"
      @ok="sendMessageResponse"
      @cancel="cancelMessage"
    >
      <div v-if="currentMessage">
        <p>{{ currentMessage.content }}</p>
        <a-input
          v-if="currentMessage.needInput"
          v-model:value="messageResponse"
          placeholder="请输入回复内容"
        />
      </div>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, onUnmounted, h, nextTick, computed } from 'vue'
import { message, notification } from 'ant-design-vue'
import {
  PlusOutlined,
  PlayCircleOutlined,
  StopOutlined,
  ClearOutlined,
} from '@ant-design/icons-vue'
import { Service } from '@/api/services/Service'
import type { ComboBoxItem } from '@/api/models/ComboBoxItem'
import { TaskCreateIn } from '@/api/models/TaskCreateIn'

// 调度台标签页相关
interface SchedulerTab {
  key: string
  title: string
  closable: boolean
  runningTasks: RunningTask[]
  activeTaskPanels: string[]
  completionAction: string
}

const schedulerTabs = ref<SchedulerTab[]>([
  {
    key: 'main',
    title: '主调度台',
    closable: false,
    runningTasks: [],
    activeTaskPanels: [],
    completionAction: 'none',
  },
])

const activeSchedulerTab = ref('main')
let tabCounter = 1

// 当前活动的调度台
const currentTab = computed(() => {
  return (
    schedulerTabs.value.find(tab => tab.key === activeSchedulerTab.value) || schedulerTabs.value[0]
  )
})

// 响应式数据
const addTaskModalVisible = ref(false)
const messageModalVisible = ref(false)
const taskOptionsLoading = ref(false)
const addTaskLoading = ref(false)
const outputRefs = ref<Map<string, HTMLElement>>(new Map())

// 任务选项
const taskOptions = ref<ComboBoxItem[]>([])

// 任务表单（弹窗用）
const taskForm = reactive({
  taskId: null,
  mode: '自动代理' as TaskCreateIn.mode,
})

// 快速任务表单（右上角用）
const quickTaskForm = reactive({
  taskId: null,
  mode: '自动代理' as TaskCreateIn.mode,
})

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
  taskQueue: Array<{
    name: string
    status: string
  }>
  userQueue: Array<{
    name: string
    status: string
  }>
}

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

// 调度台标签页操作
const onSchedulerTabEdit = (targetKey: string | MouseEvent, action: 'add' | 'remove') => {
  if (action === 'add') {
    addSchedulerTab()
  } else if (action === 'remove' && typeof targetKey === 'string') {
    removeSchedulerTab(targetKey)
  }
}

const addSchedulerTab = () => {
  tabCounter++
  const newTab: SchedulerTab = {
    key: `tab-${tabCounter}`,
    title: `调度台${tabCounter}`,
    closable: true,
    runningTasks: [],
    activeTaskPanels: [],
    completionAction: 'none',
  }
  schedulerTabs.value.push(newTab)
  activeSchedulerTab.value = newTab.key
}

const removeSchedulerTab = (targetKey: string) => {
  const targetIndex = schedulerTabs.value.findIndex(tab => tab.key === targetKey)
  if (targetIndex === -1) return

  // 停止该调度台的所有任务
  const targetTab = schedulerTabs.value[targetIndex]
  targetTab.runningTasks.forEach(task => {
    if (task.websocket) {
      task.websocket.close()
    }
  })

  // 移除调度台
  schedulerTabs.value.splice(targetIndex, 1)

  // 如果删除的是当前活动的调度台，切换到其他调度台
  if (activeSchedulerTab.value === targetKey) {
    activeSchedulerTab.value = schedulerTabs.value[Math.max(0, targetIndex - 1)].key
  }
}
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

// 添加任务（弹窗方式，创建新调度台）
const addTask = async () => {
  if (!taskForm.taskId || !taskForm.mode) {
    message.error('请填写完整的任务信息')
    return
  }

  try {
    addTaskLoading.value = true
    const response = await Service.addTaskApiDispatchStartPost({
      taskId: taskForm.taskId,
      mode: taskForm.mode,
    })

    if (response.code === 200) {
      // 创建新的调度台
      addSchedulerTab()

      // 查找任务名称
      const selectedOption = taskOptions.value.find(option => option.value === taskForm.taskId)
      const taskName = selectedOption?.label || '未知任务'

      // 创建任务并添加到新调度台
      const task: RunningTask = {
        websocketId: response.websocketId,
        taskName,
        status: '连接中',
        websocket: null,
        logs: [],
        taskQueue: [],
        userQueue: [],
      }

      // 添加到当前活动的调度台
      currentTab.value.runningTasks.push(task)
      currentTab.value.activeTaskPanels.push(task.websocketId)

      // 连接WebSocket
      connectWebSocket(task)

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
// 快速开始任务（右上角方式，添加到当前调度台）
const startQuickTask = async () => {
  if (!quickTaskForm.taskId || !quickTaskForm.mode) {
    message.error('请选择任务和执行模式')
    return
  }

  try {
    const response = await Service.addTaskApiDispatchStartPost({
      taskId: quickTaskForm.taskId,
      mode: quickTaskForm.mode,
    })

    if (response.code === 200) {
      // 查找任务名称
      const selectedOption = taskOptions.value.find(option => option.value === quickTaskForm.taskId)
      const taskName = selectedOption?.label || '未知任务'

      // 创建任务并添加到当前调度台
      const task: RunningTask = {
        websocketId: response.websocketId,
        taskName,
        status: '连接中',
        websocket: null,
        logs: [],
        taskQueue: [],
        userQueue: [],
      }

      currentTab.value.runningTasks.push(task)
      currentTab.value.activeTaskPanels.push(task.websocketId)

      // 连接WebSocket
      connectWebSocket(task)

      message.success('任务启动成功')

      // 重置表单
      quickTaskForm.taskId = null
      quickTaskForm.mode = '自动代理'
    } else {
      message.error(response.message || '启动任务失败')
    }
  } catch (error) {
    console.error('启动任务失败:', error)
    message.error('启动任务失败')
  }
}

// 取消添加任务
const cancelAddTask = () => {
  addTaskModalVisible.value = false
  taskForm.taskId = null
  taskForm.mode = '自动代理'
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

    ws.onmessage = event => {
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

    ws.onerror = error => {
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
      // 界面更新信息 - 更新任务队列和用户队列
      if (data.data) {
        // 更新任务队列
        if (data.data.task_list) {
          task.taskQueue = data.data.task_list.map((item: any) => ({
            name: item.name || item.id || '未知任务',
            status: item.status || '未知',
          }))
        }

        // 更新用户队列
        if (data.data.task_list) {
          task.userQueue = data.data.task_list.map((user: any) => ({
            name: user.name || user.username || user.id || '未知用户',
            status: user.status || '未知',
          }))
        }

        // 其他更新信息记录到日志
        for (const [key, value] of Object.entries(data.data)) {
          if (key !== 'taskQueue' && key !== 'userQueue') {
            addTaskLog(task, `${key}: ${value}`, 'info')
          }
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
        taskId: task.websocketId,
      }
      messageModalVisible.value = true
      break

    case 'Info':
      // 通知信息
      let level = 'info';
      let content = '未知通知';

      // 检查数据中是否有 Error 字段
      if (data.data?.Error) {
        // 如果是错误信息，设置为 error 级别
        level = 'error';
        content = data.data.Error; // 错误信息内容
      } else {
        // 如果没有 Error 字段，继续处理 val 或 message 字段
        content = data.data?.val || data.data?.message || '未知通知';
      }

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

        // 检查是否所有任务都完成了
        checkAllTasksCompleted()

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
// 检查所有任务是否完成，执行完成后操作
const checkAllTasksCompleted = () => {
  const allCompleted = currentTab.value.runningTasks.every(
    task => task.status === '已完成' || task.status === '已失败' || task.status === '已断开'
  )

  if (allCompleted && currentTab.value.runningTasks.length > 0) {
    executeCompletionAction(currentTab.value.completionAction)
  }
}

// 执行完成后操作
const executeCompletionAction = (action: string) => {
  switch (action) {
    case 'none':
      // 无动作
      break
    case 'exit':
      // 退出软件
      notification.info({ message: '所有任务已完成', description: '正在退出软件...' })
      // 这里可以调用 Electron 的退出方法
      window.close()
      break
    case 'sleep':
      // 睡眠
      notification.info({ message: '所有任务已完成', description: '正在进入睡眠模式...' })
      // 这里需要调用系统睡眠 API
      break
    case 'hibernate':
      // 休眠
      notification.info({ message: '所有任务已完成', description: '正在进入休眠模式...' })
      // 这里需要调用系统休眠 API
      break
    case 'shutdown':
      // 关机
      notification.info({ message: '所有任务已完成', description: '正在关机...' })
      // 这里需要调用系统关机 API
      break
    case 'force-shutdown':
      // 强制关机
      notification.info({ message: '所有任务已完成', description: '正在强制关机...' })
      // 这里需要调用系统强制关机 API
      break
  }
}

// 添加任务日志
const addTaskLog = (
  task: RunningTask,
  message: string,
  type: 'info' | 'error' | 'warning' | 'success' = 'info'
) => {
  const now = new Date()
  const time = now.toLocaleTimeString()

  // 找到任务在当前调度台中的索引
  const taskIndex = currentTab.value.runningTasks.findIndex(t => t.websocketId === task.websocketId)
  if (taskIndex >= 0) {
    // 直接修改 reactive 数组中的任务对象
    currentTab.value.runningTasks[taskIndex].logs.push({
      time,
      message,
      type,
    })

    // 更新任务状态（如果有变化）
    if (currentTab.value.runningTasks[taskIndex].status !== task.status) {
      currentTab.value.runningTasks[taskIndex].status = task.status
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
//发送消息响应
const sendMessageResponse = () => {
  if (!currentMessage.value || !currentMessage.value.taskId) {
    return
  }

  // 在所有调度台中查找任务
  let task: RunningTask | undefined
  for (const tab of schedulerTabs.value) {
    task = tab.runningTasks.find(t => t.websocketId === currentMessage.value?.taskId)
    if (task) break
  }

  if (task && task.websocket) {
    const response = {
      type: 'MessageResponse',
      messageId: currentMessage.value.messageId,
      response: messageResponse.value,
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
  const taskIndex = currentTab.value.runningTasks.findIndex(t => t.websocketId === taskId)
  if (taskIndex >= 0) {
    const task = currentTab.value.runningTasks[taskIndex]

    // 关闭WebSocket连接
    if (task.websocket) {
      task.websocket.close()
      task.websocket = null
    }

    // 从列表中移除
    currentTab.value.runningTasks.splice(taskIndex, 1)

    // 从展开面板中移除
    const panelIndex = currentTab.value.activeTaskPanels.indexOf(taskId)
    if (panelIndex >= 0) {
      currentTab.value.activeTaskPanels.splice(panelIndex, 1)
    }

    message.success('任务已停止')
  }
}

// 清空任务输出
const clearTaskOutput = (taskId: string) => {
  const task = currentTab.value.runningTasks.find(t => t.websocketId === taskId)
  if (task) {
    task.logs = []
  }
}

// 获取任务状态颜色
const getTaskStatusColor = (status: string) => {
  switch (status) {
    case '运行中':
      return 'processing'
    case '已完成':
      return 'success'
    case '已失败':
      return 'error'
    case '连接中':
      return 'default'
    case '已断开':
      return 'warning'
    case '连接错误':
      return 'error'
    case '连接失败':
      return 'error'
    default:
      return 'default'
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
  schedulerTabs.value.forEach(tab => {
    tab.runningTasks.forEach(task => {
      if (task.websocket) {
        task.websocket.close()
      }
    })
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

.scheduler-tabs {
  flex: 1;
  overflow: hidden;
}

.header-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding: 16px;
  border-radius: 8px;
  border: 1px solid var(--ant-color-border);
}

.left-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.right-actions {
  display: flex;
  gap: 12px;
  align-items: center;
}

.completion-label {
  font-size: 14px;
  color: var(--ant-color-text);
  white-space: nowrap;
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

.task-detail-layout {
  display: flex;
  height: 400px;
  gap: 1px;
  border: 1px solid var(--ant-color-border);
  border-radius: 6px;
  overflow: hidden;
}

.realtime-logs-panel {
  display: flex;
  flex-direction: column;
}

.panel-hea der {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  border-bottom: 1px solid var(--ant-color-border);
  font-size: 12px;
  font-weight: 500;
  color: var(--ant-color-text);
}

.panel-content {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.log-content {
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 12px;
  line-height: 1.4;
}

.queue-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 8px;
  margin-bottom: 4px;
  border-radius: 4px;
  font-size: 12px;
}

.queue-item-name {
  flex: 1;
  color: var(--ant-color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.queue-item-status {
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 3px;
  font-weight: 500;
}

.empty-queue {
  text-align: center;
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
  padding: 20px;
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
</style>