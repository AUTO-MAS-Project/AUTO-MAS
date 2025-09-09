<template>
  <div class="scheduler-container">
    <!-- 调度台标签页 -->
    <div class="scheduler-tabs">
      <a-tabs v-model:activeKey="activeSchedulerTab" type="editable-card" @edit="onSchedulerTabEdit">
        <a-tab-pane v-for="tab in schedulerTabs" :key="tab.key" :tab="tab.title" :closable="tab.closable">
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
              <a-select v-model:value="quickTaskForm.taskId" placeholder="选择任务" style="width: 200px"
                :loading="taskOptionsLoading" :options="taskOptions" show-search :filter-option="filterTaskOption" />
              <a-select v-model:value="quickTaskForm.mode" placeholder="执行模式" style="width: 120px">
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
             <img src="@/assets/NoData.png" alt="无数据" class="empty-image" />
            </div>

            <div v-else class="task-panels">
              <a-collapse v-model:activeKey="currentTab.activeTaskPanels"
                :key="`collapse-${currentTab.key}-${currentTab.runningTasks.length}`">
                <a-collapse-panel v-for="task in currentTab.runningTasks" :key="task.websocketId"
                  :header="`任务: ${task.taskName}`" style="font-size: 16px; margin-left: 8px">
                  <template #extra>
                    <a-tag :color="getTaskStatusColor(task.status)">
                      {{ task.status }}
                    </a-tag>
                    <a-button type="text" size="small" danger @click.stop="stopTask(task.websocketId)"
                      :icon="h(StopOutlined)">
                      停止
                    </a-button>
                  </template>

                  <!--                  <div class="task-detail-layout">-->
                  <a-row :gutter="16" style="height: 100%">
                    <!--                    &lt;!&ndash; 任务队列  &ndash;&gt;-->
                    <!--                    <a-col :span="5">-->
                    <!--                      <a-card title="任务队列" size="small" style="height: 100%">-->
                    <!--                        <template :style="{ height: 'calc(100% - 40px)', padding: '8px' }">-->
                    <!--                          <a-list-->
                    <!--                            :data-source="task.taskQueue"-->
                    <!--                            size="small"-->
                    <!--                            :locale="{ emptyText: '暂无任务队列' }"-->
                    <!--                            style="height: 100%; overflow-y: auto"-->
                    <!--                          >-->
                    <!--                            <template #renderItem="{ item }">-->
                    <!--                              <a-list-item>-->
                    <!--                                <a-list-item-meta>-->
                    <!--                                  <template #title>-->
                    <!--                                    <span class="queue-item-title">{{ item.name }}</span>-->
                    <!--                                  </template>-->
                    <!--                                  <template #description>-->
                    <!--                                    <a-tag-->
                    <!--                                      :color="getQueueItemStatusColor(item.status)"-->
                    <!--                                      size="small"-->
                    <!--                                    >-->
                    <!--                                      {{ item.status }}-->
                    <!--                                    </a-tag>-->
                    <!--                                  </template>-->
                    <!--                                </a-list-item-meta>-->
                    <!--                              </a-list-item>-->
                    <!--                            </template>-->
                    <!--                          </a-list>-->
                    <!--                        </template>-->
                    <!--                      </a-card>-->
                    <!--                    </a-col>-->

                    <!-- 用户队列 -->
                    <a-col :span="5">
                      <a-card title="用户队列" size="small" style="height: 100%">
                        <!--                        <template #extra>-->
                        <!--                          <span style="font-size: 12px; color: #666;">{{ task.userQueue.length }} 项</span>-->
                        <!--                        </template>-->
                        <div style="height: calc(100% - 40px); padding: 8px;">
                          <!--                          &lt;!&ndash; 调试信息 &ndash;&gt;-->
                          <!--                          <div v-if="task.userQueue.length === 0"-->
                          <!--                            style="color: #999; font-size: 12px; margin-bottom: 8px;">-->
                          <!--                            调试: userQueue 长度为 {{ task.userQueue.length }}-->
                          <!--                          </div>-->
                          <!--                          <div v-else style="color: #999; font-size: 12px; margin-bottom: 8px;">-->
                          <!--                            调试: 找到 {{ task.userQueue.length }} 个队列项-->
                          <!--                          </div>-->

                          <a-list :data-source="task.userQueue" size="small" :locale="{ emptyText: '暂无用户队列' }"
                            style="height: calc(100% - 30px); overflow-y: auto">
                            <template #renderItem="{ item }">
                              <a-list-item>
                                <a-list-item-meta>
                                  <template #title>
                                    <span class="queue-item-title">{{ item.name }}</span>
                                    <a-tag :color="getQueueItemStatusColor(item.status)" size="small">
                                      {{ item.status }}
                                    </a-tag>
                                  </template>
                                </a-list-item-meta>
                              </a-list-item>
                            </template>
                          </a-list>
                        </div>
                      </a-card>
                    </a-col>

                    <!-- 实时日志 -->
                    <a-col :span="19">
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
                          <div class="panel-content log-content"
                            :ref="el => setOutputRef(el as HTMLElement, task.websocketId)"
                            :key="`output-${task.websocketId}-${task.logs.length}`">
                            <div v-for="(log, index) in task.logs" :key="`${task.websocketId}-${index}-${log.time}`"
                              :class="['log-line', `log-${log.type}`]">
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
    <!-- 消息
