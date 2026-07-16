import { computed, ref, watch } from 'vue'
import { message, Modal, notification } from 'ant-design-vue'
import { Service } from '@/api/services/Service'
import { TaskCreateIn } from '@/api/models/TaskCreateIn'
import { PowerIn } from '@/api/models/PowerIn'
import { useWebSocket } from '@/composables/useWebSocket'
import { useAudioPlayer } from '@/composables/useAudioPlayer'
import {
  WS_ID_MAIN,
  WS_ID_TASK_MANAGER,
  WS_POWER_SIGN_UPDATED,
  WS_TASK_COMPLETED,
  WS_TASK_CREATED,
  WS_TASK_INFO_UPDATED,
  WS_TASK_LOG_UPDATED,
  WS_TASK_NOTICE,
  type WSPowerSignData,
  type WSTaskCompletedData,
  type WSTaskCreatedData,
  type WSTaskNoticeData,
} from '@/services/websocket/types'
import type { ComboBoxItem } from '@/api/models/ComboBoxItem'
import type { QueueItem } from './schedulerConstants'
import { type SchedulerTab, type SchedulerStatus } from './schedulerConstants'
const logger = window.electronAPI.getLogger('调度台逻辑')

// 使用 sessionStorage 存储调度台状态，支持页面刷新时保留数据
// sessionStorage 在页面刷新时保留数据，但在关闭标签页/重启应用时清除
const SCHEDULER_TABS_KEY = 'scheduler-tabs-session'
const STORAGE_SAVE_DEBOUNCE_MS = 800
const LOG_RENDER_INTERVAL_MS = 200
const LOG_RENDER_MAX_CHARS = 120000

let storageSaveTimer: number | null = null
const pendingLogUpdates = new Map<string, number>()
const pendingLogContents = new Map<string, string>()

const getDefaultTabRuntimeState = () => ({
  taskQueue: [],
  userQueue: [],
  logs: [],
  isLogAtBottom: true,
  lastLogContent: '',
  overviewData: undefined,
  lastMessageHash: '',
  lastMessageTime: 0,
})

const trimLogForRender = (content: string) => {
  if (content.length <= LOG_RENDER_MAX_CHARS) return content

  const trimmed = content.slice(-LOG_RENDER_MAX_CHARS)
  const firstLineBreak = trimmed.indexOf('\n')
  const tail = firstLineBreak >= 0 ? trimmed.slice(firstLineBreak + 1) : trimmed
  return `前方日志较长，调度台仅显示最近内容；完整日志仍会写入历史记录。\n\n${tail}`
}

const clearPendingLogUpdate = (tabKey: string) => {
  const timer = pendingLogUpdates.get(tabKey)
  if (timer) {
    window.clearTimeout(timer)
    pendingLogUpdates.delete(tabKey)
  }
  pendingLogContents.delete(tabKey)
}

const toPersistedTab = (tab: SchedulerTab): SchedulerTab => ({
  key: tab.key,
  title: tab.title,
  closable: tab.closable,
  status: tab.status,
  selectedTaskId: tab.selectedTaskId,
  selectedMode: tab.selectedMode,
  resumeFromScriptId: tab.resumeFromScriptId ?? null,
  resumeScriptOptions: tab.resumeScriptOptions ? [...tab.resumeScriptOptions] : [],
  resumeScriptLoading: false,
  taskId: tab.taskId,
  subscriptionIds: [],
  runningTaskLabel: tab.runningTaskLabel,
  runningModeLabel: tab.runningModeLabel,
  logMode: tab.logMode || 'follow',
  ...getDefaultTabRuntimeState(),
})

const normalizePersistedTab = (tab: SchedulerTab): SchedulerTab => ({
  ...tab,
  ...getDefaultTabRuntimeState(),
  resumeScriptOptions: tab.resumeScriptOptions || [],
  resumeScriptLoading: false,
  subscriptionIds: [],
  logMode: tab.logMode || 'follow',
})

