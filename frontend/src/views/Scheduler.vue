<template>
  <div class="scheduler-page">
    <!-- 页面头部 -->
    <div class="scheduler-header">
      <div class="header-left">
        <h1 class="page-title">调度中心</h1>
      </div>
      <div class="header-actions">
        <span class="power-label">任务完成后电源操作：</span>
        <a-select 
          v-model:value="powerAction" 
          style="width: 140px"
          :disabled="!canChangePowerAction"
          @change="onPowerActionChange"
        >
          <a-select-option value="NoAction">无动作</a-select-option>
          <a-select-option value="KillSelf">退出软件</a-select-option>
          <a-select-option value="Sleep">睡眠</a-select-option>
          <a-select-option value="Hibernate">休眠</a-select-option>
          <a-select-option value="Shutdown">关机</a-select-option>
          <a-select-option value="ShutdownForce">强制关机</a-select-option>
        </a-select>
      </div>
    </div>

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
          :closable="tab.closable && tab.status !== '运行'"
        >
          <template #tab>
            <span class="tab-title">{{ tab.title }}</span>
            <a-tag :color="getTabStatusColor(tab.status)" size="small" class="tab-status">
              {{ tab.status }}
            </a-tag>
            <a-tooltip v-if="tab.status === '运行'" title="运行中的调度台无法删除" placement="top">
              <span class="tab-lock-icon">🔒</span>
            </a-tooltip>
          </template>

          <!-- 任务控制与状态内容 -->
          <div class="task-unified-card">
            <!-- 顶部控制栏 -->
            <div class="unified-control-row">
                  <a-select 
                    v-model:value="tab.selectedTaskId" 
                    placeholder="选择任务项" 
                    style="width: 200px"
                    :loading="taskOptionsLoading" 
                    :options="taskOptions" 
                    show-search 
                    :filter-option="filterTaskOption"
                    :disabled="tab.status === '运行'"
                  />
                  <a-select 
                    v-model:value="tab.selectedMode" 
                    placeholder="选择模式" 
                    style="width: 120px"
                    :disabled="tab.status === '运行'"
                  >
                    <a-select-option value="自动代理">自动代理</a-select-option>
                    <a-select-option value="人工排查">人工排查</a-select-option>
                    <a-select-option value="设置脚本">设置脚本</a-select-option>
                  </a-select>
                  <div class="control-spacer"></div>
                  <a-button 
                    v-if="tab.status !== '运行'" 
                    type="primary" 
                    @click="startTask(tab)"
                    :icon="h(PlayCircleOutlined)"
                    :disabled="!tab.selectedTaskId || !tab.selectedMode"
                  >
                    开始任务
                  </a-button>
                  <a-button 
                    v-else 
                    danger 
                    @click="stopTask(tab)"
                    :icon="h(StopOutlined)"
                  >
                    中止任务
                  </a-button>
                </div>

                <!-- 状态展示区域 -->
                <a-row :gutter="16" class="status-row">
                  <!-- 任务队列栏 -->
                  <a-col :span="4">
                    <div class="status-column">
                      <div class="section-header">
                        <h3>任务队列</h3>
                      </div>
                      <div class="column-content">
                        <!-- 调试信息 -->
                        <div v-if="false" style="font-size: 10px; color: red; padding: 4px; border: 1px solid red;">
                          Debug Tasks: {{ tab.taskQueue.length }} 
                          <div>{{ JSON.stringify(tab.taskQueue) }}</div>
                        </div>
                        
                        <div v-if="tab.taskQueue.length === 0" class="empty-state-mini">
                          <img src="@/assets/NoData.png" alt="暂无数据" class="empty-image-mini" />
                          <p class="empty-text-mini">暂无任务队列</p>
                        </div>
                        <div v-else class="queue-cards">
                          <a-card 
                            v-for="(task, index) in tab.taskQueue" 
                            :key="`task-${index}`"
                            size="small" 
                            class="queue-card"
                            :class="{ 'running-card': task.status === '运行' }"
                          >
                            <template #title>
                              <div class="card-title-row">
                                <a-tag :color="getQueueStatusColor(task.status)" size="small">
                                  {{ task.status }}
                                </a-tag>
                              </div>
                            </template>
                            <div class="card-content">
                              <p class="task-name">{{ task.name }}</p>
                            </div>
                          </a-card>
                        </div>
                      </div>
                    </div>
                  </a-col>

                  <!-- 用户队列栏 -->
                  <a-col :span="4">
                    <div class="status-column">
                      <div class="section-header">
                        <h3>用户队列</h3>
                      </div>
                      <div class="column-content">
                        <!-- 调试信息 -->
                        <div v-if="false" style="font-size: 10px; color: blue; padding: 4px; border: 1px solid blue;">
                          Debug Users: {{ tab.userQueue.length }}
                          <div>{{ JSON.stringify(tab.userQueue) }}</div>
                        </div>
                        
                        <div v-if="tab.userQueue.length === 0" class="empty-state-mini">
                          <img src="@/assets/NoData.png" alt="暂无数据" class="empty-image-mini" />
                          <p class="empty-text-mini">暂无用户队列</p>
                        </div>
                        <div v-else class="queue-cards">
                          <a-card 
                            v-for="(user, index) in tab.userQueue" 
                            :key="`user-${index}`"
                            size="small" 
                            class="queue-card"
                            :class="{ 'running-card': user.status === '运行' }"
                          >
                            <template #title>
                              <div class="card-title-row">
                                <a-tag :color="getQueueStatusColor(user.status)" size="small">
                                  {{ user.status }}
                                </a-tag>
                              </div>
                            </template>
                            <div class="card-content">
                              <p class="user-name">{{ user.name }}</p>
                            </div>
                          </a-card>
                        </div>
                      </div>
                    </div>
                  </a-col>

                  <!-- 日志栏 -->
                  <a-col :span="16">
                    <div class="status-column">
                      <div class="section-header">
                        <h3>实时日志</h3>
                      </div>
                      <div 
                        class="column-content log-content"
                        :ref="el => setLogRef(el as HTMLElement, tab.key)"
                        @scroll="onLogScroll(tab)"
                      >
                        <div v-if="tab.logs.length === 0" class="empty-state-mini">
                          <img src="@/assets/NoData.png" alt="暂无数据" class="empty-image-mini" />
                          <p class="empty-text-mini">暂无日志信息</p>
                        </div>
                        <div 
                          v-for="(log, index) in tab.logs" 
                          :key="`${tab.key}-${index}-${log.timestamp}`"
                          :class="['log-line', `log-${log.type}`]"
                        >
                          <span class="log-time">{{ log.time }}</span>
                          <span class="log-message">{{ log.message }}</span>
                        </div>
                      </div>
                    </div>
                  </a-col>
                </a-row>
            </div>
        </a-tab-pane>
      </a-tabs>
    </div>

    <!-- 消息对话框 -->
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

    <!-- 电源操作倒计时模态框 -->
    <a-modal
      v-model:open="powerCountdownVisible"
      title="电源操作确认"
      :closable="false"
      :maskClosable="false"
      @cancel="cancelPowerAction"
    >
      <template #footer>
        <a-button @click="cancelPowerAction">取消</a-button>
      </template>
      <div class="power-countdown">
        <div style="color: #faad14; font-size: 24px; margin-right: 16px;">⚠️</div>
        <div>
          <p>所有任务已完成，系统将在 <strong>{{ powerCountdown }}</strong> 秒后执行：<strong>{{ getPowerActionText(powerAction) }}</strong></p>
          <a-progress :percent="(10 - powerCountdown) * 10" :show-info="false" />
        </div>
      </div>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, h, nextTick, computed } from 'vue'
