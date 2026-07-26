import { computed, ref, watch } from 'vue'
import { message, Modal, notification } from 'ant-design-vue'
import { Service } from '@/api/services/Service'
import { TaskCreateIn } from '@/api/models/TaskCreateIn'
import { useWebSocket, ExternalWSHandlers } from '@/composables/useWebSocket'
import { useAudioPlayer } from '@/composables/useAudioPlayer'
import schedulerHandlers from './schedulerHandlers'
import type { ComboBoxItem } from '@/api/models/ComboBoxItem'
import {
  WS_ID_MAIN,
  WS_SNAPSHOT_REQUEST,
  WS_TASK_COMPLETED,
  WS_TASK_INFO_UPDATED,
  WS_TASK_LOG_UPDATED,
  WS_TASK_NOTICE,
  type WSTaskCompletedData,
  type WSTaskNoticeData,
} from '@/services/websocket/types'
import type { QueueItem } from './schedulerConstants'
import {
  type SchedulerTab,
  type TaskMessage,
  type SchedulerTabStatus,
  type SchedulerConnectionState,
  isValidSchedulerTabStatus,
} from './schedulerConstants'
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
  websocketId: tab.websocketId,
  subscriptionIds: [],
  subscriptionId: null,
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
  subscriptionId: null,
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
      websocketId: null,
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

// 消息弹窗
const messageModalVisible = ref(false)
const currentMessage = ref<TaskMessage | null>(null)
const messageResponse = ref('')

// 初始化标志 - 确保某些操作只执行一次
let _initialized = false
let _watchInitialized = false