对话框 -->
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
import { ref, reactive, onMounted, onUnmounted, h, nextTick, computed } from 'vue'
import { message, notification } from 'ant-design-vue'
import { PlayCircleOutlined, StopOutlined } from '@ant-design/icons-vue'
import { Service } from '@/api/services/Service'
import type { ComboBoxItem } from '@/api/models/ComboBoxItem'
import { TaskCreateIn } from '@/api/models/TaskCreateIn'
import { useWebSocket, type WebSocketBaseMessage } from '@/composables/useWebSocket'

// 类型定义
interface RunningTask {
  websocketId: string
  taskName: string
  status: string
  logs: Array<{ time: string; message: string; type: 'info' | 'error' | 'warning' | 'success' }>
  taskQueue: Array<{ name: string; status: string }>
  userQueue: Array<{ name: string; status: string }>
}
interface SchedulerTab {
  key: string
  title: string
  closable: boolean
  runningTasks: RunningTask[]
  activeTaskPanels: string[]
  completionAction: string
}
interface TaskMessage { title: string; content: string; needInput: boolean; messageId?: string; taskId?: string }

// 状态
const schedulerTabs = ref<SchedulerTab[]>([{ key: 'main', title: '主调度台', closable: false, runningTasks: [], activeTaskPanels: [], completionAction: 'none' }])
const activeSchedulerTab = ref('main')
let tabCounter = 1
const currentTab = computed(() => schedulerTabs.value.find(t => t.key === activeSchedulerTab.value) || schedulerTabs.value[0])

const addTaskModalVisible = ref(false)
const messageModalVisible = ref(false)
const taskOptionsLoading = ref(false)
const addTaskLoading = ref(false)
const taskOptions = ref<ComboBoxItem[]>([])
const outputRefs = ref(new Map<string, HTMLElement>())
const currentMessage = ref<TaskMessage | null>(null)
const messageResponse = ref('')

// 表单
const taskForm = reactive<{ taskId: string | null; mode: TaskCreateIn.mode }>({ taskId: null, mode: TaskCreateIn.mode.AutoMode })
const quickTaskForm = reactive<{ taskId: string | null; mode: TaskCreateIn.mode }>({ taskId: null, mode: TaskCreateIn.mode.AutoMode })

// WebSocket API
const { connect: wsConnect, disconnect: wsDisconnect, sendRaw } = useWebSocket()

// Tab 事件
const onSchedulerTabEdit = (targetKey: string | MouseEvent, action: 'add' | 'remove') => {
  if (action === 'add') addSchedulerTab()
  else if (action === 'remove' && typeof targetKey === 'string') removeSchedulerTab(targetKey)
}
const addSchedulerTab = () => {
  tabCounter++
  const tab: SchedulerTab = { key: `tab-${tabCounter}`, title: `调度台${tabCounter}`, closable: true, runningTasks: [], activeTaskPanels: [], completionAction: 'none' }
  schedulerTabs.value.push(tab)
  activeSchedulerTab.value = tab.key
}
const removeSchedulerTab = (key: string) => {
  const idx = schedulerTabs.value.findIndex(t => t.key === key)
  if (idx === -1) return
  schedulerTabs.value[idx].runningTasks.forEach(t => wsDisconnect(t.websocketId))
  schedulerTabs.value.splice(idx, 1)
  if (activeSchedulerTab.value === key) activeSchedulerTab.value = schedulerTabs.value[Math.max(0, idx - 1)]?.key || 'main'
}

// 引用
const setOutputRef = (el: HTMLElement | null, id: string) => { if (el) outputRefs.value.set(id, el); else outputRefs.value.delete(id) }

// 拉取任务选项
const loadTaskOptions = async () => {
  try {
    taskOptionsLoading.value = true
    const r = await Service.getTaskComboxApiInfoComboxTaskPost()
    if (r.code === 200) taskOptions.value = r.data
    else message.error('获取任务列表失败')
  } catch (e) {
    console.error(e)
    message.error('获取任务列表失败')
  } finally {
    taskOptionsLoading.value = false
  }
}