import { message, notification, Modal } from 'ant-design-vue'
import { PlayCircleOutlined, StopOutlined } from '@ant-design/icons-vue'
import { Service } from '@/api/services/Service'
import type { ComboBoxItem } from '@/api/models/ComboBoxItem'
import { TaskCreateIn } from '@/api/models/TaskCreateIn'
import { PowerIn } from '@/api/models/PowerIn'
import { useWebSocket } from '@/composables/useWebSocket'

// 类型定义
interface QueueItem {
  name: string
  status: string
}

interface LogEntry {
  time: string
  message: string
  type: 'info' | 'error' | 'warning' | 'success'
  timestamp: number
}

interface SchedulerTab {
  key: string
  title: string
  closable: boolean
  status: '新建' | '运行' | '结束'
  selectedTaskId: string | null
  selectedMode: TaskCreateIn.mode | null
  websocketId: string | null
  taskQueue: QueueItem[]
  userQueue: QueueItem[]
  logs: LogEntry[]
  isLogAtBottom: boolean
  lastLogContent: string
}

interface TaskMessage { 
  title: string
  content: string
  needInput: boolean
  messageId?: string
  taskId?: string
}

// 状态管理
const schedulerTabs = ref<SchedulerTab[]>([
  { 
    key: 'main', 
    title: '主调度台', 
    closable: false, 
    status: '新建',
    selectedTaskId: null,
    selectedMode: null,
    websocketId: null,
    taskQueue: [], 
    userQueue: [], 
    logs: [],
    isLogAtBottom: true,
    lastLogContent: ''
  }
])
const activeSchedulerTab = ref('main')
let tabCounter = 1

// 电源操作相关
const powerAction = ref<PowerIn.signal>(PowerIn.signal.NO_ACTION)
const powerCountdownVisible = ref(false)
const powerCountdown = ref(10)
let powerCountdownTimer: ReturnType<typeof setInterval> | null = null

// 计算是否可以修改电源操作
const canChangePowerAction = computed(() => {
  return !schedulerTabs.value.some(tab => tab.status === '运行')
})