export function useSchedulerLogic() {
  // WebSocket 实例
  const ws = useWebSocket()

  // 调度器连接状态（从 WebSocket 状态派生）
  const schedulerConnectionState = computed<SchedulerConnectionState>(() => {
    const wsStatus = ws.status.value
    switch (wsStatus) {
      case '连接中':
        return 'connecting'
      case '已连接':
        return 'connected'
      case '已断开':
        return 'disconnected'
      case '连接错误':
        return 'failed'
      default:
        return 'idle'
    }
  })

  const isSchedulerConnected = computed(() => schedulerConnectionState.value === 'connected')

  const taskSubscriptionIds = (tab: SchedulerTab): string[] => {
    const ids = [...(tab.subscriptionIds ?? [])]
    if (tab.subscriptionId && !ids.includes(tab.subscriptionId)) ids.push(tab.subscriptionId)
    return ids
  }

  const unsubscribeTab = (tab: SchedulerTab) => {
    for (const subscriptionId of taskSubscriptionIds(tab)) {
      try {
        ws.unsubscribe(subscriptionId)
      } catch (error) {
        const errorMsg = error instanceof Error ? error.message : String(error)
        logger.warn(`清理订阅 ${subscriptionId} 时发生错误: ${errorMsg}`)
      }
    }
    tab.subscriptionIds = []
    tab.subscriptionId = null
  }

  // TaskManager消息处理函数（供全局WebSocket调用）
  const handleTaskManagerMessage = (wsMessage: any) => {
    if (!wsMessage || typeof wsMessage !== 'object') return

    const { type, data } = wsMessage
    logger.info(`收到TaskManager消息: 类型=${type}, 数据=${JSON.stringify(data)}`)

    if (type === 'Signal' && data && data.newTask) {
      // 收到新任务信号，自动创建调度台
      const taskId = data.newTask
      const queueId = data.queueId
      const taskName = data.taskName
      const taskType = data.taskType
      logger.info(
        `收到新任务信号: 任务ID=${taskId}, 队列ID=${queueId}, 任务名称=${taskName}, 任务类型=${taskType}`
      )

      // 创建新的调度台
      createSchedulerTabForTask(taskId, queueId, taskName, taskType)
    }
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
      websocketId: taskId,
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
    websocketId?: string
    selectedTaskId?: string
  }) => {
    tabCounter++
    const status = options?.status || '空闲'
    // 使用 schedulerConstants 的统一校验集合，避免类型与校验集合不一致
    const validStatus: SchedulerTabStatus = isValidSchedulerTabStatus(status) ? status : '空闲'

    const tab: SchedulerTab = {
      key: `tab-${tabCounter}`,
      title: options?.title || `调度台${tabCounter}`,
      closable: true,
      status: validStatus,
      selectedTaskId: options?.selectedTaskId || options?.websocketId || null,
      selectedMode: TaskCreateIn.mode.AUTO_PROXY,
      resumeFromScriptId: null,
      resumeScriptOptions: [],
      resumeScriptLoading: false,
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

    // 运行中的任务不允许直接删除，必须先停止
    // 停止中/失败/结束/空闲 均可删除
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
  // 停止中的任务也不允许批量删除，避免删除正在停止的 tab 导致订阅泄漏
  const removeAllNonRunningTabs = () => {
    const nonRunningTabs = schedulerTabs.value.filter(
      tab => tab.key !== 'main' && tab.status !== '运行' && tab.status !== '停止中'
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
      if (tab.resumeFromScriptId && tab.selectedMode !== TaskCreateIn.mode.CYCLE_RUN) {
        requestBody.resumeFromScriptId = tab.resumeFromScriptId
      }

      const response = await Service.addTaskApiDispatchStartPost(requestBody)

      if (response.code === 200) {
        tab.status = '运行'
        tab.websocketId = response.taskId

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
    if (!tab.websocketId) return

    // 进入停止中状态，防止重复点击 stop，并提供 UI 反馈
    const previousStatus = tab.status
    tab.status = '停止中'

    try {
      const response = await Service.stopTaskApiDispatchStopPost({
        taskId: tab.websocketId,
      })

      // 后端 dispatch.py 在异常时返回 OutBase(code=500)，HTTP 仍为 200
      // 必须显式检查 response.code，否则 code=500 会被当作成功
      if (response.code !== 200) {
        // 停止失败：恢复原状态，标记失败，不播放成功音频
        tab.status = previousStatus === '运行' ? '失败' : previousStatus
        const backendMsg = response.message || '未知错误'
        logger.error(`停止任务失败: 后端返回 code=${response.code}, message=${backendMsg}`)
        message.error(`停止任务失败: ${backendMsg}`)
        saveTabsToStorage(schedulerTabs.value)
        return
      }

      // 播放任务中止音频
      const { playSound } = useAudioPlayer()
      await playSound('maa_task_aborted')

      // 保持"停止中"状态，等待后端通过 WebSocket 发送真实结束信号
      // WS Accomplish 信号到达后 handleSignalMessage 会将状态切为"结束"
      message.info('正在停止任务，请稍候...')
      saveTabsToStorage(schedulerTabs.value)
    } catch (error) {
      // 网络异常等：恢复原状态，标记失败
      tab.status = previousStatus === '运行' ? '失败' : previousStatus
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`停止任务请求异常: ${errorMsg}`)
      message.error('停止任务失败')
      saveTabsToStorage(schedulerTabs.value)
    }
  }

  // WebSocket 订阅与消息处理
  const subscribeToTask = (tab: SchedulerTab) => {
    if (!tab.websocketId) return

    // 如果订阅已存在且 WebSocket ID 未改变，则不重复注册。
    if (taskSubscriptionIds(tab).length > 0) {
      logger.info(`订阅已存在，跳过重复订阅: {
        key: ${tab.key},
        subscriptionIds: ${taskSubscriptionIds(tab).join(',')},
        websocketId: ${tab.websocketId},
      }`)
      return
    }

    const messageTypes = [
      WS_TASK_INFO_UPDATED,
      WS_TASK_LOG_UPDATED,
      WS_TASK_NOTICE,
      WS_TASK_COMPLETED,
      // 迁移期兼容尚未升级的宿主或插件发送器。
      'Update',
      'Info',
      'Message',
      'Signal',
    ]
    tab.subscriptionIds = messageTypes.map(type =>
      ws.subscribe({ id: tab.websocketId!, type }, message => handleWebSocketMessage(tab, message))
    )
    tab.subscriptionId = null
    logger.info(
      `新建WebSocket订阅: ${JSON.stringify({
        key: tab.key,
        websocketId: tab.websocketId,
        subscriptionIds: tab.subscriptionIds,
      })}`
    )

    if (tab.subscriptionIds.some(subscriptionId => !subscriptionId)) {
      logger.error(
        `WebSocket订阅创建失败！: ${JSON.stringify({
          key: tab.key,
          websocketId: tab.websocketId,
        })}`
      )
      message.error('WebSocket订阅创建失败，可能无法接收任务消息')
    }
  }

  const handleWebSocketMessage = (tab: SchedulerTab, wsMessage: any) => {
    if (!wsMessage || typeof wsMessage !== 'object') return

    const { id, type, data } = wsMessage

    // 处理全局消息（如电源操作倒计时）
    if (id === 'Main' && type === 'Message' && data?.type === 'Countdown') {
      logger.info(`收到全局倒计时消息: ${JSON.stringify(data)}`)
      handleMessageDialog(tab, data)
      return
    }

    // 只处理与当前标签页相关的消息
    if (id && id !== tab.websocketId) {
      logger.info(`消息ID不匹配，忽略消息: messageId=${id}, tabId=${tab.websocketId}`)
      return
    }

    // 停止中状态：忽略迟到的 Update/Info/log 消息，防止旧快照覆盖状态
    // 仅允许 Accomplish/Completed 信号通过，以完成停止→结束的状态转换
    // 这修复了"停止后旧 WS 消息覆盖状态"的缺陷
    if (
      tab.status === '停止中' &&
      (type === 'Update' ||
        type === WS_TASK_INFO_UPDATED ||
        type === WS_TASK_LOG_UPDATED ||
        type === 'Info' ||
        type === 'Message')
    ) {
      logger.info(
        `停止中状态忽略迟到消息: type=${type}, tabKey=${tab.key}, websocketId=${tab.websocketId}`
      )
      return
    }

    switch (type) {
      case 'Update':
        logger.debug(
          `处理Update消息: taskInfo=${Array.isArray(data?.task_info) ? data.task_info.length : 0}, logLength=${typeof data?.log === 'string' ? data.log.length : 0}`
        )
        handleUpdateMessage(tab, data)
        break
      case 'Info':
        logger.debug(`处理Info消息: ${JSON.stringify(data)}`)
        handleInfoMessage(data)
        break
      case 'Message':
        logger.debug(`处理Message消息: ${JSON.stringify(data)}`)
        handleMessageDialog(tab, data)
        break
      case 'Signal':
        logger.debug(`处理Signal消息: ${JSON.stringify(data)}`)
        handleSignalMessage(tab, data)
        break
      case WS_TASK_INFO_UPDATED:
      case WS_TASK_LOG_UPDATED:
        handleUpdateMessage(tab, data)
        break
      case WS_TASK_NOTICE: {
        const notice = data as WSTaskNoticeData
        const legacyNotice =
          notice.level === 'error'
            ? { Error: notice.message }
            : notice.level === 'warning'
              ? { Warning: notice.message }
              : { Info: notice.message }
        void handleInfoMessage(legacyNotice)
        break
      }
      case WS_TASK_COMPLETED: {
        const completed = data as WSTaskCompletedData
        void handleSignalMessage(tab, {
          Accomplish: completed.result,
          task_info: completed.task_info,
        })
        break
      }
      default:
        logger.warn(`未知的WebSocket消息类型: ${type}, ${JSON.stringify(wsMessage)}`)
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

  const buildTaskInfoSignature = (taskInfo: any[] | undefined, data?: any) => {
    if (!Array.isArray(taskInfo)) return ''

    const taskSignature = taskInfo
      .map((task, index) => {
        const users = Array.isArray(task.userList)
          ? task.userList.map((user: any) => `${user.name || ''}:${user.status || ''}`).join(',')
          : ''
        return `${task.script_id || index}:${task.name || ''}:${task.status || ''}[${users}]`
      })
      .join('|')
    const cycleSignature = JSON.stringify({
      queueId: data?.cycleQueueId ?? null,
      currentItemId: data?.cycleCurrentItemId ?? null,
      waitingReason: data?.cycleWaitingReason ?? null,
      nextRunAt: data?.cycleNextRunAt ?? null,
      nextList: data?.cycleNextList ?? [],
    })
    return `${taskSignature}#${cycleSignature}`
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

  const applyTaskInfoSnapshot = (tab: SchedulerTab, data: any): boolean => {
    if (!data.task_info || !Array.isArray(data.task_info)) {
      logger.debug('没有task_info数据，保持现有overviewData')
      return false
    }

    const overviewPanel = overviewRefs.value.get(tab.key)
    if (overviewPanel && overviewPanel.handleWSMessage) {
      overviewPanel.handleWSMessage({
        type: 'Update',
        id: tab.websocketId,
        data,
      })
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

  const handleUpdateMessage = (tab: SchedulerTab, data: any) => {
    // 添加消息去重机制
    const taskInfoSignature = buildTaskInfoSignature(data.task_info, data)
    const messageKey = `${tab.key}_${taskInfoSignature}`
    const currentTime = Date.now()

    // 检查是否是重复消息
    if (!tab.lastMessageHash) tab.lastMessageHash = ''
    if (!tab.lastMessageTime) tab.lastMessageTime = 0

    if (
      taskInfoSignature &&
      tab.lastMessageHash === messageKey &&
      currentTime - tab.lastMessageTime < 100 &&
      data.log === undefined
    ) {
      logger.debug(`重复的Update消息被过滤: ${tab.key}`)
      return
    }

    if (taskInfoSignature) {
      tab.lastMessageHash = messageKey
      tab.lastMessageTime = currentTime
    }

    applyTaskInfoSnapshot(tab, data)

    // 处理日志 - 直接显示完整日志内容，覆盖上次显示的内容
    if (data.log) {
      if (typeof data.log === 'string') {
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
      } else if (typeof data.log === 'object') {
        let newContent = ''
        if (data.log.Error) newContent = data.log.Error
        else if (data.log.Warning) newContent = data.log.Warning
        else if (data.log.Info) newContent = data.log.Info
        else newContent = JSON.stringify(data.log)

        if (tab.lastLogContent !== newContent) {
          scheduleLogContentUpdate(tab, newContent)
          logger.debug(
            `更新日志对象: ${JSON.stringify({
              tabKey: tab.key,
              contentLength: newContent.length,
            })}`
          )
        }
      }
    }
    // 移除可能导致递归更新的 saveTabsToStorage 调用
    // saveTabsToStorage(schedulerTabs.value)
  }

  const handleInfoMessage = async (data: any) => {
    const { playSound } = useAudioPlayer()

    if (data.Error) {
      const errorMsg = String(data.Error).toLowerCase()

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

      notification.error({ message: '任务错误', description: data.Error })
    } else if (data.Warning) {
      // 播放异常音频
      await playSound('exception_occurred')
      notification.warning({ message: '任务警告', description: data.Warning })
    } else if (data.Info) {
      const infoMsg = String(data.Info).toLowerCase()

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

      notification.info({ message: '任务信息', description: data.Info })
    }
  }

  const handleMessageDialog = (tab: SchedulerTab, data: any) => {
    // 处理倒计时消息 - 已移至全局组件处理
    if (data.type === 'Countdown') {
      logger.info(`收到倒计时消息，由全局组件处理: ${JSON.stringify(data)}`)
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

  const handleSignalMessage = async (tab: SchedulerTab, data: any) => {
    logger.debug(`处理Signal消息: ${JSON.stringify(data)}`)

    // 只有收到WebSocket的Accomplish信号才将任务标记为结束状态
    // 这确保了调度台状态与实际任务执行状态严格同步
    if (data && data.Accomplish) {
      // 已结束/失败的 tab 忽略重复的 Accomplish 信号，避免重复清理和音频播放
      if (tab.status === '结束' || tab.status === '失败') {
        logger.info(`忽略重复 Accomplish 信号: tabKey=${tab.key}, 当前状态=${tab.status}`)
        return
      }
      logger.info('收到Accomplish信号，设置任务状态为结束')

      applyTaskInfoSnapshot(tab, data)

      // 清空日志并显示原始代理结果信息
      const resultText = data.Accomplish
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
        logger.debug(
          `已强制更新schedulerTabs，当前tabs状态: ${JSON.stringify(schedulerTabs.value)}`
        )
      }

      if (taskSubscriptionIds(tab).length > 0) {
        logger.info(
          `任务完成，清理WebSocket订阅: ${JSON.stringify({
            key: tab.key,
            subscriptionIds: taskSubscriptionIds(tab),
            websocketId: tab.websocketId,
          })}`
        )
        unsubscribeTab(tab)
      }

      if (tab.websocketId) {
        logger.info(
          `任务完成，清理websocketId: ${JSON.stringify({
            key: tab.key,
            websocketId: tab.websocketId,
          })}`
        )
        tab.websocketId = null
      }

      // 播放任务完成音频
      const { playSound } = useAudioPlayer()
      await playSound('task_completed')

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
      logger.debug(`设置 TaskOverviewPanel 引用: ${key}, ${JSON.stringify(el)}`)
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
            })),
          },
        }
        try {
          el.handleWSMessage(wsMessage)
        } catch (e) {
          const errorMsg = e instanceof Error ? e.message : String(e)
          logger.warn(`回放 overviewData 到面板时异常: ${errorMsg}`)
        }
      }
    } else {
      overviewRefs.value.delete(key)
    }
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
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`获取任务列表失败: ${errorMsg}`)
      message.error('获取任务列表失败')
    } finally {
      taskOptionsLoading.value = false
    }
  }

  // 初始化函数 - 使用单例标志确保核心初始化只执行一次
  const initialize = () => {
    // 核心初始化只执行一次
    if (!_initialized) {
      _initialized = true
      logger.info('调度中心首次初始化开始')

      // 设置全局WebSocket的消息处理函数
      // 通过 import 的 ExternalWSHandlers 直接注册处理函数，保证导入方能够永久引用并调用
      ExternalWSHandlers.taskManagerMessage = handleTaskManagerMessage
      ExternalWSHandlers.mainMessage = handleMainMessage
      logger.info('已设置全局WebSocket消息处理函数')

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
                selectedTaskId: tab.queueId,
              })
              subscribeToTask(newTab)
              saveTabsToStorage(schedulerTabs.value)
            } catch (e) {
              const errorMsg = e instanceof Error ? e.message : String(e)
              logger.warn(`registerSchedulerUI onNewTab error: ${errorMsg}`)
            }
          },
          onCountdown: data => {
            try {
              // 倒计时已移至全局组件处理，这里不再处理
              logger.info(`倒计时消息由全局组件处理: ${JSON.stringify(data)}`)
            } catch (e) {
              const errorMsg = e instanceof Error ? e.message : String(e)
              logger.warn(`registerSchedulerUI onCountdown error: ${errorMsg}`)
            }
          },
        })
      } catch (e) {
        const errorMsg = e instanceof Error ? e.message : String(e)
        logger.warn(`schedulerHandlers registration failed: ${errorMsg}`)
      }

      logger.info('调度中心首次初始化完成')
    } else {
      logger.info('调度中心重复初始化跳过（单例模式）')
    }

    // 以下操作每次 initialize 调用都可以执行

    // 为已有调度台预加载恢复脚本选项，确保刷新后恢复交互可用
    schedulerTabs.value.forEach(tab => {
      if (tab.status !== '运行' && isQueueTask(tab)) {
        loadResumeScriptOptions(tab)
      }
    })

    // 回放 pending tabs（如果有的话）- 会被 consume 掉，所以多次调用是安全的
    try {
      const pending = schedulerHandlers.consumePendingTabIds()
      if (pending && pending.length > 0) {
        pending.forEach((item: any) => {
          try {
            const taskId = typeof item === 'string' ? item : item.taskId
            const queueId = typeof item === 'string' ? undefined : item.queueId

            const newTab = addSchedulerTab({
              title: `调度台自动-${taskId}`,
              status: '运行',
              websocketId: taskId,
              selectedTaskId: queueId,
            })
            subscribeToTask(newTab)
          } catch (e) {
            const errorMsg = e instanceof Error ? e.message : String(e)
            logger.warn(`replay pending tab error: ${errorMsg}`)
          }
        })
        saveTabsToStorage(schedulerTabs.value)
      }

      // 回放 pending countdown（如果有的话）
      const pendingCountdown = schedulerHandlers.consumePendingCountdown()
      if (pendingCountdown) {
        try {
          // 倒计时已移至全局组件处理，这里不再处理
          logger.info(`待处理倒计时消息由全局组件处理: ${JSON.stringify(pendingCountdown)}`)
        } catch (e) {
          const errorMsg = e instanceof Error ? e.message : String(e)
          logger.warn(`replay pending countdown error: ${errorMsg}`)
        }
      }
    } catch (e) {
      const errorMsg = e instanceof Error ? e.message : String(e)
      logger.warn(`pending回放时出现问题: ${errorMsg}`)
    }

    // 为已有的"运行"标签恢复 WebSocket 订阅，防止路由切换返回后不再更新
    // 注意：subscribeToTask 内部会检查订阅是否已存在，避免重复订阅
    try {
      schedulerTabs.value.forEach(tab => {
        if (tab.status === '运行' && tab.websocketId) {
          logger.info(
            `初始化阶段检查运行中标签的订阅: ${JSON.stringify({
              key: tab.key,
              websocketId: tab.websocketId,
              hasSubscription: taskSubscriptionIds(tab).length > 0,
            })}`
          )
          // subscribeToTask 会自动跳过已有订阅，保持缓存标记不丢失
          subscribeToTask(tab)
        } else if (tab.status === '停止中') {
          // 页面刷新后"停止中"的 tab 无法再收到 WS 完成信号，标记为失败
          // 避免永久停留在停止中状态
          logger.warn(
            `初始化阶段发现停止中的标签，标记为失败: ${JSON.stringify({
              key: tab.key,
              websocketId: tab.websocketId,
            })}`
          )
          tab.status = '失败'
          tab.websocketId = null
          unsubscribeTab(tab)
        }
      })
    } catch (e) {
      const errorMsg = e instanceof Error ? e.message : String(e)
      logger.warn(`恢复订阅时出现问题: ${errorMsg}`)
    }

    // 订阅就绪后主动补拉一次状态快照，修复冷启动时序断链：
    // 连接建立瞬间后端主动推送的 Main/snapshot.response 早于任务订阅建立会被丢弃，
    // 导致运行中任务状态无法恢复。此处所有订阅（sessionStorage 恢复 + pending 回放）
    // 均已建立，按需请求快照即可补齐。后端 dispatcher 按 envelope.id 回显
    // snapshot.response，而连接层只在 id=Main 时展开快照，故必须用 id=Main 请求。
    // 多次请求幂等无害；未连接时 send 返回 false，重连成功后后端会在 on_connect
    // 时自动推送快照（届时订阅已在），无需额外补偿。
    try {
      if (ws.send(WS_ID_MAIN, WS_SNAPSHOT_REQUEST, {})) {
        logger.info('已发送状态快照补拉请求（snapshot.request）')
      } else {
        logger.info('快照补拉请求未发送（连接未就绪），等待连接建立后由后端主动推送')
      }
    } catch (e) {
      const errorMsg = e instanceof Error ? e.message : String(e)
      logger.warn(`发送快照补拉请求失败: ${errorMsg}`)
    }
  }

  // Main消息处理函数（供全局WebSocket调用）
  const handleMainMessage = (wsMessage: any) => {
    if (!wsMessage || typeof wsMessage !== 'object') return

    const { type, data } = wsMessage
    logger.info(`收到Main消息: ${JSON.stringify({ type, data })}`)

    // 首先调用 schedulerHandlers 的处理函数，确保 RequestClose 等信号被正确处理
    try {
      schedulerHandlers.handleMainMessage(wsMessage)
    } catch (e) {
      const errorMsg = e instanceof Error ? e.message : String(e)
      logger.warn(`schedulerHandlers.handleMainMessage error: ${errorMsg}`)
    }

    if (type === 'Message' && data && data.type === 'Countdown') {
      // 收到倒计时消息，由全局组件处理
      logger.info(`收到倒计时消息，由全局组件处理: ${JSON.stringify(data)}`)
      // 不再在调度中心处理倒计时
    }
  }

  // 调试函数：检查所有调度台的订阅状态
  const debugSubscriptionStatus = () => {
    logger.info('当前调度台订阅状态:')
    schedulerTabs.value.forEach(tab => {
      logger.info(
        `- Tab ${tab.key} (${tab.title}): ${JSON.stringify({
          status: tab.status,
          websocketId: tab.websocketId,
          subscriptionIds: taskSubscriptionIds(tab),
          hasSubscription: taskSubscriptionIds(tab).length > 0,
        })}`
      )
    })
    logger.info(`WebSocket状态: ${JSON.stringify(ws.status.value)}`)
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

    // 注意：由于keep-alive机制，路由切换时组件不会卸载
    // cleanup只在组件真正销毁时才会调用（如应用关闭）
    // 所以这里清理所有订阅，包括运行中的任务
    logger.info('清理所有WebSocket订阅')
    schedulerTabs.value.forEach(tab => {
      if (taskSubscriptionIds(tab).length > 0) {
        logger.info(
          `清理订阅: ${JSON.stringify({
            key: tab.key,
            status: tab.status,
            subscriptionIds: taskSubscriptionIds(tab),
          })}`
        )
        unsubscribeTab(tab)
      }
    })

    saveTabsToStorageNow(schedulerTabs.value)
  }

  return {
    // 状态
    schedulerTabs,
    activeSchedulerTab,
    logRefs,
    // 将“运行/运行中”的用户标记为“等待”，并据此推导脚本状态

    taskOptionsLoading,
    taskOptions,
    messageModalVisible,
    currentMessage,
    messageResponse,

    // 计算属性
    currentTab,

    // Tab 管理
    addSchedulerTab,
    removeSchedulerTab,
    removeAllNonRunningTabs,

    // 任务操作
    startTask,
    stopTask,
    handleTaskSelectionChange,
    loadResumeScriptOptions,

    // 日志操作
    onLogScroll,
    setLogRef,

    // 消息操作
    sendMessageResponse,
    cancelMessage,

    // 初始化与清理
    initialize,
    loadTaskOptions,
    cleanup,

    // 任务总览面板引用管理
    setOverviewRef,

    // 调试功能
    debugSubscriptionStatus,

    // 调度器连接状态
    schedulerConnectionState,
    isSchedulerConnected,
  }
}
