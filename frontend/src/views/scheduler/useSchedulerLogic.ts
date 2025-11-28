import { computed, ref, watch } from 'vue'
import { useLocalStorage } from '@vueuse/core'
import { message, Modal, notification } from 'ant-design-vue'
import { Service } from '@/api/services/Service'
import { TaskCreateIn } from '@/api/models/TaskCreateIn'
import { PowerIn } from '@/api/models/PowerIn'
import { useWebSocket, ExternalWSHandlers } from '@/composables/useWebSocket'
import schedulerHandlers from './schedulerHandlers'
import type { ComboBoxItem } from '@/api/models/ComboBoxItem'
import type { QueueItem, Script } from './schedulerConstants'
import { type SchedulerTab, type TaskMessage, type SchedulerStatus } from './schedulerConstants'

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
        status: '空闲',
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

// 保存调度台状态到内存
const saveTabsToStorage = (tabs: SchedulerTab[]) => {
  // 保存到内存变量而不是localStorage
  schedulerTabsMemory = tabs
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

  // 电源操作状态
  const powerAction = ref<PowerIn.signal>(PowerIn.signal.NO_ACTION)
  // 注意：电源倒计时弹窗已移至全局组件 GlobalPowerCountdown.vue
  // 这里保留引用以避免破坏现有代码，但实际功能由全局组件处理
  const powerCountdownVisible = ref(false)
  const powerCountdownData = ref<{
    title?: string
    message?: string
    countdown?: number
  }>({})
  // 前端自己的60秒倒计时 - 已移至全局组件
  let powerCountdownTimer: ReturnType<typeof setInterval> | null = null

  // 消息弹窗
  const messageModalVisible = ref(false)
  const currentMessage = ref<TaskMessage | null>(null)
  const messageResponse = ref('')

  // WebSocket 实例
  const ws = useWebSocket()

  // TaskManager消息处理函数（供全局WebSocket调用）
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
    // 使用现有的addSchedulerTab函数创建新调度台，并传入特定的配置选项
    const newTab = addSchedulerTab({
      title: `调度台${tabCounter}`,
      status: '运行',
      websocketId: taskId,
    })

    // 立即订阅该任务的WebSocket消息
    subscribeToTask(newTab)

    console.log('[Scheduler] 已创建新的自动调度台:', newTab.title, '任务ID:', taskId)
    message.success(`已自动创建调度台: ${newTab.title}`)

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
  const addSchedulerTab = (options?: { title?: string; status?: string; websocketId?: string }) => {
    tabCounter++
    const status = options?.status || '空闲'
    // 使用更安全的类型断言，确保状态值是有效的SchedulerStatus
    const validStatus: SchedulerStatus = ['空闲', '运行', '等待', '结束', '异常'].includes(status)
      ? (status as SchedulerStatus)
      : '空闲'

    const tab: SchedulerTab = {
      key: `tab-${tabCounter}`,
      title: options?.title || `调度台${tabCounter}`,
      closable: true,
      status: validStatus,
      selectedTaskId: options?.websocketId || null,
      selectedMode: TaskCreateIn.mode.AutoMode,
      websocketId: options?.websocketId || null,
      taskQueue: [],
      userQueue: [],
      logs: [],
      isLogAtBottom: true,
      lastLogContent: '',
    }
    schedulerTabs.value.push(tab)
    activeSchedulerTab.value = tab.key

    return tab
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
      content: `确定要删除调度台 "${tab.title}" 吗？`,
      okText: '确认删除',
      cancelText: '取消',
      okType: 'danger',
      onOk() {
        const idx = schedulerTabs.value.findIndex(t => t.key === key)
        if (idx === -1) return

        // 清理 WebSocket 订阅
        if (tab.subscriptionId) {
          ws.unsubscribe(tab.subscriptionId)
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

  // 批量删除所有未运行状态的调度台子页（主调度台除外）
  const removeAllNonRunningTabs = () => {
    const nonRunningTabs = schedulerTabs.value.filter(
      tab => tab.key !== 'main' && tab.status !== '运行'
    )

    if (nonRunningTabs.length === 0) {
      message.info('没有可删除的调度台')
      return
    }

    Modal.confirm({
      title: '批量删除',
      content: `确定要删除 ${nonRunningTabs.length} 个空闲的调度台吗？`,
      okText: '确认删除',
      cancelText: '取消',
      okType: 'danger',
      onOk() {
        nonRunningTabs.forEach(tab => {
          // 清理 WebSocket 订阅
          if (tab.subscriptionId) {
            ws.unsubscribe(tab.subscriptionId)
          }

          // 清理日志引用
          logRefs.value.delete(tab.key)

          // 清理任务总览面板引用
          overviewRefs.value.delete(tab.key)
        })

        // 从数组中移除这些标签页
        schedulerTabs.value = schedulerTabs.value.filter(
          tab => tab.key === 'main' || tab.status === '运行'
        )

        // 如果当前活动的标签页被删除了，切换到主调度台
        if (!schedulerTabs.value.find(tab => tab.key === activeSchedulerTab.value)) {
          activeSchedulerTab.value = 'main'
        }

        message.success(`成功删除 ${nonRunningTabs.length} 个调度台`)
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

        // 确保清理任何可能存在的旧订阅
        if (tab.subscriptionId) {
          console.log('[Scheduler] 清理旧的WebSocket订阅:', tab.subscriptionId)
          ws.unsubscribe(tab.subscriptionId)
          tab.subscriptionId = null
        }

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

      // 等待后端通过 WebSocket 发送真实结束/更新信号进行同步
      message.info('正在停止任务，请稍候...')
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

    // 如果已经有活动的订阅，先清理旧订阅
    if (tab.subscriptionId) {
      console.log('[Scheduler] 检测到旧订阅，先清理:', {
        key: tab.key,
        oldSubscriptionId: tab.subscriptionId,
        newWebsocketId: tab.websocketId,
      })
      ws.unsubscribe(tab.subscriptionId)
      tab.subscriptionId = null
    }

    const subscriptionId = ws.subscribe({ id: tab.websocketId }, message =>
      handleWebSocketMessage(tab, message)
    )

    // 将订阅ID保存到tab中，以便后续取消订阅
    tab.subscriptionId = subscriptionId
    console.log('[Scheduler] 新建WebSocket订阅:', {
      key: tab.key,
      websocketId: tab.websocketId,
      subscriptionId,
    })

    // 验证订阅是否成功建立
    if (!subscriptionId) {
      console.error('[Scheduler] WebSocket订阅创建失败！', {
        key: tab.key,
        websocketId: tab.websocketId,
      })
      message.error('WebSocket订阅创建失败，可能无法接收任务消息')
    }
  }

  const handleWebSocketMessage = (tab: SchedulerTab, wsMessage: any) => {
    if (!wsMessage || typeof wsMessage !== 'object') return

    const { id, type, data } = wsMessage

    console.log('[Scheduler] 收到WebSocket消息:', { id, type, data, tabId: tab.websocketId })

    // 处理全局消息（如电源操作倒计时）
    if (id === 'Main' && type === 'Message' && data?.type === 'Countdown') {
      console.log('[Scheduler] 收到全局倒计时消息:', data)
      handleMessageDialog(tab, data)
      return
    }

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
        handleInfoMessage(data)
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
          if (data.task_info) {
            handleUpdateMessage(tab, data)
          }
          // 尝试处理可能的日志信息
          if (data.log) {
            handleUpdateMessage(tab, data)
          }
          // 尝试处理可能的错误/警告/信息
          if (data.Error || data.Warning || data.Info) {
            handleInfoMessage(data)
          }
        }
    }
  }

  const handleUpdateMessage = (tab: SchedulerTab, data: any) => {
    // 添加消息去重机制
    const messageKey = `${tab.key}_${JSON.stringify(data.task_info || {})}`
    const currentTime = Date.now()

    // 检查是否是重复消息
    if (!tab.lastMessageHash) tab.lastMessageHash = ''
    if (!tab.lastMessageTime) tab.lastMessageTime = 0

    if (tab.lastMessageHash === messageKey && currentTime - tab.lastMessageTime < 100) {
      console.log('重复的Update消息被过滤:', tab.key)
      return
    }

    tab.lastMessageHash = messageKey
    tab.lastMessageTime = currentTime

    // 直接将 WebSocket 消消息传递给 TaskOverviewPanel
    const overviewPanel = overviewRefs.value.get(tab.key)
    if (overviewPanel && overviewPanel.handleWSMessage) {
      const wsMessage = {
        type: 'Update',
        id: tab.websocketId,
        data: data,
      }
      console.log('传递 WebSocket 消息给 TaskOverviewPanel:', wsMessage)
      overviewPanel.handleWSMessage(wsMessage)
    }

    // 同步维护 任务总览 快照 overviewData（用于路由返回后的快速恢复）
    try {
      if (data.task_info && Array.isArray(data.task_info)) {
        // 完整脚本+用户数据，直接保存
        tab.overviewData = (data.task_info as any[]).map(s => ({
          script_id: s.script_id || `script_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
          name: s.name || '未知脚本',
          status: s.status || '等待',
          user_list: s.userList ? [...s.userList] : [],
        }))
      } else {
        // 如果没有task_info数据，保持现有数据不变
        console.log('[Scheduler] 没有task_info数据，保持现有overviewData')
      }
    } catch (e) {
      console.warn('[Scheduler] 维护 overviewData 快照时出现问题:', e)
    }

    // 处理 队列与日志 显示
    // 处理task_info初始化消息
    if (data.task_info && Array.isArray(data.task_info)) {
      // 初始化任务队列 - 保持原始状态
      const newTaskQueue = data.task_info.map((item: any) => ({
        name: item.name || '未知任务',
        status: item.status || '等待',
      }))

      // 初始化用户队列（仅包含运行状态下的用户）
      const newUserQueue: QueueItem[] = []
      data.task_info.forEach((taskItem: any) => {
        if (taskItem.userList && Array.isArray(taskItem.userList)) {
          taskItem.userList.forEach((user: any) => {
            if (user.status === '运行') {
              newUserQueue.push({
                name: `${taskItem.name}-${user.name}`,
                status: user.status,
              })
            }
          })
        }
      })

      tab.taskQueue.splice(0, tab.taskQueue.length, ...newTaskQueue)
      tab.userQueue.splice(0, tab.userQueue.length, ...newUserQueue)
    }

    // 处理日志 - 直接显示完整日志内容，覆盖上次显示的内容
    if (data.log) {
      if (typeof data.log === 'string') {
        const newContent = data.log
        if (tab.lastLogContent !== newContent) {
          tab.lastLogContent = newContent
          console.log('[Scheduler] 更新日志内容:', {
            tabKey: tab.key,
            contentLength: newContent.length
          })
        }
      } else if (typeof data.log === 'object') {
        let newContent = ''
        if (data.log.Error) newContent = data.log.Error
        else if (data.log.Warning) newContent = data.log.Warning
        else if (data.log.Info) newContent = data.log.Info
        else newContent = JSON.stringify(data.log)

        if (tab.lastLogContent !== newContent) {
          tab.lastLogContent = newContent
          console.log('[Scheduler] 更新日志对象:', {
            tabKey: tab.key,
            contentLength: newContent.length
          })
        }
      }
    }
    // 移除可能导致递归更新的 saveTabsToStorage 调用
    // saveTabsToStorage(schedulerTabs.value)
  }

  const handleInfoMessage = (data: any) => {
    if (data.Error) {
      notification.error({ message: '任务错误', description: data.Error })
    } else if (data.Warning) {
      notification.warning({ message: '任务警告', description: data.Warning })
    } else if (data.Info) {
      notification.info({ message: '任务信息', description: data.Info })
    }
  }

  const handleMessageDialog = (tab: SchedulerTab, data: any) => {
    // 处理倒计时消息 - 已移至全局组件处理
    if (data.type === 'Countdown') {
      console.log('[Scheduler] 收到倒计时消息，由全局组件处理:', data)
      // 不再在调度中心处理倒计时，由 GlobalPowerCountdown 组件处理
      return
    }

    // 处理普通消息对话框
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

      if (tab.subscriptionId) {
        console.log('[Scheduler] 任务完成，清理WebSocket订阅:', {
          key: tab.key,
          subscriptionId: tab.subscriptionId,
          websocketId: tab.websocketId,
        })
        try {
          ws.unsubscribe(tab.subscriptionId)
        } catch (error) {
          console.warn('[Scheduler] 清理订阅时发生错误:', error)
        }
        tab.subscriptionId = null
      }

      if (tab.websocketId) {
        console.log('[Scheduler] 任务完成，清理websocketId:', {
          key: tab.key,
          websocketId: tab.websocketId,
        })
        tab.websocketId = null
      }

      message.success('任务完成')
      saveTabsToStorage(schedulerTabs.value)

      // 触发Vue的响应式更新
      schedulerTabs.value = [...schedulerTabs.value]
    }

    // 移除自动处理电源信号的逻辑，电源操作完全由后端WebSocket的倒计时消息控制
    // if (data && data.power && data.power !== 'NoAction') {
    //   // 不再自己处理电源信号
    // }
  }

  const onLogScroll = (isAtBottom: boolean, tab: SchedulerTab) => {
    tab.isLogAtBottom = isAtBottom
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
      // 若当前 tab 有 overviewData 快照，立即回放到子组件，保证路由切回时立现
      const tab = schedulerTabs.value.find(t => t.key === key)
      if (tab?.overviewData && el.handleWSMessage) {
        const wsMessage = {
          type: 'Update',
          id: tab.websocketId,
          data: {
            task_info: tab.overviewData?.map(s => ({
              script_id: s.script_id,
              name: s.name,
              status: s.status,
              userList: s.user_list, // 转换回后端格式
            }))
          },
        }
        try {
          el.handleWSMessage(wsMessage)
        } catch (e) {
          console.warn('[Scheduler] 回放 overviewData 到面板时异常:', e)
        }
      }
    } else {
      overviewRefs.value.delete(key)
    }
  }

  // 电源操作
  const onPowerActionChange = async (value: PowerIn.signal) => {
    powerAction.value = value
    // useLocalStorage 会自动同步到 localStorage，无需手动保存

    // 调用API设置电源操作
    try {
      await Service.setPowerApiDispatchSetPowerPost({ signal: value })
      console.log('[Scheduler] 电源操作设置成功:', value)
    } catch (error) {
      console.error('设置电源操作失败:', error)
      message.error('设置电源操作失败')
    }
  }

  // 更新电源操作显示（不发送API请求）
  const updatePowerActionDisplay = (powerSign: string) => {
    // 将后端的PowerSign转换为前端的PowerIn.signal枚举值
    let newPowerAction: PowerIn.signal = PowerIn.signal.NO_ACTION

    switch (powerSign) {
      case 'NoAction':
        newPowerAction = PowerIn.signal.NO_ACTION
        break
      case 'KillSelf':
        newPowerAction = PowerIn.signal.KILL_SELF
        break
      case 'Sleep':
        newPowerAction = PowerIn.signal.SLEEP
        break
      case 'Hibernate':
        newPowerAction = PowerIn.signal.HIBERNATE
        break
      case 'Shutdown':
        newPowerAction = PowerIn.signal.SHUTDOWN
        break
      case 'ShutdownForce':
        newPowerAction = PowerIn.signal.SHUTDOWN_FORCE
        break
      default:
        console.warn('[Scheduler] 未知的PowerSign值:', powerSign)
        return
    }

    // 更新显示状态，useLocalStorage 会自动同步到 localStorage
    powerAction.value = newPowerAction
    console.log('[Scheduler] 电源操作显示已更新为:', newPowerAction)
  }

  // 启动60秒倒计时 - 已移至全局组件，这里保留空函数避免破坏现有代码
  // 移除自动执行电源操作，由后端完全控制
  // const executePowerAction = async () => {
  //   // 不再自己执行电源操作，完全由后端控制
  // }

  const cancelPowerAction = async () => {
    console.log('[Scheduler] cancelPowerAction 已移至全局组件，调度中心不再处理')
    // 电源操作取消功能已移至 GlobalPowerCountdown 组件
    // 这里保留空函数以避免破坏现有的调用代码
  }

  // 移除自动检查任务完成的逻辑，完全由后端控制
  // const checkAllTasksCompleted = () => {
  //   // 不再自己检查任务完成状态，完全由后端WebSocket消息控制
  // }

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

  // 获取电源状态
  const getPowerState = async () => {
    try {
      const response = await Service.getPowerApiDispatchGetPowerPost()
      if (response.code === 200 && response.signal) {
        // 将后端返回的 PowerOut.signal 转换为 PowerIn.signal
        const signalMap: Record<string, PowerIn.signal> = {
          'NoAction': PowerIn.signal.NO_ACTION,
          'KillSelf': PowerIn.signal.KILL_SELF,
          'Sleep': PowerIn.signal.SLEEP,
          'Hibernate': PowerIn.signal.HIBERNATE,
          'Shutdown': PowerIn.signal.SHUTDOWN,
          'ShutdownForce': PowerIn.signal.SHUTDOWN_FORCE,
        }
        const mappedSignal = signalMap[response.signal]
        if (mappedSignal) {
          powerAction.value = mappedSignal
          console.log('[Scheduler] 已从后端获取电源状态:', mappedSignal)
        } else {
          console.warn('[Scheduler] 未知的电源信号:', response.signal)
        }
      }
    } catch (error) {
      console.error('[Scheduler] 获取电源状态失败:', error)
      // 失败时不显示错误消息，使用默认值
    }
  }

  // 初始化函数
  const initialize = () => {
    // 设置全局WebSocket的消息处理函数
    // 通过 import 的 ExternalWSHandlers 直接注册处理函数，保证导入方能够永久引用并调用
    ExternalWSHandlers.taskManagerMessage = handleTaskManagerMessage
    ExternalWSHandlers.mainMessage = handleMainMessage
    console.log('[Scheduler] 已设置全局WebSocket消息处理函数')

    // 获取后端当前的电源状态
    getPowerState()

    // 注册 UI hooks 到 schedulerHandlers，使其能在 schedulerHandlers 检测到 pending 时回放到当前 UI
    try {
      schedulerHandlers.registerSchedulerUI({
        onNewTab: tab => {
          try {
            // 创建并订阅新调度台
            const newTab = addSchedulerTab({
              title: tab.title,
              status: '运行',
              websocketId: tab.websocketId,
            })
            subscribeToTask(newTab)
            saveTabsToStorage(schedulerTabs.value)
          } catch (e) {
            console.warn('[Scheduler] registerSchedulerUI onNewTab error:', e)
          }
        },
        onCountdown: data => {
          try {
            // 倒计时已移至全局组件处理，这里不再处理
            console.log('[Scheduler] 倒计时消息由全局组件处理:', data)
          } catch (e) {
            console.warn('[Scheduler] registerSchedulerUI onCountdown error:', e)
          }
        },
      })

      // 回放 pending tabs（如果有的话）
      const pending = schedulerHandlers.consumePendingTabIds()
      if (pending && pending.length > 0) {
        pending.forEach((taskId: string) => {
          try {
            const newTab = addSchedulerTab({
              title: `调度台${taskId}`,
              status: '运行',
              websocketId: taskId,
            })
            subscribeToTask(newTab)
          } catch (e) {
            console.warn('[Scheduler] replay pending tab error:', e)
          }
        })
        saveTabsToStorage(schedulerTabs.value)
      }

      // 回放 pending countdown（如果有的话）
      const pendingCountdown = schedulerHandlers.consumePendingCountdown()
      if (pendingCountdown) {
        try {
          // 倒计时已移至全局组件处理，这里不再处理
          console.log('[Scheduler] 待处理倒计时消息由全局组件处理:', pendingCountdown)
        } catch (e) {
          console.warn('[Scheduler] replay pending countdown error:', e)
        }
      }
    } catch (e) {
      console.warn('[Scheduler] schedulerHandlers registration failed:', e)
    }

    // 新增：为已有的"运行"标签恢复 WebSocket 订阅，防止路由切换返回后不再更新
    try {
      schedulerTabs.value.forEach(tab => {
        if (tab.status === '运行' && tab.websocketId) {
          console.log('[Scheduler] 初始化阶段为运行的标签恢复订阅:', {
            key: tab.key,
            websocketId: tab.websocketId,
          })
          subscribeToTask(tab)
        }
      })
    } catch (e) {
      console.warn('[Scheduler] 恢复订阅时出现问题:', e)
    }
  }

  // Main消息处理函数（供全局WebSocket调用）
  const handleMainMessage = (wsMessage: any) => {
    if (!wsMessage || typeof wsMessage !== 'object') return

    const { type, data } = wsMessage
    console.log('[Scheduler] 收到Main消息:', { type, data })

    // 首先调用 schedulerHandlers 的处理函数，确保 RequestClose 等信号被正确处理
    try {
      schedulerHandlers.handleMainMessage(wsMessage)
    } catch (e) {
      console.warn('[Scheduler] schedulerHandlers.handleMainMessage error:', e)
    }

    if (type === 'Message' && data && data.type === 'Countdown') {
      // 收到倒计时消息，由全局组件处理
      console.log('[Scheduler] 收到倒计时消息，由全局组件处理:', data)
      // 不再在调度中心处理倒计时
    } else if (type === 'Update' && data && data.PowerSign !== undefined) {
      // 收到电源操作更新消息，更新显示
      console.log('[Scheduler] 收到电源操作更新消息:', data.PowerSign)
      updatePowerActionDisplay(data.PowerSign)
    }
  }

  // 调试函数：检查所有调度台的订阅状态
  const debugSubscriptionStatus = () => {
    console.log('[Scheduler Debug] 当前调度台订阅状态:')
    schedulerTabs.value.forEach(tab => {
      console.log(`- Tab ${tab.key} (${tab.title}):`, {
        status: tab.status,
        websocketId: tab.websocketId,
        subscriptionId: tab.subscriptionId,
        hasSubscription: !!tab.subscriptionId,
      })
    })
    console.log('[Scheduler Debug] WebSocket状态:', ws.status.value)
  }

  // 清理函数
  const cleanup = () => {
    // 清理倒计时器 - 已移至全局组件，这里保留以避免错误
    if (powerCountdownTimer) {
      clearInterval(powerCountdownTimer)
      powerCountdownTimer = null
    }

    // 清理全局WebSocket的消息处理函数
    // 不再清理或重置导出的处理函数，保持使用者注册的处理逻辑永久有效

    // 在组件卸载时，只取消非运行状态任务的订阅
    // 运行任务的订阅将保持，以便在后台继续接收消息
    schedulerTabs.value.forEach(tab => {
      if (tab.subscriptionId && tab.status !== '运行') {
        ws.unsubscribe(tab.subscriptionId)
        tab.subscriptionId = null // 清理订阅ID
      }
    })
    saveTabsToStorage(schedulerTabs.value)
    // useLocalStorage 会自动同步 powerAction，无需手动保存
  }

  return {
    // 状态
    schedulerTabs,
    activeSchedulerTab,
    logRefs,
    // 将“运行/运行中”的用户标记为“等待”，并据此推导脚本状态

    taskOptionsLoading,
    taskOptions,
    powerAction,
    powerCountdownVisible,
    powerCountdownData,
    messageModalVisible,
    currentMessage,
    messageResponse,

    // 计算属性
    canChangePowerAction,
    currentTab,

    // Tab 管理
    addSchedulerTab,
    removeSchedulerTab,
    removeAllNonRunningTabs,

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
    getPowerState,
    cleanup,

    // 任务总览面板引用管理
    setOverviewRef,

    // 调试功能
    debugSubscriptionStatus,
  }
}