// UI 状态
const messageModalVisible = ref(false)
const taskOptionsLoading = ref(false)
const taskOptions = ref<ComboBoxItem[]>([])
const logRefs = ref(new Map<string, HTMLElement>())
const currentMessage = ref<TaskMessage | null>(null)
const messageResponse = ref('')

// WebSocket
const { subscribe, unsubscribe, sendRaw } = useWebSocket()

// Tab 操作
const onSchedulerTabEdit = (targetKey: string | MouseEvent, action: 'add' | 'remove') => {
  if (action === 'add') {
    addSchedulerTab()
  } else if (action === 'remove' && typeof targetKey === 'string') {
    removeSchedulerTab(targetKey)
  }
}

const addSchedulerTab = () => {
  tabCounter++
  const tab: SchedulerTab = { 
    key: `tab-${tabCounter}`, 
    title: `调度台${tabCounter}`, 
    closable: true, 
    status: '新建',
    selectedTaskId: null,
    selectedMode: null,
    websocketId: null,
    taskQueue: [], 
    userQueue: [], 
    logs: [],
    isLogAtBottom: true,
    lastLogContent: ''
  }
  schedulerTabs.value.push(tab)
  activeSchedulerTab.value = tab.key
}

const removeSchedulerTab = (key: string) => {
  const tab = schedulerTabs.value.find(t => t.key === key)
  if (!tab) return
  
  // 不允许删除运行中的调度台
  if (tab.status === '运行') {
    Modal.warning({
      title: '无法删除调度台',
      content: `调度台 "${tab.title}" 正在运行中，无法删除。\n\n请先停止当前任务，然后再删除该调度台。`,
      okText: '知道了'
    })
    return
  }
  
  // 不允许删除主调度台
  if (key === 'main') {
    message.warning('主调度台无法删除')
    return
  }

  // 显示确认对话框
  Modal.confirm({
    title: '确认删除',
    content: `确定要删除调度台 "${tab.title}" 吗？删除后无法恢复。`,
    okText: '确认删除',
    cancelText: '取消',
    okType: 'danger',
    onOk() {
      const idx = schedulerTabs.value.findIndex(t => t.key === key)
      if (idx === -1) return
      
      // 如果有WebSocket连接，清理订阅
      if (tab.websocketId) {
        unsubscribe(tab.websocketId)
      }
      
      // 删除标签页
      schedulerTabs.value.splice(idx, 1)
      
      // 如果删除的是当前活动标签页，切换到相邻标签页
      if (activeSchedulerTab.value === key) {
        const newActiveIndex = Math.max(0, idx - 1)
        activeSchedulerTab.value = schedulerTabs.value[newActiveIndex]?.key || 'main'
      }
      
      message.success(`调度台 "${tab.title}" 已删除`)
    }
  })
}

// 电源操作
const onPowerActionChange = (value: PowerIn.signal) => {
  powerAction.value = value
}

const getPowerActionText = (action: PowerIn.signal) => {
  const map = {
    [PowerIn.signal.NO_ACTION]: '无动作',
    [PowerIn.signal.KILL_SELF]: '退出软件',
    [PowerIn.signal.SLEEP]: '睡眠',
    [PowerIn.signal.HIBERNATE]: '休眠',
    [PowerIn.signal.SHUTDOWN]: '关机',
    [PowerIn.signal.SHUTDOWN_FORCE]: '强制关机'
  }
  return map[action] || '无动作'
}

const executePowerAction = async () => {
  try {
    await Service.powerTaskApiDispatchPowerPost({ signal: powerAction.value })
    message.success(`${getPowerActionText(powerAction.value)}命令已发送`)
  } catch (error) {
    console.error('执行电源操作失败:', error)
    message.error('执行电源操作失败')
  }
}

const cancelPowerAction = () => {
  if (powerCountdownTimer) {
    clearInterval(powerCountdownTimer)
    powerCountdownTimer = null
  }
  powerCountdownVisible.value = false
  powerCountdown.value = 10
  powerAction.value = PowerIn.signal.NO_ACTION
}

const startPowerCountdown = () => {
  if (powerAction.value === PowerIn.signal.NO_ACTION) return
  
  powerCountdownVisible.value = true
  powerCountdown.value = 10
  
  powerCountdownTimer = setInterval(() => {
    powerCountdown.value--
    if (powerCountdown.value <= 0) {
      if (powerCountdownTimer) {
        clearInterval(powerCountdownTimer)
        powerCountdownTimer = null
      }
      powerCountdownVisible.value = false
      executePowerAction()
    }
  }, 1000)
}