// 添加任务（新 Tab）
const addTask = async () => {
  if (!taskForm.taskId) return message.error('请填写完整的任务信息')
  try {
    addTaskLoading.value = true
    const r = await Service.addTaskApiDispatchStartPost({ taskId: taskForm.taskId, mode: taskForm.mode })
    if (r.code === 200) {
      addSchedulerTab()
      const opt = taskOptions.value.find(o => o.value === taskForm.taskId)
      const task: RunningTask = { websocketId: r.websocketId, taskName: opt?.label || '未知任务', status: '连接中', logs: [], taskQueue: [], userQueue: [] }
      currentTab.value.runningTasks.push(task)
      currentTab.value.activeTaskPanels.push(task.websocketId)
      subscribeTask(task, taskForm.mode)
      message.success('任务创建成功')
      addTaskModalVisible.value = false
      taskForm.taskId = null
      taskForm.mode = TaskCreateIn.mode.AutoMode
    } else message.error(r.message || '创建任务失败')
  } catch (e) {
    console.error(e)
    message.error('创建任务失败')
  } finally { addTaskLoading.value = false }
}

// 快速开始（当前 Tab）
const startQuickTask = async () => {
  if (!quickTaskForm.taskId) return message.error('请选择任务和执行模式')
  try {
    const r = await Service.addTaskApiDispatchStartPost({ taskId: quickTaskForm.taskId, mode: quickTaskForm.mode })
    if (r.code === 200) {
      const opt = taskOptions.value.find(o => o.value === quickTaskForm.taskId)
      const name = opt?.label || '未知任务'
      const idx = currentTab.value.runningTasks.findIndex(t => t.taskName === name)
      if (idx >= 0) {
        const existing = currentTab.value.runningTasks[idx]
        wsDisconnect(existing.websocketId)
        const oldId = existing.websocketId
        existing.websocketId = r.websocketId
        existing.status = '连接中'
        existing.userQueue = []
        existing.logs.push({ time: new Date().toLocaleTimeString(), message: '========== 新任务开始 ==========', type: 'info' })
        const pIdx = currentTab.value.activeTaskPanels.indexOf(oldId)
        if (pIdx >= 0) currentTab.value.activeTaskPanels.splice(pIdx, 1)
        currentTab.value.activeTaskPanels.push(existing.websocketId)
        subscribeTask(existing, quickTaskForm.mode)
      } else {
        const task: RunningTask = { websocketId: r.websocketId, taskName: name, status: '连接中', logs: [], taskQueue: [], userQueue: [] }
        currentTab.value.runningTasks.push(task)
        currentTab.value.activeTaskPanels.push(task.websocketId)
        subscribeTask(task, quickTaskForm.mode)
      }
      quickTaskForm.taskId = null
      quickTaskForm.mode = TaskCreateIn.mode.AutoMode
      message.success('任务启动成功')
    } else message.error(r.message || '启动任务失败')
  } catch (e) {
    console.error(e)
    message.error('启动任务失败')
  }
}

// 订阅任务
const subscribeTask = (task: RunningTask, mode: TaskCreateIn.mode) => {
  wsConnect({
    taskId: task.websocketId,
    mode,
    onMessage: raw => handleWebSocketMessage(task, raw),
    onStatusChange: st => {
      if (st === '已连接' && task.status === '连接中') task.status = '运行中'
      if (st === '已断开' && task.status === '运行中') task.status = '已断开'
      if (st === '连接错误') task.status = '连接错误'
    }
  })
}

// 取消添加
const cancelAddTask = () => {
  addTaskModalVisible.value = false
  taskForm.taskId = null
  taskForm.mode = TaskCreateIn.mode.AutoMode
}

// 日志工具
const addTaskLog = (task: RunningTask, msg: string, type: 'info' | 'error' | 'warning' | 'success' = 'info') => {
  task.logs.push({ time: new Date().toLocaleTimeString(), message: msg, type })
  nextTick(() => {
    const el = outputRefs.value.get(task.websocketId)
    if (el) el.scrollTop = el.scrollHeight
  })
}

// 颜色映射
const getTaskStatusColor = (s: string) => ({ '连接中': 'processing', '运行中': 'blue', '已完成': 'green', '已失败': 'red', '已断开': 'default', '连接错误': 'red' } as Record<string, string>)[s] || 'default'
const getQueueItemStatusColor = (s: string) => /成功|完成|已完成/.test(s) ? 'green' : /失败|错误|异常/.test(s) ? 'red' : /等待|排队|挂起/.test(s) ? 'orange' : /进行|执行|运行/.test(s) ? 'blue' : 'default'
const filterTaskOption = (input: string, option: any) => (option?.label || '').toLowerCase().includes(input.toLowerCase())

