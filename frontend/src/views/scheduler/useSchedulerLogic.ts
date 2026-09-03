import { translate as t } from '@/i18n'
import { computed, h, ref, watch } from 'vue'
import { message, Modal, notification } from 'ant-design-vue'
import { Service } from '@/api/services/Service'
import { useMaaEndIssueReport } from '@/composables/useMaaEndIssueReport'
import { TaskCreateIn } from '@/api/models/TaskCreateIn'
import { PowerIn } from '@/api/models/PowerIn'
import { useWebSocket } from '@/composables/useWebSocket'
import { useAudioPlayer } from '@/composables/useAudioPlayer'
import {
  getTaskRuntimeState,
  getTaskRuntimeStates,
  onTaskRuntimeEvent,
  refreshTaskRuntimeSnapshot,
  type TaskRuntimeEvent,
  type TaskRuntimeState,
} from '@/composables/useTaskRuntimeState'
import {
  WS_ID_MAIN,
  WS_POWER_SIGN_UPDATED,
  WS_TASK_LOG_UPDATED,
  WS_TASK_NOTICE,
  type WSTaskCompletedData,
  type WSTaskInfoUpdatedData,
  type WSTaskLogUpdatedData,
  type WSTaskNoticeData,
} from '@/services/websocket/types'
import type { ComboBoxItem } from '@/api/models/ComboBoxItem'
import type { QueueItem } from './schedulerConstants'
import { type SchedulerTab, type SchedulerStatus, TASK_MODE_OPTIONS } from './schedulerConstants'

// 运行态里的脚本执行模式 → 词表标签；词表里没有的模式（如 Update）保留原值
const runtimeModeLabel = (mode: string | null): string | null => {
  if (!mode) return null
  const option = TASK_MODE_OPTIONS.find(item => item.value === mode)
  return option ? t(option.labelKey) : mode
}

const logger = window.electronAPI.getLogger('调度台逻辑')

// 使用 sessionStorage 存储调度台状态，支持页面刷新时保留数据
// sessionStorage 在页面刷新时保留数据，但在关闭标签页/重启应用时清除
const SCHEDULER_TABS_KEY = 'scheduler-tabs-session'
const STORAGE_SAVE_DEBOUNCE_MS = 800
const LOG_RENDER_INTERVAL_MS = 200
const LOG_RENDER_MAX_CHARS = 120000
// /stop 成功后等待真实 task.completed 的窗口；仅超时未到达时才本地补齐
const STOP_COMPLETION_GRACE_MS = 1500

let storageSaveTimer: number | null = null
const pendingLogUpdates = new Map<string, number>()
const pendingLogContents = new Map<string, string>()
// MaaEnd 失败导出弹窗全局去重，避免同一批错误连环弹窗
let maaEndFailureModalOpen = false

const getDefaultTabRuntimeState = () => ({
  taskQueue: [],
  userQueue: [],
  logs: [],
  isLogAtBottom: true,
  lastLogContent: '',
  overviewData: undefined,
  lastMessageHash: '',
  lastMessageTime: 0,
  cycleNextList: [],
})

const trimLogForRender = (content: string) => {
  if (content.length <= LOG_RENDER_MAX_CHARS) return content

  const trimmed = content.slice(-LOG_RENDER_MAX_CHARS)
  const firstLineBreak = trimmed.indexOf('\n')
  const tail = firstLineBreak >= 0 ? trimmed.slice(firstLineBreak + 1) : trimmed
  return `${t('scheduler.log.truncated')}\n\n${tail}`
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
  selectedUserId: tab.selectedUserId ?? null,
  userOptions: tab.userOptions ? [...tab.userOptions] : [],
  userOptionsLoading: false,
  taskId: tab.taskId,
  subscriptionIds: [],
  runningTaskLabel: tab.runningTaskLabel,
  runningModeLabel: tab.runningModeLabel,
  logMode: tab.logMode || 'follow',
  // 不存这个的话，刷新后模式选项里没有「循环运行」，已选的循环模式会被静默改回自动代理
  isCycleQueue: tab.isCycleQueue ?? false,
  ...getDefaultTabRuntimeState(),
})