// 任务操作
const startTask = async (tab: SchedulerTab) => {
  console.log('[Scheduler Debug] 开始启动任务:', {
    tabKey: tab.key,
    selectedTaskId: tab.selectedTaskId,
    selectedMode: tab.selectedMode,
    currentStatus: tab.status
  })
  
  if (!tab.selectedTaskId || !tab.selectedMode) {
    console.warn('[Scheduler Debug] 任务参数不完整')
    message.error('请选择任务项和执行模式')
    return
  }
  
  try {
    // 转换模式为正确的枚举值
    let modeEnum: TaskCreateIn.mode
    switch (tab.selectedMode) {
      case '自动代理':
        modeEnum = TaskCreateIn.mode.AutoMode
        break
      case '人工排查':
        modeEnum = TaskCreateIn.mode.ManualMode
        break
      case '设置脚本':
        modeEnum = TaskCreateIn.mode.SettingScriptMode
        break
      default:
        console.error('[Scheduler Debug] 无效的任务模式:', tab.selectedMode)
        message.error('无效的任务模式')
        return
    }
    
    console.log('[Scheduler Debug] 发送任务创建请求:', {
      taskId: tab.selectedTaskId,
      mode: modeEnum
    })
    
    const response = await Service.addTaskApiDispatchStartPost({
      taskId: tab.selectedTaskId,
      mode: modeEnum
    })
    
    console.log('[Scheduler Debug] 任务创建响应:', response)
    
    if (response.code === 200) {
      tab.status = '运行'
      tab.websocketId = response.websocketId
      console.log('[Scheduler Debug] 设置WebSocket ID:', tab.websocketId)
      
      // 清空之前的状态
      tab.taskQueue = []
      tab.userQueue = []
      tab.logs = []
      tab.isLogAtBottom = true
      tab.lastLogContent = ''
      
      // 添加初始日志
      addLog(tab, `任务开始: ${getTaskName(tab.selectedTaskId)} (模式: ${tab.selectedMode})`, 'info')
      
      // 订阅WebSocket消息
      subscribeToTask(tab)
      console.log('[Scheduler Debug] 已订阅WebSocket消息')
      
      message.success('任务启动成功')
    } else {
      console.error('[Scheduler Debug] 任务启动失败:', response)
      message.error(response.message || '启动任务失败')
    }
  } catch (error) {
    console.error('[Scheduler Debug] 启动任务异常:', error)
    message.error('启动任务失败')
  }
}

const stopTask = async (tab: SchedulerTab) => {
  if (!tab.websocketId) return
  
  try {
    await Service.stopTaskApiDispatchStopPost({ taskId: tab.websocketId })
    
    // 取消订阅
    unsubscribe(tab.websocketId)
    
    tab.status = '结束'
    tab.websocketId = null
    // 任务结束后不清空选择，允许重新开始
    addLog(tab, '任务已停止', 'warning')
    
    message.success('任务已停止')
    checkAllTasksCompleted()
  } catch (error) {
    console.error('停止任务失败:', error)
    message.error('停止任务失败')
    
    // 即使API调用失败，也要清理本地状态
    if (tab.websocketId) {
      unsubscribe(tab.websocketId)
      tab.status = '结束'
      tab.websocketId = null
      addLog(tab, '任务已强制停止', 'warning')
    }
  }
}

// WebSocket消息处理
const subscribeToTask = (tab: SchedulerTab) => {
  console.log('[Scheduler Debug] 订阅WebSocket消息:', {
    tabKey: tab.key,
    websocketId: tab.websocketId
  })
  
  if (!tab.websocketId) {
    console.warn('[Scheduler Debug] WebSocket ID为空，无法订阅')
    return
  }
  
  // 检查WebSocket连接状态
  const { status, getConnectionInfo } = useWebSocket()
  const connectionInfo = getConnectionInfo()
  console.log('[Scheduler Debug] WebSocket连接状态:', {
    status: status.value,
    connectionInfo: connectionInfo
  })
  
  subscribe(tab.websocketId, {
    onProgress: (data) => {
      console.log('[Scheduler Debug] onProgress收到消息:', data)
      handleWebSocketMessage(tab, data)
    },
    onResult: (data) => {
      console.log('[Scheduler Debug] onResult收到消息:', data)
      handleWebSocketMessage(tab, data)
    },
    onError: (data) => {
      console.log('[Scheduler Debug] onError收到消息:', data)
      handleWebSocketMessage(tab, data)
    },
    onNotify: (data) => {
      console.log('[Scheduler Debug] onNotify收到消息:', data)
      handleWebSocketMessage(tab, data)
    }
  })
  
  // 添加连接状态检查
  console.log('[Scheduler Debug] WebSocket订阅完成，等待消息...')
  
  // 检查当前订阅者数量
  const { subscribers } = useWebSocket()
  console.log('[Scheduler Debug] 当前订阅者数量:', subscribers.value.size)
  console.log('[Scheduler Debug] 所有订阅者:', Array.from(subscribers.value.keys()))
}

