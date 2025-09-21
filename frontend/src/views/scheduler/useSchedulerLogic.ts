import { computed, nextTick, ref, watch } from 'vue'
import { message, Modal, notification } from 'ant-design-vue'
import { Service } from '@/api/services/Service'
import { TaskCreateIn } from '@/api/models/TaskCreateIn'
import { PowerIn } from '@/api/models/PowerIn'
import { useWebSocket } from '@/composables/useWebSocket'
import type { ComboBoxItem } from '@/api/models/ComboBoxItem'
import type { QueueItem } from './schedulerConstants'
import {
  getPowerActionText,
  LOG_MAX_LENGTH,
  type LogEntry,
  type SchedulerTab,
  type TaskMessage,
} from './schedulerConstants'

// 电源操作状态仍然保存到localStorage中，以便重启后保持用户设置
const SCHEDULER_POWER_ACTION_KEY = 'scheduler-power-action'

// 使用内存变量存储调度台状态，而不是localStorage
let schedulerTabsMemory: SchedulerTab[] = []

// 从内存加载调度台状态
const loadTabsFromStorage = (): SchedulerTab[] => {
  // 如果内存中没有状态，则初始化默认状态
  if (schedulerTabsMemory.length === 0) {
    schedulerTabsMemory = [
      {
        key: 'main',
        title: '主调度台',
        closable: false,
        status: '新建',
        selectedTaskId: null,
        selectedMode: TaskCreateIn.mode.AutoMode,
        websocketId: null,
        taskQueue: [],
        userQueue: [],
        logs: [],
        isLogAtBottom: true,
        lastLogContent: '',
      },
    ]
  }
  return schedulerTabsMemory
}

// 从本地存储加载电源操作状态
const loadPowerActionFromStorage = (): PowerIn.signal => {
  try {
    const stored = localStorage.getItem(SCHEDULER_POWER_ACTION_KEY)
    if (stored) {
      return stored as PowerIn.signal
    }
  } catch (e) {
    console.error('Failed to load power action from storage:', e)
  }
  return PowerIn.signal.NO_ACTION
}

// 保存调度台状态到内存
const saveTabsToStorage = (tabs: SchedulerTab[]) => {
  // 保存到内存变量而不是localStorage
  schedulerTabsMemory = tabs
}

// 保存电源操作状态到本地存储
const savePowerActionToStorage = (powerAction: PowerIn.signal) => {
  try {
    localStorage.setItem(SCHEDULER_POWER_ACTION_KEY, powerAction)
  } catch (e) {
    console.error('Failed to save power action to storage:', e)
  }
}