const normalizePersistedTab = (tab: SchedulerTab): SchedulerTab => ({
  ...tab,
  ...getDefaultTabRuntimeState(),
  resumeScriptOptions: tab.resumeScriptOptions || [],
  resumeScriptLoading: false,
  userOptions: tab.userOptions || [],
  userOptionsLoading: false,
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
      title: t('scheduler.mainTab'),
      closable: false,
      status: '空闲',
      selectedTaskId: null,
      selectedMode: TaskCreateIn.mode.AUTO_PROXY,
      resumeFromScriptId: null,
      resumeScriptOptions: [],
      resumeScriptLoading: false,
      selectedUserId: null,
      userOptions: [],
      userOptionsLoading: false,
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
let _residentSubscriptionIds: string[] = []
let _disposeTaskRuntimeListener: (() => void) | null = null

export function useSchedulerLogic() {
  // WebSocket 实例
  const ws = useWebSocket()
  const { exportMaaEndIssueReport } = useMaaEndIssueReport(logger)

  const handleTaskCreated = (state: TaskRuntimeState) => {
    if (!state.taskName && !state.taskType) return
    logger.info(
      `收到新任务通知: 任务ID=${state.taskId}, 队列ID=${state.queueId}, 任务名称=${state.taskName}, 任务类型=${state.taskType}`
    )
    const tab = createSchedulerTabForTask(
      state.taskId,
      getRuntimeSelectedTaskId(state),
      state.taskName ?? undefined,
      state.taskType ?? undefined,
      true
    )
    applyRuntimeStateToTab(tab, state)
  }

  const createSchedulerTabForTask = (
    taskId: string,
    queueId?: string,
    taskName?: string,
    taskType?: string,
    notifyUser: boolean = true
  ) => {
    const existing = schedulerTabs.value.find(tab => tab.taskId === taskId)
    if (existing) {
      existing.status = '运行'
      if (queueId) existing.selectedTaskId = queueId
      if (taskName) existing.runningTaskLabel = taskName
      if (taskType) existing.runningModeLabel = taskType
      subscribeToTask(existing)
      return existing
    }

    // 使用现有的addSchedulerTab函数创建新调度台，并传入特定的配置选项
    const newTab = addSchedulerTab({
      title: t('scheduler.tabName', { n: tabCounter }),
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
    if (notifyUser) message.success(t('scheduler.toast.tabAutoCreated', { title: newTab.title }))

    saveTabsToStorage(schedulerTabs.value)
    return newTab
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
      title: options?.title || t('scheduler.tabName', { n: tabCounter }),
      closable: true,
      status: validStatus,
      selectedTaskId: options?.selectedTaskId || options?.taskId || null,
      selectedMode: TaskCreateIn.mode.AUTO_PROXY,
      resumeFromScriptId: null,
      resumeScriptOptions: [],
      resumeScriptLoading: false,
      selectedUserId: null,
      userOptions: [],
      userOptionsLoading: false,
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
    const existingTab = schedulerTabs.value.find(tab => tab.taskId === taskId)
    if (existingTab) {
      existingTab.status = '运行'
      existingTab.selectedTaskId = selectedTaskId
      existingTab.selectedMode = selectedMode
      existingTab.runningTaskLabel = taskLabel
      existingTab.runningModeLabel = modeLabel
      existingTab.logMode = 'follow'
      activeSchedulerTab.value = existingTab.key
      subscribeToTask(existingTab)
      const runtimeState = getTaskRuntimeState(taskId)
      if (runtimeState) applyRuntimeStateToTab(existingTab, runtimeState)
      return existingTab
    }

    const tab = addSchedulerTab({
      title: taskLabel,
      status: '运行',
      taskId,
      selectedTaskId,
    })
    tab.selectedMode = selectedMode
    tab.runningTaskLabel = taskLabel
    tab.runningModeLabel = modeLabel
    tab.logMode = 'follow'
    subscribeToTask(tab)
    const runtimeState = getTaskRuntimeState(taskId)
    if (runtimeState) applyRuntimeStateToTab(tab, runtimeState)
    saveTabsToStorage(schedulerTabs.value)
    return tab
  }

  const removeSchedulerTab = (key: string) => {
    const tab = schedulerTabs.value.find(t => t.key === key)
    if (!tab) return

    if (tab.status === '运行') {
      Modal.warning({
        title: t('scheduler.modal.cannotDeleteTitle'),
        content: t('scheduler.modal.cannotDeleteContent', { title: tab.title }),
        okText: t('scheduler.modal.gotIt'),
      })
      return
    }

    if (key === 'main') {
      message.warning(t('scheduler.toast.mainTabUndeletable'))
      return
    }

    Modal.confirm({
      title: t('scheduler.modal.deleteTitle'),
      content: t('scheduler.modal.deleteContent', { title: tab.title }),
      okText: t('scheduler.modal.deleteOk'),
      cancelText: t('common.cancel'),
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

        message.success(t('scheduler.toast.tabDeleted', { title: tab.title }))
      },
    })
  }

  // 批量删除所有未运行状态的调度台子页（主调度台除外）
  const removeAllNonRunningTabs = () => {
    const nonRunningTabs = schedulerTabs.value.filter(
      tab => tab.key !== 'main' && tab.status !== '运行'
    )

    if (nonRunningTabs.length === 0) {
      message.info(t('scheduler.toast.noIdleTabs'))
      return
    }

    Modal.confirm({
      title: t('scheduler.modal.batchDeleteTitle'),
      content: t('scheduler.modal.batchDeleteContent', { count: nonRunningTabs.length }),
      okText: t('scheduler.modal.deleteOk'),
      cancelText: t('common.cancel'),
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

        message.success(t('scheduler.toast.batchDeleted', { count: nonRunningTabs.length }))
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

  // 任务下拉里只有队列和脚本两类，所以「找得到且不是队列」即脚本任务
  const isScriptTask = (tab: SchedulerTab) => {
    const taskOption = taskOptions.value.find(item => item.value === tab.selectedTaskId)
    return Boolean(taskOption) && !isQueueTask(tab)
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
      message.error(t('scheduler.toast.loadQueueScriptsFailed'))
    } finally {
      tab.resumeScriptLoading = false
    }
  }

  // 脚本任务可以只跑其中一个用户，下拉口径与各脚本适配器一致：已启用且剩余天数不为 0
  const loadUserOptions = async (tab: SchedulerTab) => {
    if (!tab.selectedTaskId || !isScriptTask(tab)) {
      tab.userOptions = []
      tab.selectedUserId = null
      return
    }

    tab.userOptionsLoading = true
    try {
      const response = await Service.getUserApiScriptsUserGetPost({
        scriptId: tab.selectedTaskId,
        userId: null,
      })
      if (response.code !== 200) {
        tab.userOptions = []
        tab.selectedUserId = null
        return
      }

      const options: Array<{ label: string; value: string }> = []
      response.index.forEach(item => {
        const info = response.data?.[item.uid]?.Info
        if (!info?.Status || info.RemainedDay === 0) return
        options.push({ value: item.uid, label: info.Name || item.uid })
      })

      tab.userOptions = options
      if (tab.selectedUserId && !options.some(item => item.value === tab.selectedUserId)) {
        tab.selectedUserId = null
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`加载脚本用户列表失败: ${errorMsg}`)
      tab.userOptions = []
      tab.selectedUserId = null
      message.error(t('scheduler.toast.loadScriptUsersFailed'))
    } finally {
      tab.userOptionsLoading = false
    }
  }

  const handleTaskSelectionChange = async (tab: SchedulerTab, taskId: string | null) => {
    tab.selectedTaskId = taskId
    tab.resumeFromScriptId = null
    tab.selectedUserId = null
    await Promise.all([loadResumeScriptOptions(tab), loadUserOptions(tab), loadCycleQueueFlag(tab)])
  }

  // 只有循环队列能选「循环运行」，先问后端拿队列类型再决定给不给这个模式
  const loadCycleQueueFlag = async (tab: SchedulerTab) => {
    if (!tab.selectedTaskId || !isQueueTask(tab)) {
      tab.isCycleQueue = false
      if (tab.selectedMode === TaskCreateIn.mode.CYCLE_RUN) {
        tab.selectedMode = TaskCreateIn.mode.AUTO_PROXY
      }
      return
    }

    try {
      const response = await Service.getQueuesApiQueueGetPost({ queueId: tab.selectedTaskId })
      tab.isCycleQueue =
        response.code === 200 &&
        Boolean(response.data?.[tab.selectedTaskId]?.Info?.CycleEnabled)
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.warn(`获取队列类型失败，按定时队列处理: ${errorMsg}`)
      tab.isCycleQueue = false
    }

    if (!tab.isCycleQueue && tab.selectedMode === TaskCreateIn.mode.CYCLE_RUN) {
      tab.selectedMode = TaskCreateIn.mode.AUTO_PROXY
    }
  }

  const startTask = async (tab: SchedulerTab) => {
    if (!tab.selectedTaskId || !tab.selectedMode) {
      message.error(t('scheduler.toast.needTaskAndMode'))
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
      if (tab.selectedUserId) {
        requestBody.userId = tab.selectedUserId
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
        tab.cycleNextList = []
        tab.logMode = 'follow' // 任务开始时设置日志为保持最新模式

        subscribeToTask(tab)
        const runtimeState = getTaskRuntimeState(response.taskId)
        if (runtimeState) applyRuntimeStateToTab(tab, runtimeState)

        // 播放任务启动成功音频
        const { playSound } = useAudioPlayer()
        await playSound('task_started')

        message.success(t('scheduler.toast.taskStarted'))
        saveTabsToStorage(schedulerTabs.value)
      } else {
        message.error(response.message || t('scheduler.toast.startTaskFailed'))
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`启动任务失败: ${errorMsg}`)
      message.error(t('scheduler.toast.startTaskFailed'))
    }
  }

  // 按任务 ID 直接启动（供托盘「启动任务」等外部入口使用）：新建调度台并启动，与正常运行行为一致
  const startTaskById = async (taskId: string, taskLabel?: string) => {
    if (!taskId) return false

    try {
      const response = await Service.addTaskApiDispatchStartPost({
        taskId,
        mode: TaskCreateIn.mode.AUTO_PROXY,
      })

      if (response.code !== 200) {
        message.error(response.message || t('scheduler.toast.startTaskFailed'))
        return false
      }

      trackStartedTask({
        taskId: response.taskId,
        selectedTaskId: taskId,
        selectedMode: TaskCreateIn.mode.AUTO_PROXY,
        taskLabel: taskLabel || taskId,
        modeLabel: t('scheduler.mode.autoProxy'),
      })

      const { playSound } = useAudioPlayer()
      await playSound('task_started')
      message.success(t('scheduler.toast.taskBegun'))
      return true
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`按任务 ID 启动失败: ${errorMsg}`)
      message.error(t('scheduler.toast.startTaskFailed'))
      return false
    }
  }

  /**
   * 构造停止任务的本地完成数据。
   *
   * 沿用当前总览快照，避免补齐状态时把面板清空；result 留空以保留已有日志。
   */
  const buildStoppedCompletion = (tab: SchedulerTab): WSTaskCompletedData => ({
    result: '',
    outcome: 'cancelled',
    error: null,
    task_info: (tab.overviewData ?? []).map(script => ({
      script_id: script.script_id,
      name: script.name,
      status: script.status,
      userList: script.user_list.map(user => ({
        user_id: user.user_id,
        name: user.name,
        status: user.status,
      })),
    })),
  })

  const stopTask = async (tab: SchedulerTab) => {
    if (!tab.taskId) return

    const taskId = tab.taskId
    try {
      const response = await Service.stopTaskApiDispatchStopPost({ taskId })
      if (response.code !== 200) {
        throw new Error(response.message || t('scheduler.toast.stopTaskFailed'))
      }

      // 播放任务中止音频
      const { playSound } = useAudioPlayer()
      await playSound('maa_task_aborted')

      // stop 接口内部会等待任务收尾，返回时后端已经结束该任务，且 task.completed
      // 在 HTTP 响应生成前就已写入主连接（final_task 先于 accomplish 置位）。
      // 连接健康时先给真实完成消息留出短暂窗口，避免本地合成快照抢先清掉 taskId、
      // 导致随后到达的权威结果找不到调度台而被丢弃；WebSocket 断线丢失完成消息时，
      // 窗口结束后才本地补齐，防止调度台永久停留在运行中。
      if (tab.taskId === taskId && ws.state.value === 'open') {
        await new Promise(resolve => window.setTimeout(resolve, STOP_COMPLETION_GRACE_MS))
      }
      if (tab.taskId === taskId) {
        await handleTaskCompleted(tab, buildStoppedCompletion(tab))
      } else {
        saveTabsToStorage(schedulerTabs.value)
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`停止任务失败: ${errorMsg}`)
      message.error(errorMsg)
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
      ws.subscribe({ id: taskId, type: WS_TASK_LOG_UPDATED }, wsMessage =>
        handleTaskLogUpdated(tab, wsMessage.data)
      ),
      ws.subscribe({ id: taskId, type: WS_TASK_NOTICE }, wsMessage =>
        handleTaskNotice(tab, wsMessage.data)
      ),
    ]
    logger.info(`新建WebSocket订阅: key=${tab.key}, taskId=${taskId}`)
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

  const applyTaskInfoSnapshot = (tab: SchedulerTab, data: WSTaskInfoUpdatedData): boolean => {
    tab.cycleNextList = data.cycleNextList ?? []
    if (!data.task_info || !Array.isArray(data.task_info)) {
      logger.debug('没有task_info数据，保持现有overviewData')
      return false
    }

    const overviewPanel = overviewRefs.value.get(tab.key)
    if (overviewPanel && overviewPanel.applyTaskInfo) {
      overviewPanel.applyTaskInfo(data.task_info)
    }

    try {
      tab.overviewData = data.task_info.map((s, index) => ({
        script_id: s.script_id || `script_${index}`,
        name: s.name || t('scheduler.overview.unknownScript'),
        status: s.status || '等待',
        user_list: (s.userList ?? []).map((user, userIndex) => ({
          user_id: user.user_id || `user_${index}_${userIndex}`,
          name: user.name,
          status: user.status,
        })),
      }))
    } catch (e) {
      const errorMsg = e instanceof Error ? e.message : String(e)
      logger.warn(`维护 overviewData 快照时出现问题: ${errorMsg}`)
    }

    const newTaskQueue = data.task_info.map(item => ({
      name: item.name || t('scheduler.overview.unknownTask'),
      status: item.status || '等待',
    }))

    const newUserQueue: QueueItem[] = []
    data.task_info.forEach(taskItem => {
      if (taskItem.userList && Array.isArray(taskItem.userList)) {
        taskItem.userList.forEach(user => {
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

  const handleTaskLogUpdated = (tab: SchedulerTab, data: WSTaskLogUpdatedData) => {
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

  const handleTaskNotice = async (tab: SchedulerTab, data: WSTaskNoticeData) => {
    const { playSound } = useAudioPlayer()

    if (data.level === 'error') {
      const errorMsg = String(data.message).toLowerCase()
      const taskLabel =
        taskOptions.value.find(item => item.value === tab.selectedTaskId)?.label || ''
      const isMaaEndTask = [taskLabel, tab.runningTaskLabel, tab.runningModeLabel]
        .filter(Boolean)
        .some(value => value?.toLowerCase().includes('maaend') ?? false)

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

      const isMaaEndError = isMaaEndTask || errorMsg.includes('maaend')
      if (isMaaEndError) {
        if (!maaEndFailureModalOpen) {
          maaEndFailureModalOpen = true
          Modal.error({
            centered: true,
            closable: true,
            maskClosable: true,
            keyboard: true,
            title: t('scheduler.modal.maaEndFailTitle'),
            content: h('div', [
              h('p', String(data.message)),
              h('p', t('scheduler.modal.maaEndFailHint')),
            ]),
            okCancel: true,
            okText: t('scheduler.modal.maaEndExport'),
            cancelText: t('scheduler.modal.maaEndSkip'),
            onOk: () => {
              void exportMaaEndIssueReport()
            },
            afterClose: () => {
              maaEndFailureModalOpen = false
            },
          })
        }
      } else {
        notification.error({ message: t('scheduler.toast.taskError'), description: data.message })
      }
    } else if (data.level === 'warning') {
      // 播放异常音频
      await playSound('exception_occurred')
      notification.warning({ message: t('scheduler.toast.taskWarning'), description: data.message })
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

      notification.info({ message: t('scheduler.toast.taskInfo'), description: data.message })
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
    tab.status = data.outcome === 'error' ? '异常' : '结束'
    tab.cycleNextList = []
    logger.info(`已更新tab.status，当前tab状态: ${JSON.stringify(tab.status)}`)

    logger.info(`任务完成，清理订阅与任务ID: key=${tab.key}, taskId=${tab.taskId}`)
    try {
      unsubscribeTab(tab)
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.warn(`清理订阅时发生错误: ${errorMsg}`)
    }
    tab.taskId = null

    // 清理完成后再替换响应式对象，避免数组中保留旧的任务ID和订阅ID
    const tabIndex = schedulerTabs.value.findIndex(t => t.key === tab.key)
    if (tabIndex !== -1) {
      const updatedTab: SchedulerTab = { ...tab }
      schedulerTabs.value.splice(tabIndex, 1, updatedTab)
    }

    const { playSound } = useAudioPlayer()
    if (data.outcome === 'error') {
      await playSound('error_occurred')
      message.error(data.error || t('scheduler.toast.taskRunFailed'))
    } else if (data.outcome === 'cancelled') {
      message.warning(t('scheduler.toast.taskCancelled'))
    } else {
      await playSound('task_completed')
      message.success(t('scheduler.toast.taskDone'))
    }
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
      message.error(t('scheduler.toast.powerActionFailed'))
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
        message.error(t('scheduler.toast.fetchTaskListFailed'))
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`获取任务列表失败: ${errorMsg}`)
      message.error(t('scheduler.toast.fetchTaskListFailed'))
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

  const taskModeFromRuntime = (mode: TaskRuntimeState['mode']): TaskCreateIn.mode => {
    switch (mode) {
      case TaskCreateIn.mode.UPDATE:
        return TaskCreateIn.mode.UPDATE
      case TaskCreateIn.mode.SCRIPT_CONFIG:
        return TaskCreateIn.mode.SCRIPT_CONFIG
      case TaskCreateIn.mode.AUTO_PROXY:
      default:
        return TaskCreateIn.mode.AUTO_PROXY
    }
  }

  const getRuntimeSelectedTaskId = (state: TaskRuntimeState): string | undefined =>
    state.queueId ?? state.scriptId ?? state.userId ?? state.scripts[0]?.scriptId ?? undefined

  const completedDataFromState = (state: TaskRuntimeState): WSTaskCompletedData | null =>
    state.outcome
      ? {
          result: state.result ?? '',
          outcome: state.outcome,
          error: state.error,
          task_info: state.taskInfo,
        }
      : null

  const applyRuntimeStateToTab = (tab: SchedulerTab, state: TaskRuntimeState): void => {
    if (state.phase === 'completed') {
      const completedData = completedDataFromState(state)
      if (completedData && tab.taskId === state.taskId) {
        void handleTaskCompleted(tab, completedData)
      }
      return
    }

    tab.status = '运行'
    if (state.mode) tab.selectedMode = taskModeFromRuntime(state.mode)
    // 快照里的 mode 是脚本执行模式，循环与否只看 isCycle
    if (state.isCycle) {
      tab.selectedMode = TaskCreateIn.mode.CYCLE_RUN
      tab.isCycleQueue = true
    }
    // 没有任务类型文案（调度台手动启动）时按模式取词表标签，别把枚举原值亮给用户
    tab.runningModeLabel =
      state.taskType ??
      (state.isCycle ? t('scheduler.mode.cycleRun') : runtimeModeLabel(state.mode)) ??
      tab.runningModeLabel
    if (state.taskName) tab.runningTaskLabel = state.taskName
    const selectedTaskId = getRuntimeSelectedTaskId(state)
    if (selectedTaskId) tab.selectedTaskId = selectedTaskId
    applyTaskInfoSnapshot(tab, {
      task_info: state.taskInfo,
      cycleNextList: state.cycleNextList,
    })
    subscribeToTask(tab)
  }

  const applyRuntimeTaskSnapshot = (state: TaskRuntimeState): void => {
    const selectedTaskId = getRuntimeSelectedTaskId(state)
    const tab = createSchedulerTabForTask(
      state.taskId,
      selectedTaskId,
      state.taskName ?? selectedTaskId,
      state.taskType ?? state.mode ?? undefined,
      false
    )
    applyRuntimeStateToTab(tab, state)
    if (state.log) scheduleLogContentUpdate(tab, state.log, true)
  }

  const markRuntimeTaskRemoved = (taskId: string): void => {
    const tab = schedulerTabs.value.find(item => item.taskId === taskId)
    if (!tab) return
    logger.info(`运行快照确认任务已结束: key=${tab.key}, taskId=${taskId}`)
    unsubscribeTab(tab)
    tab.status = '结束'
    tab.taskId = null
    tab.logMode = 'browse'
    schedulerTabs.value = [...schedulerTabs.value]
    saveTabsToStorage(schedulerTabs.value)
  }

  const handleTaskRuntimeEvent = async (event: TaskRuntimeEvent): Promise<void> => {
    if (event.type === 'created') {
      handleTaskCreated(event.state)
      return
    }
    if (event.type === 'info') {
      const tab = schedulerTabs.value.find(item => item.taskId === event.state.taskId)
      if (tab) applyRuntimeStateToTab(tab, event.state)
      return
    }
    if (event.type === 'completed') {
      const tab = schedulerTabs.value.find(item => item.taskId === event.state.taskId)
      const completedData = completedDataFromState(event.state)
      if (tab && completedData) await handleTaskCompleted(tab, completedData)
      return
    }
    if (event.type === 'snapshot') {
      event.states.forEach(applyRuntimeTaskSnapshot)
      for (const tab of schedulerTabs.value) {
        if (tab.status === '运行' && tab.taskId && !event.activeTaskIds.has(tab.taskId)) {
          markRuntimeTaskRemoved(tab.taskId)
        }
      }
      return
    }
    if (event.type === 'removed') markRuntimeTaskRemoved(event.taskId)
  }

  const refreshRuntimeSnapshot = refreshTaskRuntimeSnapshot

  // 注册调度中心常驻消费者（幂等）。task.* 的权威状态由 task-runtime
  // 常驻资源统一维护；调度器这里只消费状态事件并保留日志、提示订阅。
  const registerResidentSubscriptions = () => {
    if (_residentSubscribed) return
    _residentSubscribed = true

    // keep-alive 下路由切换不取消，应用关闭时随进程释放
    _residentSubscriptionIds = [
      ws.subscribe({ id: WS_ID_MAIN, type: WS_POWER_SIGN_UPDATED }, wsMessage =>
        updatePowerActionDisplay(wsMessage.data.signal)
      ),
    ]
    _disposeTaskRuntimeListener = onTaskRuntimeEvent(handleTaskRuntimeEvent)
    getTaskRuntimeStates()
      .filter(state => state.phase !== 'completed')
      .forEach(applyRuntimeTaskSnapshot)
    logger.info('已注册调度中心常驻消费者 (task runtime / power.sign.updated)')
  }

  const disposeResidentSubscriptions = () => {
    _disposeTaskRuntimeListener?.()
    _disposeTaskRuntimeListener = null
    for (const subscriptionId of _residentSubscriptionIds.splice(0)) {
      ws.unsubscribe(subscriptionId)
    }
    schedulerTabs.value.forEach(tab => unsubscribeTab(tab))
    _residentSubscribed = false
    logger.info('已释放调度中心常驻订阅')
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

    // 为已有调度台预加载恢复脚本 / 用户选项，确保刷新后恢复交互可用
    schedulerTabs.value.forEach(tab => {
      if (tab.status === '运行') return
      if (isQueueTask(tab)) {
        loadResumeScriptOptions(tab)
      } else if (isScriptTask(tab)) {
        loadUserOptions(tab)
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
    startTaskById,
    stopTask,
    handleTaskSelectionChange,
    loadResumeScriptOptions,
    loadUserOptions,

    // 日志操作
    onLogScroll,
    setLogRef,

    // 电源操作
    onPowerActionChange,

    // 初始化与清理
    initialize,
    registerResidentSubscriptions,
    disposeResidentSubscriptions,
    refreshRuntimeSnapshot,
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

/** 应用最终退出时释放调度中心常驻与任务订阅。 */
export function disposeSchedulerSubscriptions() {
  useSchedulerLogic().disposeResidentSubscriptions()
}