// 统一的WebSocket消息处理函数
const handleWebSocketMessage = (tab: SchedulerTab, wsMessage: any) => {
  console.log('[Scheduler Debug] 收到WebSocket消息:', {
    tabKey: tab.key,
    tabWebsocketId: tab.websocketId,
    message: wsMessage
  })
  
  // 检查消息是否符合 WebSocketMessage 格式
  if (!wsMessage || typeof wsMessage !== 'object') {
    console.warn('[Scheduler Debug] 收到无效的WebSocket消息:', wsMessage)
    return
  }
  
  const { id, type, data } = wsMessage
  
  console.log('[Scheduler Debug] 解析WebSocket消息:', {
    messageId: id,
    messageType: type,
    messageData: data,
    tabWebsocketId: tab.websocketId,
    isMatch: id === tab.websocketId
  })
  
  // 只处理与当前标签页相关的消息
  if (id !== tab.websocketId) {
    console.log('[Scheduler Debug] 消息ID不匹配，跳过处理')
    return
  }
  
  switch (type) {
    case 'Update':
      console.log('[Scheduler Debug] 处理Update消息')
      handleUpdateMessage(tab, data)
      break
    case 'Info':
      console.log('[Scheduler Debug] 处理Info消息')
      handleInfoMessage(tab, data)
      break
    case 'Message':
      console.log('[Scheduler Debug] 处理Message消息')
      handleMessageDialog(tab, data)
      break
    case 'Signal':
      console.log('[Scheduler Debug] 处理Signal消息')
      handleSignalMessage(tab, data)
      break
    default:
      console.warn('[Scheduler Debug] 未知的WebSocket消息类型:', type, '完整消息:', wsMessage)
      // 尝试作为通用消息处理
      addLog(tab, `收到未知类型消息: ${type} - ${JSON.stringify(data)}`, 'info')
  }
}

const handleUpdateMessage = (tab: SchedulerTab, data: any) => {
  console.log('[Scheduler Debug] 处理Update消息:', {
    tabKey: tab.key,
    data: data,
    hasTaskList: !!data.task_list,
    hasUserList: !!data.user_list,
    taskListLength: data.task_list?.length,
    userListLength: data.user_list?.length
  })
  
  // 更新任务队列
  if (data.task_list && Array.isArray(data.task_list)) {
    console.log('[Scheduler Debug] 更新任务队列:', data.task_list)
    const newTaskQueue = data.task_list.map((item: any) => ({
      name: item.name || '未知任务',
      status: item.status || '未知'
    }))
    tab.taskQueue.splice(0, tab.taskQueue.length, ...newTaskQueue)
    console.log('[Scheduler Debug] 任务队列更新后:', tab.taskQueue)
  }
  
  // 更新用户队列
  if (data.user_list && Array.isArray(data.user_list)) {
    console.log('[Scheduler Debug] 更新用户队列:', data.user_list)
    const newUserQueue = data.user_list.map((item: any) => ({
      name: item.name || '未知用户',
      status: item.status || '未知'
    }))
    tab.userQueue.splice(0, tab.userQueue.length, ...newUserQueue)
    console.log('[Scheduler Debug] 用户队列更新后:', tab.userQueue)
  }
}

const handleInfoMessage = (tab: SchedulerTab, data: any) => {
  console.log('[Scheduler Debug] 处理Info消息:', {
    tabKey: tab.key,
    data: data
  })
  
  if (data.Error) {
    console.log('[Scheduler Debug] 添加错误日志:', data.Error)
    addLog(tab, data.Error, 'error')
    notification.error({ message: '任务错误', description: data.Error })
  } else if (data.Warning) {
    console.log('[Scheduler Debug] 添加警告日志:', data.Warning)
    addLog(tab, data.Warning, 'warning')
    notification.warning({ message: '任务警告', description: data.Warning })
  } else if (data.Info) {
    console.log('[Scheduler Debug] 添加信息日志:', data.Info)
    addLog(tab, data.Info, 'info')
    notification.info({ message: '任务信息', description: data.Info })
  } else {
    // 处理其他信息类型
    console.log('[Scheduler Debug] 处理其他信息类型:', data)
    for (const [key, value] of Object.entries(data)) {
      if (typeof value === 'string') {
        console.log('[Scheduler Debug] 添加其他类型日志:', `${key}: ${value}`)
        addLog(tab, `${key}: ${value}`, 'info')
      }
    }
  }
}

const handleMessageDialog = (tab: SchedulerTab, data: any) => {
  // 处理需要用户输入的消息对话框
  if (data.title && data.content) {
    currentMessage.value = {
      title: data.title,
      content: data.content,
      needInput: data.needInput || false,
      messageId: data.messageId,
      taskId: tab.websocketId || undefined
    }
    messageModalVisible.value = true
  }
}

const handleSignalMessage = (tab: SchedulerTab, data: any) => {
  if (data.Accomplish) {
    addLog(tab, `任务完成: ${data.Accomplish}`, 'success')
    tab.status = '结束'
    
    // 清理WebSocket连接
    if (tab.websocketId) {
      unsubscribe(tab.websocketId)
      tab.websocketId = null
    }
    
    notification.success({ message: '任务完成', description: data.Accomplish })
    checkAllTasksCompleted()
  }
  
  if (data.power) {
    addLog(tab, `电源操作信号: ${data.power}`, 'info')
    // 如果收到电源操作信号，触发倒计时
    if (data.power !== 'NoAction') {
      powerAction.value = data.power as PowerIn.signal
      startPowerCountdown()
    }
  }
}