// 从 sessionStorage 加载调度台状态
const loadTabsFromStorage = (): SchedulerTab[] => {
  try {
    const saved = sessionStorage.getItem(SCHEDULER_TABS_KEY)
    if (saved) {
      const parsed = JSON.parse(saved)
      // 验证数据格式
      if (Array.isArray(parsed) && parsed.length > 0) {
        logger.info(`从 sessionStorage 恢复调度台状态: ${parsed.length} 个调度台`)
        return parsed.map(normalizePersistedTab)
      }
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.warn(`从 sessionStorage 加载调度台状态失败: ${errorMsg}`)
    // 清除损坏的数据
    sessionStorage.removeItem(SCHEDULER_TABS_KEY)
  }

  // 如果没有保存的状态或加载失败，返回默认状态
  logger.info('初始化默认调度台状态')
  return [
    {
      key: 'main',
      title: '主调度台',
      closable: false,
      status: '空闲',
      selectedTaskId: null,
      selectedMode: TaskCreateIn.mode.AUTO_PROXY,
      resumeFromScriptId: null,
      resumeScriptOptions: [],
      resumeScriptLoading: false,
      taskId: null,
      taskQueue: [],
      userQueue: [],
      logs: [],
      isLogAtBottom: true,
      lastLogContent: '',
      logMode: 'follow',
    },
  ]
}

// 保存调度台状态到 sessionStorage
const saveTabsToStorageNow = (tabs: SchedulerTab[]) => {
  try {
    sessionStorage.setItem(SCHEDULER_TABS_KEY, JSON.stringify(tabs.map(toPersistedTab)))
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存调度台状态到 sessionStorage 失败: ${errorMsg}`)
  }
}

const saveTabsToStorage = (tabs: SchedulerTab[]) => {
  if (storageSaveTimer) {
    window.clearTimeout(storageSaveTimer)
  }
  storageSaveTimer = window.setTimeout(() => {
    saveTabsToStorageNow(tabs)
    storageSaveTimer = null
  }, STORAGE_SAVE_DEBOUNCE_MS)
}

// ============================================
// 单例模式：模块级别共享状态
// 确保预挂载和组件挂载使用相同的状态实例
// ============================================

// 核心状态 - 模块级别单例
const schedulerTabs = ref<SchedulerTab[]>(loadTabsFromStorage())
const activeSchedulerTab = ref(schedulerTabs.value[0]?.key || 'main')
const logRefs = ref(new Map<string, HTMLElement>())
const overviewRefs = ref(new Map<string, any>()) // 任务总览面板引用

// 从现有调度台中计算最大编号
let tabCounter = 1
const initTabCounter = () => {
  if (schedulerTabs.value.length > 1) {
    const tabNumbers = schedulerTabs.value
      .filter(tab => tab.key.startsWith('tab-'))
      .map(tab => parseInt(tab.key.replace('tab-', '')) || 0)

    if (tabNumbers.length > 0) {
      tabCounter = Math.max(...tabNumbers) + 1
      logger.info(`从现有调度台恢复 tabCounter: ${tabCounter}`)
    }
  }
}
initTabCounter()

// 任务选项
const taskOptionsLoading = ref(false)
const taskOptions = ref<ComboBoxItem[]>([])
const scriptOptionsMap = ref<Record<string, string>>({})

// 电源操作状态（倒计时弹窗由全局组件 GlobalPowerCountdown.vue 处理）
const powerAction = ref<PowerIn.signal>(PowerIn.signal.NO_ACTION)

interface StartedTaskTracking {
  taskId: string
  selectedTaskId: string
  selectedMode: TaskCreateIn.mode
  taskLabel: string
  modeLabel: string
}

// 初始化标志 - 确保某些操作只执行一次
let _initialized = false
let _watchInitialized = false
// 常驻订阅注册标志 - 与 _initialized 分开，允许在进入应用前（甚至初始化向导阶段）
// 就注册 task.created，避免启动队列任务的创建通知因订阅晚于连接而丢失
let _residentSubscribed = false

export function useSchedulerLogic() {
  // WebSocket 实例
  const ws = useWebSocket()

  // 新任务创建通知处理（常驻订阅 id=TaskManager, type=task.created）
  const handleTaskCreated = (data: WSTaskCreatedData) => {
    logger.info(
      `收到新任务通知: 任务ID=${data.taskId}, 队列ID=${data.queueId}, 任务名称=${data.taskName}, 任务类型=${data.taskType}`
    )
    createSchedulerTabForTask(
      data.taskId,
      data.queueId ?? undefined,
      data.taskName ?? undefined,
      data.taskType ?? undefined
    )
  }

  const createSchedulerTabForTask = (
    taskId: string,
    queueId?: string,
    taskName?: string,
    taskType?: string
  ) => {
    // 使用现有的addSchedulerTab函数创建新调度台，并传入特定的配置选项
    const newTab = addSchedulerTab({
      title: `调度台${tabCounter}`,
      status: '运行',
      taskId,
      selectedTaskId: queueId, // 传入队列ID作为选中的任务ID
    })

    // 设置运行时文本快照，确保自动启动的任务也能正确显示
    if (taskName) newTab.runningTaskLabel = taskName
    if (taskType) newTab.runningModeLabel = taskType
    newTab.logMode = 'follow' // 任务开始时设置日志为保持最新模式

    // 立即订阅该任务的WebSocket消息
    subscribeToTask(newTab)

    logger.info(`已创建新的自动调度台: ${newTab.title}, 任务ID=${taskId}`)
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

  // 监听调度台变化并保存到本地存储（只初始化一次）
  const watchTabsChanges = () => {
    if (_watchInitialized) return
    _watchInitialized = true
    // 使用Vue的watch API来监听数组变化，而不是重写原生方法
    watch(
      () => schedulerTabs.value.map(toPersistedTab),
      () => {
        saveTabsToStorage(schedulerTabs.value)
      }
    )
  }

  // 初始化监听
  watchTabsChanges()

  // Tab 管理
  const addSchedulerTab = (options?: {
    title?: string
    status?: string
    taskId?: string
    selectedTaskId?: string
  }) => {
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
      selectedTaskId: options?.selectedTaskId || options?.taskId || null,
      selectedMode: TaskCreateIn.mode.AUTO_PROXY,
      resumeFromScriptId: null,
      resumeScriptOptions: [],
      resumeScriptLoading: false,
      taskId: options?.taskId || null,
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

  const trackStartedTask = ({
    taskId,
    selectedTaskId,
    selectedMode,
    taskLabel,
    modeLabel,
  }: StartedTaskTracking) => {
    const existingTab = schedulerTabs.value.find(tab => tab.websocketId === taskId)
    if (existingTab) {
      activeSchedulerTab.value = existingTab.key
      subscribeToTask(existingTab)
      return existingTab
    }

    const tab = addSchedulerTab({
      title: taskLabel,
      status: '运行',
      websocketId: taskId,
      selectedTaskId,
    })
    tab.selectedMode = selectedMode
    tab.runningTaskLabel = taskLabel
    tab.runningModeLabel = modeLabel
    tab.logMode = 'follow'
    subscribeToTask(tab)
    saveTabsToStorage(schedulerTabs.value)
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
        unsubscribeTab(tab)

        // 清理日志引用
        logRefs.value.delete(key)
        clearPendingLogUpdate(key)

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
          unsubscribeTab(tab)

          // 清理日志引用
          logRefs.value.delete(tab.key)
          clearPendingLogUpdate(tab.key)

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
  // 注：当前通过任务选项 label 的 "队列 - " 前缀判断是否为队列任务。
  //     这是对后端 ComboBox label 格式的隐式依赖；若 label 格式变更需同步调整。
  const isQueueTask = (tab: SchedulerTab) => {
    const taskOption = taskOptions.value.find(item => item.value === tab.selectedTaskId)
    return Boolean(taskOption?.label.startsWith('队列 - '))
  }

  const loadScriptLabelMap = async () => {
    try {
      const response = await Service.getScriptComboxApiInfoComboxScriptPost()
      if (response.code === 200 && Array.isArray(response.data)) {
        const mapped: Record<string, string> = {}
        response.data.forEach(item => {
          if (item.value && item.label) {
            mapped[item.value] = item.label
          }
        })
        scriptOptionsMap.value = mapped
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.warn(`加载脚本下拉信息失败，将回退为脚本ID显示: ${errorMsg}`)
    }
  }

  const loadResumeScriptOptions = async (tab: SchedulerTab) => {
    if (!tab.selectedTaskId || !isQueueTask(tab)) {
      tab.resumeScriptOptions = []
      tab.resumeFromScriptId = null
      return
    }

    tab.resumeScriptLoading = true
    try {
      await loadScriptLabelMap()
      const response = await Service.getItemApiQueueItemGetPost({ queueId: tab.selectedTaskId })
      if (response.code !== 200) {
        tab.resumeScriptOptions = []
        tab.resumeFromScriptId = null
        return
      }

      const options: Array<{ label: string; value: string }> = []
      const scriptSeen = new Set<string>()
      response.index.forEach(item => {
        const scriptId = response.data?.[item.uid]?.Info?.ScriptId
        if (!scriptId || scriptSeen.has(scriptId)) return
        scriptSeen.add(scriptId)
        options.push({
          value: scriptId,
          label: scriptOptionsMap.value[scriptId] || scriptId,
        })
      })

      tab.resumeScriptOptions = options
      if (tab.resumeFromScriptId && !options.some(item => item.value === tab.resumeFromScriptId)) {
        tab.resumeFromScriptId = null
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`加载恢复脚本列表失败: ${errorMsg}`)
      tab.resumeScriptOptions = []
      tab.resumeFromScriptId = null
      message.error('加载队列脚本失败，无法按脚本ID恢复')
    } finally {
      tab.resumeScriptLoading = false
    }
  }

  const handleTaskSelectionChange = async (tab: SchedulerTab, taskId: string | null) => {
    tab.selectedTaskId = taskId
    tab.resumeFromScriptId = null
    await loadResumeScriptOptions(tab)
  }

  const startTask = async (tab: SchedulerTab) => {
    if (!tab.selectedTaskId || !tab.selectedMode) {
      message.error('请选择任务项和执行模式')
      return
    }

    try {
      const requestBody: TaskCreateIn & { resumeFromScriptId?: string } = {
        taskId: tab.selectedTaskId,
        mode: tab.selectedMode,
      }
      if (tab.resumeFromScriptId) {
        requestBody.resumeFromScriptId = tab.resumeFromScriptId
      }

      const response = await Service.addTaskApiDispatchStartPost(requestBody)

      if (response.code === 200) {
        tab.status = '运行'
        tab.taskId = response.taskId

        // 确保清理任何可能存在的旧订阅
        unsubscribeTab(tab)

        // 清空之前的状态
        tab.taskQueue.splice(0)
        tab.userQueue.splice(0)
        tab.logs.splice(0)
        tab.isLogAtBottom = true
        tab.lastLogContent = ''
        tab.logMode = 'follow' // 任务开始时设置日志为保持最新模式

        subscribeToTask(tab)

        // 播放任务启动成功音频
        const { playSound } = useAudioPlayer()
        await playSound('task_started')

        message.success('任务启动成功')
        saveTabsToStorage(schedulerTabs.value)
      } else {
        message.error(response.message || '启动任务失败')
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`启动任务失败: ${errorMsg}`)
      message.error('启动任务失败')
    }
  }

  const stopTask = async (tab: SchedulerTab) => {
    if (!tab.taskId) return

    try {
      await Service.stopTaskApiDispatchStopPost({ taskId: tab.taskId })

      // 播放任务中止音频
      const { playSound } = useAudioPlayer()
      await playSound('maa_task_aborted')

      // 等待后端通过 WebSocket 发送真实结束/更新信号进行同步
      message.info('正在停止任务，请稍候...')
      saveTabsToStorage(schedulerTabs.value)
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`停止任务失败: ${errorMsg}`)
      message.error('停止任务失败')
      saveTabsToStorage(schedulerTabs.value)
    }
  }

  // WebSocket 订阅与消息处理：按 id + type 精确订阅任务消息
  const unsubscribeTab = (tab: SchedulerTab) => {
    if (!tab.subscriptionIds || tab.subscriptionIds.length === 0) return
    for (const subscriptionId of tab.subscriptionIds) {
      ws.unsubscribe(subscriptionId)
    }
    tab.subscriptionIds = []
  }

  const subscribeToTask = (tab: SchedulerTab) => {
    if (!tab.taskId) return

    // 订阅已存在时跳过（keep-alive 下路由切换不重复订阅）
    if (tab.subscriptionIds && tab.subscriptionIds.length > 0) {
      logger.info(`订阅已存在，跳过重复订阅: key=${tab.key}, taskId=${tab.taskId}`)
      return
    }

    const taskId = tab.taskId
    tab.subscriptionIds = [
      ws.subscribe({ id: taskId, type: WS_TASK_INFO_UPDATED }, wsMessage =>
        handleTaskInfoUpdated(tab, wsMessage.data as { task_info?: any[] })
      ),
      ws.subscribe({ id: taskId, type: WS_TASK_LOG_UPDATED }, wsMessage =>
        handleTaskLogUpdated(tab, wsMessage.data as { log?: string })
      ),
      ws.subscribe({ id: taskId, type: WS_TASK_NOTICE }, wsMessage => {
        void handleTaskNotice(wsMessage.data as unknown as WSTaskNoticeData)
      }),
      ws.subscribe({ id: taskId, type: WS_TASK_COMPLETED }, wsMessage => {
        void handleTaskCompleted(tab, wsMessage.data as unknown as WSTaskCompletedData)
      }),
    ]
    logger.info(`新建WebSocket订阅: key=${tab.key}, taskId=${taskId}`)
  }

  const buildTaskInfoSignature = (taskInfo: any[] | undefined) => {
    if (!Array.isArray(taskInfo)) return ''

    return taskInfo
      .map((task, index) => {
        const users = Array.isArray(task.userList)
          ? task.userList.map((user: any) => `${user.name || ''}:${user.status || ''}`).join(',')
          : ''
        return `${task.script_id || index}:${task.name || ''}:${task.status || ''}[${users}]`
      })
      .join('|')
  }

  const applyLogContentUpdate = (tab: SchedulerTab, content: string) => {
    const nextContent = trimLogForRender(content)
    if (tab.lastLogContent !== nextContent) {
      tab.lastLogContent = nextContent
    }
  }

  const scheduleLogContentUpdate = (tab: SchedulerTab, content: string, immediate = false) => {
    pendingLogContents.set(tab.key, content)

    if (immediate) {
      clearPendingLogUpdate(tab.key)
      applyLogContentUpdate(tab, content)
      return
    }

    if (pendingLogUpdates.has(tab.key)) return

    const timer = window.setTimeout(() => {
      const latestContent = pendingLogContents.get(tab.key)
      if (latestContent !== undefined) {
        applyLogContentUpdate(tab, latestContent)
      }
      pendingLogUpdates.delete(tab.key)
      pendingLogContents.delete(tab.key)
    }, LOG_RENDER_INTERVAL_MS)
    pendingLogUpdates.set(tab.key, timer)
  }

  const applyTaskInfoSnapshot = (tab: SchedulerTab, data: { task_info?: any[] }): boolean => {
    if (!data.task_info || !Array.isArray(data.task_info)) {
      logger.debug('没有task_info数据，保持现有overviewData')
      return false
    }

    const overviewPanel = overviewRefs.value.get(tab.key)
    if (overviewPanel && overviewPanel.applyTaskInfo) {
      overviewPanel.applyTaskInfo(data.task_info)
    }

    try {
      tab.overviewData = (data.task_info as any[]).map((s, index) => ({
        script_id: s.script_id || `script_${index}`,
        name: s.name || '未知脚本',
        status: s.status || '等待',
        user_list: s.userList ? [...s.userList] : [],
      }))
    } catch (e) {
      const errorMsg = e instanceof Error ? e.message : String(e)
      logger.warn(`维护 overviewData 快照时出现问题: ${errorMsg}`)
    }

    const newTaskQueue = data.task_info.map((item: any) => ({
      name: item.name || '未知任务',
      status: item.status || '等待',
    }))

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
    return true
  }

  const handleTaskInfoUpdated = (tab: SchedulerTab, data: { task_info?: any[] }) => {
    // 添加消息去重机制
    const taskInfoSignature = buildTaskInfoSignature(data.task_info)
    const messageKey = `${tab.key}_${taskInfoSignature}`
    const currentTime = Date.now()

    // 检查是否是重复消息
    if (!tab.lastMessageHash) tab.lastMessageHash = ''
    if (!tab.lastMessageTime) tab.lastMessageTime = 0

    if (
      taskInfoSignature &&
      tab.lastMessageHash === messageKey &&
      currentTime - tab.lastMessageTime < 100
    ) {
      logger.debug(`重复的任务信息消息被过滤: ${tab.key}`)
      return
    }

    if (taskInfoSignature) {
      tab.lastMessageHash = messageKey
      tab.lastMessageTime = currentTime
    }

    applyTaskInfoSnapshot(tab, data)
    // 移除可能导致递归更新的 saveTabsToStorage 调用
    // saveTabsToStorage(schedulerTabs.value)
  }

  const handleTaskLogUpdated = (tab: SchedulerTab, data: { log?: string }) => {
    // 直接显示完整日志内容，覆盖上次显示的内容
    if (typeof data.log !== 'string' || !data.log) return
    const newContent = data.log
    if (tab.lastLogContent !== newContent) {
      scheduleLogContentUpdate(tab, newContent)
      logger.debug(
        `更新日志内容: ${JSON.stringify({
          tabKey: tab.key,
          contentLength: newContent.length,
        })}`
      )
    }
  }

  const handleTaskNotice = async (data: WSTaskNoticeData) => {
    const { playSound } = useAudioPlayer()

    if (data.level === 'error') {
      const errorMsg = String(data.message).toLowerCase()

      // 根据错误内容匹配具体的 noisy 模式音频
      if (
        errorMsg.includes('adb') &&
        (errorMsg.includes('连接') || errorMsg.includes('connection'))
      ) {
        await playSound('maa_adb_connection_error')
      } else if (
        errorMsg.includes('模拟器') &&
        (errorMsg.includes('未检测') ||
          errorMsg.includes('not detected') ||
          errorMsg.includes('找不到'))
      ) {
        await playSound('maa_no_emulator_detected')
      } else if (errorMsg.includes('登录') && errorMsg.includes('失败')) {
        await playSound('maa_prts_login_failed')
      } else if (errorMsg.includes('超时') || errorMsg.includes('timeout')) {
        await playSound('maa_process_timeout')
      } else if (errorMsg.includes('部分') && errorMsg.includes('失败')) {
        await playSound('maa_partial_task_failed')
      } else if (errorMsg.includes('异常') && errorMsg.includes('退出')) {
        await playSound('maa_task_exited')
      } else if (errorMsg.includes('子任务') && errorMsg.includes('失败')) {
        await playSound('subtask_failed')
      } else {
        // 默认错误音频
        await playSound('error_occurred')
      }

      notification.error({ message: '任务错误', description: data.message })
    } else if (data.level === 'warning') {
      // 播放异常音频
      await playSound('exception_occurred')
      notification.warning({ message: '任务警告', description: data.message })
    } else {
      const infoMsg = String(data.message).toLowerCase()

      // 匹配成功信息的 noisy 模式音频
      if (infoMsg.includes('skland') || infoMsg.includes('森空岛')) {
        if (
          infoMsg.includes('签到成功') ||
          infoMsg.includes('checkin success') ||
          infoMsg.includes('成功')
        ) {
          await playSound('skland_checkin_success')
        } else if (
          infoMsg.includes('签到失败') ||
          infoMsg.includes('checkin failed') ||
          infoMsg.includes('失败')
        ) {
          await playSound('skland_checkin_failed')
        }
      } else if (
        infoMsg.includes('六星') ||
        infoMsg.includes('6星') ||
        infoMsg.includes('six star')
      ) {
        await playSound('six_star_report')
      } else if (infoMsg.includes('adb') && infoMsg.includes('成功')) {
        await playSound('adb_success')
      } else if (infoMsg.includes('adb') && infoMsg.includes('失败')) {
        await playSound('adb_failed')
      }

      notification.info({ message: '任务信息', description: data.message })
    }
  }

  const handleTaskCompleted = async (tab: SchedulerTab, data: WSTaskCompletedData) => {
    // 收到任务完成消息才将任务标记为结束状态
    // 这确保了调度台状态与实际任务执行状态严格同步
    logger.info('收到任务完成消息，设置任务状态为结束')

    applyTaskInfoSnapshot(tab, data)

    // 清空日志并显示原始代理结果信息
    const resultText = data.result
    if (resultText && typeof resultText === 'string') {
      scheduleLogContentUpdate(tab, resultText, true)
      logger.info('已清空日志并显示任务结果')
    }

    // 切换日志模式为自由浏览
    tab.logMode = 'browse'
    logger.info('已切换日志模式为自由浏览')

    // 使用Vue的响应式更新方式
    tab.status = '结束'
    logger.info(`已更新tab.status为结束，当前tab状态: ${JSON.stringify(tab.status)}`)

    // 强制触发Vue响应式更新
    const tabIndex = schedulerTabs.value.findIndex(t => t.key === tab.key)
    if (tabIndex !== -1) {
      const updatedTab: SchedulerTab = { ...tab }
      schedulerTabs.value.splice(tabIndex, 1, updatedTab)
    }

    logger.info(`任务完成，清理订阅与任务ID: key=${tab.key}, taskId=${tab.taskId}`)
    try {
      unsubscribeTab(tab)
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.warn(`清理订阅时发生错误: ${errorMsg}`)
    }
    tab.taskId = null

    // 播放任务完成音频
    const { playSound } = useAudioPlayer()
    await playSound('task_completed')

    message.success('任务完成')
    saveTabsToStorage(schedulerTabs.value)

    // 触发Vue的响应式更新
    schedulerTabs.value = [...schedulerTabs.value]
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
      logger.debug(`设置 TaskOverviewPanel 引用: ${key}, ${JSON.stringify(el)}`)
      // 若当前 tab 有 overviewData 快照，立即回放到子组件，保证路由切回时立现
      const tab = schedulerTabs.value.find(t => t.key === key)
      if (tab?.overviewData && el.applyTaskInfo) {
        const taskInfo = tab.overviewData?.map(s => ({
          script_id: s.script_id,
          name: s.name,
          status: s.status,
          userList: s.user_list, // 转换回后端格式
        }))
        try {
          el.applyTaskInfo(taskInfo)
        } catch (e) {
          const errorMsg = e instanceof Error ? e.message : String(e)
          logger.warn(`回放 overviewData 到面板时异常: ${errorMsg}`)
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
      logger.info(`电源操作设置成功: ${JSON.stringify(value)}`)
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`设置电源操作失败: ${errorMsg}`)
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
      case 'Shutdown':
        newPowerAction = PowerIn.signal.SHUTDOWN
        break
      case 'ShutdownForce':
        newPowerAction = PowerIn.signal.SHUTDOWN_FORCE
        break
      case 'Reboot':
        newPowerAction = PowerIn.signal.REBOOT
        break
      case 'Hibernate':
        newPowerAction = PowerIn.signal.HIBERNATE
        break
      case 'Sleep':
        newPowerAction = PowerIn.signal.SLEEP
        break
      case 'KillSelf':
        newPowerAction = PowerIn.signal.KILL_SELF
        break
      case 'Logoff':
        newPowerAction = PowerIn.signal.LOGOFF
        break
      default:
        logger.warn(`未知的PowerSign值: ${powerSign}`)
        return
    }

    // 更新显示状态，useLocalStorage 会自动同步到 localStorage
    powerAction.value = newPowerAction
    logger.info(`电源操作显示已更新为: ${JSON.stringify(newPowerAction)}`)
  }

  // 启动60秒倒计时 - 已移至全局组件，这里保留空函数避免破坏现有代码
  // 移除自动执行电源操作，由后端完全控制
  // const executePowerAction = async () => {
  //   // 不再自己执行电源操作，完全由后端控制
  // }

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
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`获取任务列表失败: ${errorMsg}`)
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
          NoAction: PowerIn.signal.NO_ACTION,
          Shutdown: PowerIn.signal.SHUTDOWN,
          ShutdownForce: PowerIn.signal.SHUTDOWN_FORCE,
          Reboot: PowerIn.signal.REBOOT,
          Hibernate: PowerIn.signal.HIBERNATE,
          Sleep: PowerIn.signal.SLEEP,
          KillSelf: PowerIn.signal.KILL_SELF,
          Logoff: PowerIn.signal.LOGOFF,
        }
        const mappedSignal = signalMap[response.signal]
        if (mappedSignal) {
          powerAction.value = mappedSignal
          logger.info(`已从后端获取电源状态: ${JSON.stringify(mappedSignal)}`)
        } else {
          logger.warn(`未知的电源信号: ${response.signal}`)
        }
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`获取电源状态失败: ${errorMsg}`)
      // 失败时不显示错误消息，使用默认值
    }
  }

  // 电源状态变更事件处理函数
  const handlePowerStateChanged = () => {
    logger.info('收到电源状态变更事件，重新获取电源状态')
    getPowerState()
  }

  // 注册调度中心常驻订阅（幂等）。必须在任何主连接建立前调用，
  // 因协议无缓存无重放：启动队列在连接就绪约 10 秒后创建任务并发 task.created，
  // 若订阅晚于连接建立（如初始化向导停留期间），该通知将永久丢失。
  const registerResidentSubscriptions = () => {
    if (_residentSubscribed) return
    _residentSubscribed = true

    // keep-alive 下路由切换不取消，应用关闭时随进程释放
    ws.subscribe({ id: WS_ID_TASK_MANAGER, type: WS_TASK_CREATED }, wsMessage =>
      handleTaskCreated(wsMessage.data as unknown as WSTaskCreatedData)
    )
    ws.subscribe({ id: WS_ID_MAIN, type: WS_POWER_SIGN_UPDATED }, wsMessage =>
      updatePowerActionDisplay((wsMessage.data as unknown as WSPowerSignData).signal)
    )
    logger.info('已注册调度中心常驻订阅 (task.created / power.sign.updated)')
  }

  // 初始化函数 - 使用单例标志确保核心初始化只执行一次
  const initialize = () => {
    // 常驻订阅可能已在进入应用前注册，这里幂等兜底
    registerResidentSubscriptions()

    // 核心初始化只执行一次
    if (!_initialized) {
      _initialized = true
      logger.info('调度中心首次初始化开始')

      // 监听电源状态变更事件（从 GlobalPowerCountdown 组件触发）
      window.addEventListener('power-state-changed', handlePowerStateChanged)
      logger.info('已注册电源状态变更事件监听器')

      logger.info('调度中心首次初始化完成')
    } else {
      logger.info('调度中心重复初始化跳过（单例模式）')
    }

    // 以下操作每次 initialize 调用都可以执行

    // 获取后端当前的电源状态
    getPowerState()

    // 为已有调度台预加载恢复脚本选项，确保刷新后恢复交互可用
    schedulerTabs.value.forEach(tab => {
      if (tab.status !== '运行' && isQueueTask(tab)) {
        loadResumeScriptOptions(tab)
      }
    })

    // 为已有的"运行"标签恢复 WebSocket 订阅，防止路由切换返回后不再更新
    // 注意：subscribeToTask 内部会检查订阅是否已存在，避免重复订阅
    try {
      schedulerTabs.value.forEach(tab => {
        if (tab.status === '运行' && tab.taskId) {
          logger.info(
            `初始化阶段检查运行中标签的订阅: ${JSON.stringify({
              key: tab.key,
              taskId: tab.taskId,
              hasSubscription: (tab.subscriptionIds?.length ?? 0) > 0,
            })}`
          )
          subscribeToTask(tab)
        }
      })
    } catch (e) {
      const errorMsg = e instanceof Error ? e.message : String(e)
      logger.warn(`恢复订阅时出现问题: ${errorMsg}`)
    }
  }

  // 调试函数：检查所有调度台的订阅状态
  const debugSubscriptionStatus = () => {
    logger.info('当前调度台订阅状态:')
    schedulerTabs.value.forEach(tab => {
      logger.info(
        `- Tab ${tab.key} (${tab.title}): ${JSON.stringify({
          status: tab.status,
          taskId: tab.taskId,
          subscriptionIds: tab.subscriptionIds,
        })}`
      )
    })
    logger.info(`WebSocket状态: ${JSON.stringify(ws.state.value)}`)
  }

  // 清理函数 - 由于keep-alive，这个函数只在组件真正销毁时调用
  // 路由切换时不会调用，所以所有订阅都保持活跃
  const cleanup = () => {
    logger.info('调度中心组件卸载，清理资源')

    if (storageSaveTimer) {
      window.clearTimeout(storageSaveTimer)
      storageSaveTimer = null
      saveTabsToStorageNow(schedulerTabs.value)
    }
    pendingLogUpdates.forEach(timer => window.clearTimeout(timer))
    pendingLogUpdates.clear()
    pendingLogContents.clear()

    // 移除电源状态变更事件监听器
    window.removeEventListener('power-state-changed', handlePowerStateChanged)
    logger.info('已移除电源状态变更事件监听器')

    // 注意：由于keep-alive机制，路由切换时组件不会卸载
    // cleanup只在组件真正销毁时才会调用（如应用关闭）
    // 所以这里清理所有订阅，包括运行中的任务
    logger.info('清理所有WebSocket订阅')
    schedulerTabs.value.forEach(tab => {
      try {
        unsubscribeTab(tab)
      } catch (error) {
        const errorMsg = error instanceof Error ? error.message : String(error)
        logger.warn(`清理订阅时发生错误: ${errorMsg}`)
      }
    })

    saveTabsToStorageNow(schedulerTabs.value)
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

    // 计算属性
    canChangePowerAction,
    currentTab,

    // Tab 管理
    addSchedulerTab,
    removeSchedulerTab,
    removeAllNonRunningTabs,

    // 任务操作
    trackStartedTask,
    startTask,
    stopTask,
    handleTaskSelectionChange,
    loadResumeScriptOptions,

    // 日志操作
    onLogScroll,
    setLogRef,

    // 电源操作
    onPowerActionChange,

    // 初始化与清理
    initialize,
    registerResidentSubscriptions,
    loadTaskOptions,
    getPowerState,
    cleanup,

    // 任务总览面板引用管理
    setOverviewRef,

    // 调试功能
    debugSubscriptionStatus,
  }
}

/**
 * 在建立主连接前注册调度中心常驻订阅（task.created / power.sign.updated）。
 * 幂等，供各启动路径（正常进入、跳过初始化、初始化向导）在 connect 前调用。
 */
export function bootstrapSchedulerSubscriptions() {
  useSchedulerLogic().registerResidentSubscriptions()
}
