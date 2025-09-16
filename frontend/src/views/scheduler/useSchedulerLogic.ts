import { computed, nextTick, ref } from 'vue'
import { message, Modal, notification } from 'ant-design-vue'
import { Service } from '@/api/services/Service'
import { TaskCreateIn } from '@/api/models/TaskCreateIn'
import { PowerIn } from '@/api/models/PowerIn'
import { useWebSocket } from '@/composables/useWebSocket'
import type { ComboBoxItem } from '@/api/models/ComboBoxItem'
import {
  getPowerActionText,
  LOG_MAX_LENGTH,
  type LogEntry,
  type SchedulerTab,
  type TaskMessage,
} from './schedulerConstants'

export function useSchedulerLogic() {
  // 核心状态
  const schedulerTabs = ref<SchedulerTab[]>([
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
  ])

  const activeSchedulerTab = ref('main')
  const logRefs = ref(new Map<string, HTMLElement>())
  let tabCounter = 1

  // 任务选项
  const taskOptionsLoading = ref(false)
  const taskOptions = ref<ComboBoxItem[]>([])

  // 电源操作
  const powerAction = ref<PowerIn.signal>(PowerIn.signal.NO_ACTION)
  const powerCountdownVisible = ref(false)
  const powerCountdown = ref(10)
  let powerCountdownTimer: ReturnType<typeof setInterval> | null = null

  // 消息弹窗
  const messageModalVisible = ref(false)
  const currentMessage = ref<TaskMessage | null>(null)
  const messageResponse = ref('')

  // WebSocket 实例
  const ws = useWebSocket()

  // 计算属性
  const canChangePowerAction = computed(() => {
    return !schedulerTabs.value.some(tab => tab.status === '运行')
  })

  const currentTab = computed(() => {
    return schedulerTabs.value.find(tab => tab.key === activeSchedulerTab.value)
  })

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

      if (tab.websocketId) {
        ws.unsubscribe(tab.websocketId)
      }

      tab.status = '结束'
      tab.websocketId = null

      message.success('任务已停止')
      checkAllTasksCompleted()
    } catch (error) {
      console.error('停止任务失败:', error)
      message.error('停止任务失败')

      // 即使 API 调用失败也要清理本地状态
      if (tab.websocketId) {
        ws.unsubscribe(tab.websocketId)
        tab.status = '结束'
        tab.websocketId = null
      }
    }
  }

  // WebSocket 订阅与消息处理
  const subscribeToTask = (tab: SchedulerTab) => {
    if (!tab.websocketId) return

    ws.subscribe(tab.websocketId, {
      onProgress: data =>
        handleWebSocketMessage(tab, { ...data, type: 'Update', id: tab.websocketId }),
      onResult: data =>
        handleWebSocketMessage(tab, { ...data, type: 'Result', id: tab.websocketId }),
      onError: data => handleWebSocketMessage(tab, { ...data, type: 'Error', id: tab.websocketId }),
      onNotify: data => handleWebSocketMessage(tab, { ...data, type: 'Info', id: tab.websocketId }),
    })
  }

  const handleWebSocketMessage = (tab: SchedulerTab, wsMessage: any) => {
    if (!wsMessage || typeof wsMessage !== 'object') return

    const { id, type, data } = wsMessage

    // 只处理与当前标签页相关的消息，除非是全局信号
    if (id && id !== tab.websocketId && type !== 'Signal') return

    switch (type) {
      case 'Update':
        handleUpdateMessage(tab, data)
        break
      case 'Info':
        handleInfoMessage(tab, data)
        break
      case 'Message':
        handleMessageDialog(tab, data)
        break
      case 'Signal':
        handleSignalMessage(tab, data)
        break
      default:
        console.warn('未知的WebSocket消息类型:', type)
    }
  }

  const handleUpdateMessage = (tab: SchedulerTab, data: any) => {
    // 更新任务队列
    if (data.task_list && Array.isArray(data.task_list)) {
      const newTaskQueue = data.task_list.map((item: any) => ({
        name: item.name || '未知任务',
        status: item.status || '未知',
      }))
      tab.taskQueue.splice(0, tab.taskQueue.length, ...newTaskQueue)
    }

    // 更新用户队列
    if (data.user_list && Array.isArray(data.user_list)) {
      const newUserQueue = data.user_list.map((item: any) => ({
        name: item.name || '未知用户',
        status: item.status || '未知',
      }))
      tab.userQueue.splice(0, tab.userQueue.length, ...newUserQueue)
    }

    // 处理日志
    if (data.log) {
      if (typeof data.log === 'string') {
        addLog(tab, data.log, 'info')
      } else if (typeof data.log === 'object') {
        if (data.log.Error) addLog(tab, data.log.Error, 'error')
        else if (data.log.Warning) addLog(tab, data.log.Warning, 'warning')
        else if (data.log.Info) addLog(tab, data.log.Info, 'info')
        else addLog(tab, JSON.stringify(data.log), 'info')
      }
    }
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
    if (data.Accomplish) {
      tab.status = '结束'

      if (tab.websocketId) {
        ws.unsubscribe(tab.websocketId)
        tab.websocketId = null
      }

      notification.success({ message: '任务完成', description: data.Accomplish })
      checkAllTasksCompleted()
    }

    if (data.power && data.power !== 'NoAction') {
      powerAction.value = data.power as PowerIn.signal
      startPowerCountdown()
    }
  }

  // 日志管理
  const addLog = (tab: SchedulerTab, message: string, type: LogEntry['type'] = 'info') => {
    const logEntry: LogEntry = {
      time: new Date().toLocaleTimeString(),
      message,
      type,
      timestamp: Date.now(),
    }

    tab.logs.push(logEntry)

    // 限制日志条数
    if (tab.logs.length > LOG_MAX_LENGTH) {
      tab.logs.splice(0, tab.logs.length - LOG_MAX_LENGTH)
    }

    // 自动滚动到底部
    if (tab.isLogAtBottom) {
      nextTick(() => {
        const el = logRefs.value.get(tab.key)
        if (el) {
          el.scrollTop = el.scrollHeight
        }
      })
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

  // 电源操作
  const onPowerActionChange = (value: PowerIn.signal) => {
    powerAction.value = value
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

  // 清理函数
  const cleanup = () => {
    if (powerCountdownTimer) {
      clearInterval(powerCountdownTimer)
    }

    schedulerTabs.value.forEach(tab => {
      if (tab.websocketId) {
        ws.unsubscribe(tab.websocketId)
      }
    })
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
    addLog,
    onLogScroll,
    setLogRef,

    // 电源操作
    onPowerActionChange,
    cancelPowerAction,

    // 消息操作
    sendMessageResponse,
    cancelMessage,

    // 初始化与清理
    loadTaskOptions,
    cleanup,
  }
}