// 日志处理
const addLog = (tab: SchedulerTab, message: string, type: LogEntry['type'] = 'info') => {
  console.log('[Scheduler Debug] 添加日志:', {
    tabKey: tab.key,
    message: message,
    type: type,
    currentLogsLength: tab.logs.length
  })
  
  const logEntry: LogEntry = {
    time: new Date().toLocaleTimeString(),
    message,
    type,
    timestamp: Date.now()
  }
  
  tab.logs.push(logEntry)
  
  console.log('[Scheduler Debug] 日志添加后:', {
    tabKey: tab.key,
    totalLogs: tab.logs.length,
    isLogAtBottom: tab.isLogAtBottom
  })
  
  // 如果日志在底部，自动滚动
  if (tab.isLogAtBottom) {
    nextTick(() => {
      const el = logRefs.value.get(tab.key)
      if (el) {
        el.scrollTop = el.scrollHeight
        console.log('[Scheduler Debug] 日志自动滚动到底部')
      } else {
        console.warn('[Scheduler Debug] 找不到日志元素，无法滚动')
      }
    })
  }
}

const onLogScroll = (tab: SchedulerTab) => {
  const el = logRefs.value.get(tab.key)
  if (!el) return
  
  // 检查是否滚动到底部
  const threshold = 5
  tab.isLogAtBottom = el.scrollHeight - el.scrollTop - el.clientHeight <= threshold
}

const setLogRef = (el: HTMLElement | null, key: string) => {
  if (el) {
    logRefs.value.set(key, el)
  } else {
    logRefs.value.delete(key)
  }
}

// 完成检测
const checkAllTasksCompleted = () => {
  const hasRunningTasks = schedulerTabs.value.some(tab => tab.status === '运行')
  
  if (!hasRunningTasks && powerAction.value !== PowerIn.signal.NO_ACTION) {
    startPowerCountdown()
  }
}

// 消息弹窗
const sendMessageResponse = () => {
  if (currentMessage.value?.taskId) {
    // 发送WebSocket回复
    sendRaw('Response', {
      messageId: currentMessage.value.messageId,
      response: messageResponse.value
    }, currentMessage.value.taskId)
  }
  
  messageModalVisible.value = false
  messageResponse.value = ''
  currentMessage.value = null
}

const cancelMessage = () => {
  messageModalVisible.value = false
  messageResponse.value = ''
  currentMessage.value = null
}

// 工具函数
const getTaskName = (taskId: string) => {
  const option = taskOptions.value.find(opt => opt.value === taskId)
  return option?.label || '未知任务'
}

const getTabStatusColor = (status: string): string => {
  const colorMap: Record<string, string> = {
    '新建': 'default',
    '运行': 'processing',
    '结束': 'success'
  }
  return colorMap[status] || 'default'
}

const getQueueStatusColor = (status: string) => {
  if (/成功|完成|已完成/.test(status)) return 'green'
  if (/失败|错误|异常/.test(status)) return 'red'
  if (/等待|排队|挂起/.test(status)) return 'orange'
  if (/进行|执行|运行/.test(status)) return 'blue'
  return 'default'
}

const filterTaskOption = (input: string, option: any) => {
  return (option?.label || '').toLowerCase().includes(input.toLowerCase())
}

// 调试工具函数
const testWebSocketConnection = () => {
  const { status, getConnectionInfo, sendRaw } = useWebSocket()
  const connectionInfo = getConnectionInfo()
  
  console.log('[Scheduler Debug] 手动测试WebSocket连接:')
  console.log('状态:', status.value)
  console.log('连接信息:', connectionInfo)
  
  // 尝试发送一个测试消息
  try {
    sendRaw('Signal', { Test: 'Frontend Test Message' })
    console.log('[Scheduler Debug] 测试消息已发送')
  } catch (error) {
    console.error('[Scheduler Debug] 发送测试消息失败:', error)
  }
}

// 在开发者工具中暴露测试函数
if (typeof window !== 'undefined') {
  (window as any).testWebSocketConnection = testWebSocketConnection
}

// 加载任务选项
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

// 生命周期
onMounted(() => {
  console.log('[Scheduler Debug] 组件已挂载，开始初始化')
  
  // 检查WebSocket连接状态
  const { status, getConnectionInfo } = useWebSocket()
  console.log('[Scheduler Debug] 组件初始化时WebSocket状态:', {
    status: status.value,
    connectionInfo: getConnectionInfo()
  })
  
  loadTaskOptions()
  console.log('[Scheduler Debug] 开始加载任务选项')
  
  console.log('[Scheduler Debug] 初始化的调度台标签:', schedulerTabs.value)
})

onUnmounted(() => {
  // 清理定时器
  if (powerCountdownTimer) {
    clearInterval(powerCountdownTimer)
  }
  
  // 取消所有订阅
  schedulerTabs.value.forEach(tab => {
    if (tab.websocketId) {
      unsubscribe(tab.websocketId)
    }
  })
})
</script>