// 完成检测
const checkAllTasksCompleted = () => {
  const all: RunningTask[] = []
  schedulerTabs.value.forEach(t => all.push(...t.runningTasks))
  if (!all.length) return
  if (!all.every(t => ['已完成', '已失败', '已断开'].includes(t.status))) return
  const action = currentTab.value.completionAction
  if (!action || action === 'none') return
  message.success(`所有任务结束，准备执行动作: ${action}`)
}

// 消息弹窗控制
const cancelMessage = () => {
  messageModalVisible.value = false
  messageResponse.value = ''
  currentMessage.value = null
}

// WebSocket 消息处理
const handleWebSocketMessage = (task: RunningTask, raw: WebSocketBaseMessage) => {
  const type = raw.type
  const payload: any = raw.data
  const idx = currentTab.value.runningTasks.findIndex(t => t.websocketId === task.websocketId)
  if (idx === -1) return
  switch (type) {
    case 'Update': {
      if (payload?.task_list) {
        currentTab.value.runningTasks[idx].userQueue = payload.task_list.map((i: any) => ({ name: i.name || '未知任务', status: i.status || '未知' }))
      }
      if (payload) Object.entries(payload).forEach(([k, v]) => { if (k !== 'task_list') addTaskLog(currentTab.value.runningTasks[idx], `${k}: ${v}`, 'info') })
      break
    }
    case 'Message': {
      currentMessage.value = { title: '任务消息', content: payload?.message || payload?.val || '任务需要您的输入', needInput: true, messageId: payload?.messageId || (raw as any).messageId, taskId: task.websocketId }
      messageModalVisible.value = true
      break
    }
    case 'Info': {
      const isErr = !!payload?.Error
      const content = payload?.Error || payload?.val || payload?.message || '未知通知'
      addTaskLog(task, content, isErr ? 'error' : 'info')
      if (isErr) notification.error({ message: '任务错误', description: content })
      else notification.info({ message: '任务信息', description: content })
      break
    }
    case 'Signal': {
      if (payload?.Accomplish !== undefined) {
        const done = !!payload.Accomplish
        currentTab.value.runningTasks[idx].status = done ? '已完成' : '已失败'
        addTaskLog(currentTab.value.runningTasks[idx], `任务${done ? '已完成' : '已失败'}`, done ? 'success' : 'error')
        checkAllTasksCompleted()
        wsDisconnect(task.websocketId)
      }
      break
    }
    default:
      addTaskLog(task, `收到未知消息类型: ${type}`, 'warning')
  }
}

// 回复消息
const sendMessageResponse = () => {
  if (!currentMessage.value?.taskId) return
  const task = schedulerTabs.value.flatMap(t => t.runningTasks).find(t => t.websocketId === currentMessage.value!.taskId)
  if (task) {
    sendRaw('MessageResponse', { messageId: currentMessage.value!.messageId, response: messageResponse.value }, task.websocketId)
    addTaskLog(task, `用户回复: ${messageResponse.value}`, 'info')
  }
  messageModalVisible.value = false
  messageResponse.value = ''
  currentMessage.value = null
}

// 停止任务
const stopTask = (id: string) => {
  const idx = currentTab.value.runningTasks.findIndex(t => t.websocketId === id)
  if (idx >= 0) {
    const task = currentTab.value.runningTasks[idx]
    wsDisconnect(task.websocketId)
    currentTab.value.runningTasks.splice(idx, 1)
    const p = currentTab.value.activeTaskPanels.indexOf(id)
    if (p >= 0) currentTab.value.activeTaskPanels.splice(p, 1)
    message.success('任务已停止')
  }
}

// 清空日志（按钮已注释，可保留）
const clearTaskOutput = (id: string) => {
  const t = currentTab.value.runningTasks.find(x => x.websocketId === id)
  if (t) t.logs = []
}

// 生命周期
onMounted(() => { wsConnect(); loadTaskOptions() })
onUnmounted(() => { schedulerTabs.value.forEach(tab => tab.runningTasks.forEach(t => wsDisconnect(t.websocketId))) })
</script>

<style scoped>
.scheduler-container {
  height: calc(100vh - 64px);
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
}

.completion-label {
  margin-right: 8px;
  font-weight: 500;
}

.right-actions {
  display: flex;
  align-items: center;
}

.execution-area {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.empty-state {
  text-align: center;
  color: #999;
  padding: 40px 0;
}

.task-panels {
  margin-top: 16px;
}

.realtime-logs-panel {
  display: flex;
  flex-direction: column;
}

.panel-header {
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