export function useSchedulerLogic() {
  // 核心状态 - 从本地存储加载或使用默认值
  const schedulerTabs = ref<SchedulerTab[]>(loadTabsFromStorage())

  const activeSchedulerTab = ref(schedulerTabs.value[0]?.key || 'main')
  const logRefs = ref(new Map<string, HTMLElement>())
  const overviewRefs = ref(new Map<string, any>()) // 任务总览面板引用
  let tabCounter =
    schedulerTabs.value.length > 1
      ? Math.max(
        ...schedulerTabs.value
          .filter(tab => tab.key.startsWith('tab-'))
          .map(tab => parseInt(tab.key.replace('tab-', '')) || 0)
      ) + 1
      : 1

  // 任务选项
  const taskOptionsLoading = ref(false)
  const taskOptions = ref<ComboBoxItem[]>([])

  // 电源操作 - 从本地存储加载或使用默认值
  const powerAction = ref<PowerIn.signal>(loadPowerActionFromStorage())
  const powerCountdownVisible = ref(false)
  const powerCountdown = ref(10)
  let powerCountdownTimer: ReturnType<typeof setInterval> | null = null

  // 消息弹窗
  const messageModalVisible = ref(false)
  const currentMessage = ref<TaskMessage | null>(null)
  const messageResponse = ref('')

  // WebSocket 实例
  const ws = useWebSocket()

  // 订阅TaskManager消息，处理自动创建的任务
  const subscribeToTaskManager = () => {
    ws.subscribe('TaskManager', {
      onMessage: (message) => handleTaskManagerMessage(message)
    })
  }

  const handleTaskManagerMessage = (wsMessage: any) => {
    if (!wsMessage || typeof wsMessage !== 'object') return

    const { type, data } = wsMessage
    console.log('[Scheduler] 收到TaskManager消息:', { type, data })

    if (type === 'Signal' && data && data.newTask) {
      // 收到新任务信号，自动创建调度台
      const taskId = data.newTask
      console.log('[Scheduler] 收到新任务信号，任务ID:', taskId)

      // 创建新的调度台
      createSchedulerTabForTask(taskId)
    }
  }

  const createSchedulerTabForTask = (taskId: string) => {
    // 检查是否已经存在相同websocketId的调度台
    const existingTab = schedulerTabs.value.find(tab => tab.websocketId === taskId)
    if (existingTab) {
      console.log('[Scheduler] 调度台已存在，切换到该调度台:', existingTab.title)
      activeSchedulerTab.value = existingTab.key
      return
    }

    // 创建新的调度台
    tabCounter++
    const tab: SchedulerTab = {
      key: `tab-${tabCounter}`,
      title: `自动调度台${tabCounter}`,
      closable: true,
      status: '运行', // 直接设置为运行状态
      selectedTaskId: null,
      selectedMode: TaskCreateIn.mode.AutoMode,
      websocketId: taskId, // 设置websocketId
      taskQueue: [],
      userQueue: [],
      logs: [],
      isLogAtBottom: true,
      lastLogContent: '',
    }

    schedulerTabs.value.push(tab)
    activeSchedulerTab.value = tab.key

    // 立即订阅该任务的WebSocket消息
    subscribeToTask(tab)

    console.log('[Scheduler] 已创建新的自动调度台:', tab.title, '任务ID:', taskId)
    message.success(`已自动创建调度台: ${tab.title}`)

    saveTabsToStorage(schedulerTabs.value)
  }

  // 计算属性
  const canChangePowerAction = computed(() => {
    return !schedulerTabs.value.some(tab => tab.status === '运行')
  })

  const currentTab = computed(() => {
    return schedulerTabs.value.find(tab => tab.key === activeSchedulerTab.value)
  })

  // 监听调度台变化并保存到本地存储
  const watchTabsChanges = () => {
    // 使用Vue的watch API来监听数组变化，而不是重写原生方法
    watch(
      schedulerTabs,
      newTabs => {
        saveTabsToStorage(newTabs)
      },
      { deep: true }
    )
  }

  // 初始化监听
  watchTabsChanges()

  // Tab 管理
  const addSchedulerTab = () => {
    tabCounter++
    const tab: SchedulerTab = {
      key: `tab-${tabCounter}`,
      title: `调度台${tabCounter}`,
      closable: true,
      status: '新建',
      selectedTaskId: null,
      selectedMode: TaskCreateIn.mode.AutoMode,
      websocketId: null,
      taskQueue: [],
      userQueue: [],
      logs: [],
      isLogAtBottom: true,
      lastLogContent: '',
    }
    schedulerTabs.value.push(tab)
    activeSchedulerTab.value = tab.key
  }

  const removeSchedulerTab = (key: string) => {
    const tab = schedulerTabs.value.find(t => t.key === key)
    if (!tab) return

    if (tab.status === '运行') {
      Modal.warning({
        title: '无法删除调度台',
        content: `调度台 "${tab.title}" 正在运行中，无法删除。请先停止当前任务。`,
        okText: '知道了',
      })
      return
    }

    if (key === 'main') {
      message.warning('主调度台无法删除')
      return
    }

    Modal.confirm({
      title: '确认删除',
      content: `确定要删除调度台 "${tab.title}" 吗？删除后无法恢复。`,
      okText: '确认删除',
      cancelText: '取消',
      okType: 'danger',
      onOk() {
        const idx = schedulerTabs.value.findIndex(t => t.key === key)
        if (idx === -1) return

        // 清理 WebSocket 订阅
        if (tab.websocketId) {
          ws.unsubscribe(tab.websocketId)
        }

        // 清理日志引用
        logRefs.value.delete(key)

        // 清理任务总览面板引用
        overviewRefs.value.delete(key)

        schedulerTabs.value.splice(idx, 1)

        if (activeSchedulerTab.value === key) {
          const newActiveIndex = Math.max(0, idx - 1)
          activeSchedulerTab.value = schedulerTabs.value[newActiveIndex]?.key || 'main'
        }

        message.success(`调度台 "${tab.title}" 已删除`)
      },
    })
  }

  // 任务操作
  const startTask = async (tab: SchedulerTab) => {
    if (!tab.selectedTaskId || !tab.selectedMode) {
      message.error('请选择任务项和执行模式')
      return
    }

    try {
      const response = await Service.addTaskApiDispatchStartPost({
        taskId: tab.selectedTaskId,
        mode: tab.selectedMode,
      })

      if (response.code === 200) {
        tab.status = '运行'
        tab.websocketId = response.websocketId

        // 清空之前的状态
        tab.taskQueue.splice(0)
        tab.userQueue.splice(0)
        tab.logs.splice(0)
        tab.isLogAtBottom = true
        tab.lastLogContent = ''

        subscribeToTask(tab)
        message.success('任务启动成功')
        saveTabsToStorage(schedulerTabs.value)
      } else {
        message.error(response.message || '启动任务失败')
      }
    } catch (error) {
      console.error('启动任务失败:', error)
      message.error('启动任务失败')
    }
  }

  const stopTask = async (tab: SchedulerTab) => {
    if (!tab.websocketId) return

    try {
      await Service.stopTaskApiDispatchStopPost({ taskId: tab.websocketId })

      // 不再取消订阅，保持WebSocket连接以便接收结束信号
      // 只需发送停止请求，等待后端通过WebSocket发送结束信号
      // 移除了提示消息"已发送停止任务请求，等待任务完成确认"
      // 因为任务状态变更必须由明确外部信号驱动，不应该使用提示消息来表示等待状态
      saveTabsToStorage(schedulerTabs.value)
    } catch (error) {
      console.error('停止任务失败:', error)
      message.error('停止任务失败')
      saveTabsToStorage(schedulerTabs.value)
    }
  }

  // WebSocket 订阅与消息处理
  const subscribeToTask = (tab: SchedulerTab) => {
    if (!tab.websocketId) return

    ws.subscribe(tab.websocketId, {
      onMessage: (message) => handleWebSocketMessage(tab, message)
    })
  }

  const handleWebSocketMessage = (tab: SchedulerTab, wsMessage: any) => {
    if (!wsMessage || typeof wsMessage !== 'object') return

    const { id, type, data } = wsMessage

    console.log('[Scheduler] 收到WebSocket消息:', { id, type, data, tabId: tab.websocketId })

    // 只处理与当前标签页相关的消息
    if (id && id !== tab.websocketId) {
      console.log('[Scheduler] 消息ID不匹配，忽略消息:', { messageId: id, tabId: tab.websocketId })
      return
    }

    switch (type) {
      case 'Update':
        console.log('[Scheduler] 处理Update消息:', data)
        handleUpdateMessage(tab, data)
        break
      case 'Info':
        console.log('[Scheduler] 处理Info消息:', data)
        handleInfoMessage(tab, data)
        break
      case 'Message':
        console.log('[Scheduler] 处理Message消息:', data)
        handleMessageDialog(tab, data)
        break
      case 'Signal':
        console.log('[Scheduler] 处理Signal消息:', data)
        handleSignalMessage(tab, data)
        break
      default:
        console.warn('[Scheduler] 未知的WebSocket消息类型:', type, wsMessage)
        // 即使是未知类型的消息，也尝试处理其中可能包含的有效数据
        if (data) {
          // 尝试处理可能的任务队列更新
          if (data.task_dict || data.task_list || data.user_list) {
            handleUpdateMessage(tab, data)
          }
          // 尝试处理可能的日志信息
          if (data.log) {
            handleUpdateMessage(tab, data)
          }
          // 尝试处理可能的错误/警告/信息
          if (data.Error || data.Warning || data.Info) {
            handleInfoMessage(tab, data)
          }
        }
    }
  }

  const handleUpdateMessage = (tab: SchedulerTab, data: any) => {
    // 直接将 WebSocket 消息传递给 TaskOverviewPanel
    const overviewPanel = overviewRefs.value.get(tab.key)
    if (overviewPanel && overviewPanel.handleWSMessage) {
      const wsMessage = {
        type: 'Update',
        id: tab.websocketId,
        data: data
      }
      console.log('传递 WebSocket 消息给 TaskOverviewPanel:', wsMessage)
      overviewPanel.handleWSMessage(wsMessage)
    }

    // 处理task_dict初始化消息
    if (data.task_dict && Array.isArray(data.task_dict)) {
      // 初始化任务队列 - 保持原始状态
      const newTaskQueue = data.task_dict.map((item: any) => ({
        name: item.name || '未知任务',
        status: item.status || '等待',  // 使用实际状态，而不是强制设置为等待
      }));

      // 初始化用户队列（仅包含运行状态下的用户）
      const newUserQueue: QueueItem[] = [];
      data.task_dict.forEach((taskItem: any) => {
        if (taskItem.user_list && Array.isArray(taskItem.user_list)) {
          taskItem.user_list.forEach((user: any) => {
            // 只有在用户状态为运行时才添加到用户队列中
            if (user.status === '运行') {
              newUserQueue.push({
                name: `${taskItem.name}-${user.name}`,
                status: user.status,
              });
            }
          });
        }
      });

      tab.taskQueue.splice(0, tab.taskQueue.length, ...newTaskQueue);
      tab.userQueue.splice(0, tab.userQueue.length, ...newUserQueue);
    }

    // 更新任务队列
    if (data.task_list && Array.isArray(data.task_list)) {
      const newTaskQueue = data.task_list.map((item: any) => ({
        name: item.name || '未知任务',
        status: item.status || '未知',
      }));
      tab.taskQueue.splice(0, tab.taskQueue.length, ...newTaskQueue);
    }

    // 更新用户队列
    if (data.user_list && Array.isArray(data.user_list)) {
      const newUserQueue = data.user_list.map((item: any) => ({
        name: item.name || '未知用户',
        status: item.status || '未知',
      }));
      tab.userQueue.splice(0, tab.userQueue.length, ...newUserQueue);
    }

    // 处理日志 - 直接显示完整日志内容，覆盖上次显示的内容
    if (data.log) {
      if (typeof data.log === 'string') {
        // 直接替换日志内容，不添加时间戳，不保留历史记录
        tab.lastLogContent = data.log;
      } else if (typeof data.log === 'object') {
        if (data.log.Error) tab.lastLogContent = data.log.Error;
        else if (data.log.Warning) tab.lastLogContent = data.log.Warning;
        else if (data.log.Info) tab.lastLogContent = data.log.Info;
        else tab.lastLogContent = JSON.stringify(data.log);
      }
    }
    saveTabsToStorage(schedulerTabs.value)
  }

  const handleInfoMessage = (tab: SchedulerTab, data: any) => {
    if (data.Error) {
      notification.error({ message: '任务错误', description: data.Error })
    } else if (data.Warning) {
      notification.warning({ message: '任务警告', description: data.Warning })
    } else if (data.Info) {
      notification.info({ message: '任务信息', description: data.Info })
    }
  }

  const handleMessageDialog = (tab: SchedulerTab, data: any) => {
    if (data.title && data.content) {
      currentMessage.value = {
        title: data.title,
        content: data.content,
        needInput: data.needInput || false,
        messageId: data.messageId,
        taskId: tab.websocketId || undefined,
      }
      messageModalVisible.value = true
    }
  }

  const handleSignalMessage = (tab: SchedulerTab, data: any) => {
    console.log('[Scheduler] 处理Signal消息:', data)

    // 只有收到WebSocket的Accomplish信号才将任务标记为结束状态
    // 这确保了调度台状态与实际任务执行状态严格同步
    if (data && data.Accomplish) {
      console.log('[Scheduler] 收到Accomplish信号，设置任务状态为结束')
      // 使用Vue的响应式更新方式
      tab.status = '结束'
      console.log('[Scheduler] 已更新tab.status为结束，当前tab状态:', tab.status)

      // 强制触发Vue响应式更新
      const tabIndex = schedulerTabs.value.findIndex(t => t.key === tab.key)
      if (tabIndex !== -1) {
        const updatedTab: SchedulerTab = { ...tab }
        schedulerTabs.value.splice(tabIndex, 1, updatedTab)
        console.log('[Scheduler] 已强制更新schedulerTabs，当前tabs状态:', schedulerTabs.value)
      }

      if (tab.websocketId) {
        ws.unsubscribe(tab.websocketId)
        tab.websocketId = null
      }

      message.success('任务完成')
      checkAllTasksCompleted()
      saveTabsToStorage(schedulerTabs.value)

      // 触发Vue的响应式更新
      schedulerTabs.value = [...schedulerTabs.value]
    }

    if (data && data.power && data.power !== 'NoAction') {
      powerAction.value = data.power as PowerIn.signal
      savePowerActionToStorage(powerAction.value)
      startPowerCountdown()
    }
  }

  const onLogScroll = (tab: SchedulerTab) => {
    const el = logRefs.value.get(tab.key)
    if (!el) return

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

  const setOverviewRef = (el: any, key: string) => {
    if (el) {
      overviewRefs.value.set(key, el)
      console.log('设置 TaskOverviewPanel 引用:', key, el)
    } else {
      overviewRefs.value.delete(key)
    }
  }

  // 电源操作
  const onPowerActionChange = (value: PowerIn.signal) => {
    powerAction.value = value
    savePowerActionToStorage(value)
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
    // 注意：这里不重置 powerAction，保留用户选择
  }

  const checkAllTasksCompleted = () => {
    const hasRunningTasks = schedulerTabs.value.some(tab => tab.status === '运行')

    if (!hasRunningTasks && powerAction.value !== PowerIn.signal.NO_ACTION) {
      startPowerCountdown()
    }
  }

  // 消息弹窗操作
  const sendMessageResponse = () => {
    if (currentMessage.value?.taskId) {
      ws.sendRaw(
        'Response',
        {
          messageId: currentMessage.value.messageId,
          response: messageResponse.value,
        },
        currentMessage.value.taskId
      )
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

  // 任务选项加载
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

  // 初始化函数
  const initialize = () => {
    // 订阅TaskManager消息
    subscribeToTaskManager()
    console.log('[Scheduler] 已订阅TaskManager消息')
  }

  // 清理函数
  const cleanup = () => {
    if (powerCountdownTimer) {
      clearInterval(powerCountdownTimer)
    }

    // 取消订阅TaskManager
    ws.unsubscribe('TaskManager')

    schedulerTabs.value.forEach(tab => {
      if (tab.websocketId) {
        ws.unsubscribe(tab.websocketId)
      }
    })
    saveTabsToStorage(schedulerTabs.value)
    savePowerActionToStorage(powerAction.value)
  }

  return {
    // 状态
    schedulerTabs,
    activeSchedulerTab,
    logRefs,
    taskOptionsLoading,
    taskOptions,
    powerAction,
    powerCountdownVisible,
    powerCountdown,
    messageModalVisible,
    currentMessage,
    messageResponse,

    // 计算属性
    canChangePowerAction,
    currentTab,

    // Tab 管理
    addSchedulerTab,
    removeSchedulerTab,

    // 任务操作
    startTask,
    stopTask,

    // 日志操作
    onLogScroll,
    setLogRef,

    // 电源操作
    onPowerActionChange,
    cancelPowerAction,

    // 消息操作
    sendMessageResponse,
    cancelMessage,

    // 初始化与清理
    initialize,
    loadTaskOptions,
    cleanup,

    // 任务总览面板引用管理
    setOverviewRef,
  }
}