<style scoped>
/* 全局样式 - 禁用页面滚动 */
:global(html, body) {
  overflow: hidden;
}

/* 页面容器 */
.scheduler-page {
  height: 100vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* 页面头部样式 */
.scheduler-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 4px 24px; /* 使用 padding-bottom 替代 margin-bottom */
  flex-shrink: 0;
}

.header-left {
  flex: 1;
}

.page-title {
  margin: 0;
  font-size: 32px;
  font-weight: 700;
  color: var(--ant-color-text);
  background: linear-gradient(135deg, var(--ant-color-primary), var(--ant-color-primary-hover));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.header-actions {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 8px;
}

.power-label {
  font-size: 14px;
  color: #595959;
  white-space: nowrap;
}

.scheduler-tabs {
  flex: 1;
  overflow: hidden;
  background: transparent;
  display: flex; /* 使其成为 flex 容器 */
  flex-direction: column;
  padding-bottom: 16px; /* 将间距放在这里 */
}

.scheduler-tabs :deep(.ant-tabs) {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.scheduler-tabs :deep(.ant-tabs-content-holder) {
  flex: 1; /* 自动填充剩余空间 */
  min-height: 0; /* 关键修复：允许在 flex item 内部滚动 */
  overflow: hidden;
  background: transparent;
}

.scheduler-tabs :deep(.ant-tabs-tabpane) {
  height: 100%;
  overflow: hidden;
}

.scheduler-tabs :deep(.ant-tabs-nav) {
  margin-bottom: 0; /* 移除罪魁祸首 */
}

.scheduler-tabs :deep(.ant-tabs-card > .ant-tabs-nav .ant-tabs-tab) {
  background: var(--ant-color-bg-container);
  border: 1px solid var(--ant-color-border);
  border-radius: 6px 6px 0 0;
  margin-right: 4px;
}

.scheduler-tabs :deep(.ant-tabs-card > .ant-tabs-nav .ant-tabs-tab-active) {
  background: var(--ant-color-bg-container);
  border-bottom-color: var(--ant-color-bg-container);
}

.tab-title {
  margin-right: 8px;
}

.tab-status {
  margin-left: 4px;
}

.tab-lock-icon {
  margin-left: 4px;
  font-size: 12px;
  opacity: 0.7;
}

.task-unified-card {
  height: 100%;
  overflow: hidden;
  border-radius: 12px;
  border: 1px solid var(--ant-color-border);
  background: var(--ant-color-bg-container);
  display: flex;
  flex-direction: column;
}

.status-row {
  flex: 1;
  height: auto !important;
  min-height: 0;
}

.unified-control-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 20px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
  flex-shrink: 0;
  margin-bottom: 16px; /* 将margin移到这里，在flex容器内部 */
}

.control-spacer {
  flex: 1;
}

.status-column {
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 0;
  background-color: var(--ant-color-bg-container);
  border-radius: 8px;
  overflow: hidden;
}

/* section header 样式 */
.section-header {
  margin-bottom: 0;
  padding: 16px 16px 12px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-shrink: 0;
}

.section-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  color: var(--ant-color-text);
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-header h3::before {
  content: '';
  width: 3px;
  height: 18px;
  background: linear-gradient(135deg, var(--ant-color-primary), var(--ant-color-primary-hover));
  border-radius: 2px;
}

.column-content {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  min-height: 0;
}

.log-content {
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 12px;
  line-height: 1.4;
  background: var(--ant-color-bg-layout);
  border: 1px solid var(--ant-color-border);
  border-radius: 8px;
  padding: 12px;
  /* 移除height: 100%，让它继承column-content的布局 */
}

.queue-item-name {
  font-size: 13px;
  color: var(--ant-color-text);
  margin-right: 8px;
  font-weight: 500;
}

.extra-status-tag {
  margin-left: 4px;
}

/* 队列卡片样式 */
.queue-cards {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.queue-card {
  border: 1px solid var(--ant-color-border);
  border-radius: 8px;
  background: var(--ant-color-bg-container);
  transition: all 0.2s ease;
  overflow: hidden;
}

.queue-card:hover {
  border-color: var(--ant-color-primary);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.queue-card.running-card {
  border-color: var(--ant-color-primary);
  background: linear-gradient(135deg, var(--ant-color-primary-bg) 0%, var(--ant-color-bg-container) 100%);
  animation: runningPulse 2s ease-in-out infinite alternate;
}

@keyframes runningPulse {
  0% {
    box-shadow: 0 0 0 0 rgba(24, 144, 255, 0.4);
  }
  100% {
    box-shadow: 0 0 0 4px rgba(24, 144, 255, 0.1);
  }
}

.card-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 4px;
}

.card-content {
  padding: 4px 0;
}

.task-name,
.user-name {
  margin: 0;
  font-size: 13px;
  font-weight: 500;
  color: var(--ant-color-text);
  line-height: 1.4;
  word-break: break-word;
}

.running-card .task-name,
.running-card .user-name {
  color: var(--ant-color-primary);
}

/* 队列卡片在小空间中的响应式 */
.queue-card :deep(.ant-card-head) {
  padding: 8px 12px;
  min-height: auto;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.queue-card :deep(.ant-card-body) {
  padding: 8px 12px;
}

.queue-card :deep(.ant-card-head-title) {
  font-size: 12px;
  font-weight: 500;
}

.log-line {
  display: flex;
  margin-bottom: 2px;
  padding: 2px 0;
  word-break: break-all;
}

.log-time {
  color: var(--ant-color-text-tertiary);
  margin-right: 12px;
  flex-shrink: 0;
  min-width: 80px;
  font-size: 11px;
}

.log-message {
  flex: 1;
  font-size: 12px;
}

.log-info .log-message {
  color: var(--ant-color-text);
}

.log-success .log-message {
  color: var(--ant-color-success);
  font-weight: 500;
}

.log-warning .log-message {
  color: var(--ant-color-warning);
  font-weight: 500;
}

.log-error .log-message {
  color: var(--ant-color-error);
  font-weight: 500;
}

.power-countdown {
  display: flex;
  align-items: flex-start;
  gap: 16px;
}

.power-countdown p {
  margin: 0 0 16px 0;
  font-size: 14px;
  line-height: 1.5;
}

.power-countdown strong {
  color: var(--ant-color-warning);
}

/* 小尺寸空状态样式 */
.empty-state-mini {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 32px 16px;
  text-align: center;
}

.empty-image-mini {
  max-width: 80px;
  max-height: 80px;
  width: auto;
  height: auto;
  margin-bottom: 12px;
  opacity: 0.6;
  object-fit: contain;
}

.empty-text-mini {
  margin: 0;
  font-size: 14px;
  color: var(--ant-color-text-secondary);
}

/* 自定义滚动条样式 */
.column-content::-webkit-scrollbar,
.log-content::-webkit-scrollbar {
  width: 6px;
}

.column-content::-webkit-scrollbar-track,
.log-content::-webkit-scrollbar-track {
  background: var(--ant-color-bg-layout);
  border-radius: 3px;
}

.column-content::-webkit-scrollbar-thumb,
.log-content::-webkit-scrollbar-thumb {
  background: var(--ant-color-border);
  border-radius: 3px;
}

.column-content::-webkit-scrollbar-thumb:hover,
.log-content::-webkit-scrollbar-thumb:hover {
  background: var(--ant-color-text-tertiary);
}

/* 响应式设计 */
@media (max-width: 1200px) {
  .unified-control-row {
    flex-wrap: wrap;
    gap: 8px;
  }
  
  .header-actions {
    flex-wrap: wrap;
    gap: 6px;
  }
  
  .page-title {
    font-size: 28px;
  }
}

@media (max-width: 768px) {
  .scheduler-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 16px;
  }
  
  .header-actions {
    width: 100%;
    justify-content: flex-start;
  }
  
  .page-title {
    font-size: 24px;
  }
  
  .unified-control-row {
    flex-direction: column;
    align-items: stretch;
    padding: 12px 16px;
  }
  
  .unified-control-row > * {
    width: 100%;
  }
  
  .control-spacer {
    display: none;
  }
  
  .status-column {
    padding: 16px;
  }
}

/* Ant Design 组件自定义样式 */
:deep(.ant-tabs-content-holder) {
  overflow: hidden;
  background: transparent;
}

:deep(.ant-tabs-tabpane) {
  height: 100%;
  overflow: hidden;
}

:deep(.ant-row) {
  flex: 1;
  height: 100%;
  min-height: 0;
}

:deep(.ant-col) {
  height: 100%;
  display: flex;
  flex-direction: column;
}

:deep(.ant-list-item) {
  padding: 12px 16px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
  transition: background-color 0.2s ease;
}

:deep(.ant-list-item:hover) {
  background-color: var(--ant-color-fill-tertiary);
}

:deep(.ant-list-item:last-child) {
  border-bottom: none;
}

:deep(.ant-list-item-meta-title) {
  margin-bottom: 4px;
  font-size: 13px;
  font-weight: 500;
}

:deep(.ant-list-item-meta-description) {
  font-size: 12px;
  color: var(--ant-color-text-secondary);
}

:deep(.ant-tag) {
  margin: 0;
  font-size: 11px;
  line-height: 18px;
  border-radius: 6px;
  font-weight: 500;
}

:deep(.ant-progress-inner) {
  background-color: var(--ant-color-fill-secondary);
}

:deep(.ant-progress-bg) {
  background: linear-gradient(90deg, var(--ant-color-warning), var(--ant-color-error));
}

:deep(.ant-select) {
  border-radius: 6px;
}

:deep(.ant-btn) {
  border-radius: 6px;
  font-weight: 500;
}
</style>
