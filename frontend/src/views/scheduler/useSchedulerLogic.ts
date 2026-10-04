import { translate as t } from '@/i18n'
import { h, ref, watch } from 'vue'
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
import { type SchedulerTab, type SchedulerStatus, TASK_MODE_OPTIONS } from './schedulerConstants'
import { applyTaskLogUpdate, trimLogBuffer } from './schedulerLogBuffer'
import { findReusableSchedulerTab } from './schedulerTabReuse'
import { reconcileSelectedUserIds, toRunnableUserOptions } from './schedulerUserOptions'
import {
  countQueueSelectedUsers,
  countQueueUsers,
  isRunnableQueueScriptId,
  reconcileQueueScope,
  toQueueUserIds,
  type QueueScopeGroup,
  type QueueUserScope,
} from './schedulerQueueScope'
import { buildStartTaskRequest } from './schedulerStartRequest'
import { resolveTaskCompletionFeedback } from '@/utils/taskFailures'

/** sessionStorage 里的勾选只当字符串数组用，坏数据直接忽略。 */
const normalizePersistedQueueScope = (value: unknown): QueueUserScope => {
  if (!value || typeof value !== 'object') return {}
  const scope: QueueUserScope = {}
  Object.entries(value as Record<string, unknown>).forEach(([scriptId, ids]) => {
    if (Array.isArray(ids)) {
      scope[scriptId] = ids.filter((id): id is string => typeof id === 'string')
    }
  })
  return scope
}

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
// 同一标签页可能连续刷新用户列表；旧请求不得覆盖较新的选择和加载状态。
const latestUserOptionsRequest = new WeakMap<SchedulerTab, object>()
// 队列运行范围同理：连续刷新时只有最新一次请求可以写回托管与勾选
const latestQueueScopeRequest = new WeakMap<SchedulerTab, object>()
const latestResumeOptionsRequest = new WeakMap<SchedulerTab, object>()
// 序号断裂后正在等快照重建 buffer 的标签页，期间到达的增量直接丢弃、不重复拉快照
const pendingLogResyncs = new Set<string>()
// 手动启动还在等 /dispatch/start 返回的标签页：同队列的定时任务此时复用它的话，
// 返回后会被手动任务的 taskId 覆盖，定时任务就没有调度台可显示了
const startingTabKeys = new Set<string>()
// keep-alive 停用期间只更新 buffer，不往日志面板写；激活时一次性刷新
let schedulerViewActive = true
// 是否离开过调度台；用于区分「首次激活」与「切走再切回」
let schedulerViewLeft = false
// MaaEnd 失败导出弹窗全局去重，避免同一批错误连环弹窗
let maaEndFailureModalOpen = false

const getDefaultTabRuntimeState = () => ({
  logBuffer: '',
  logSeq: undefined,
  logFirstLine: 1,
  displayLogFirstLine: 1,
  lastLogContent: '',
  overviewData: undefined,
  lastMessageHash: '',
  lastMessageTime: 0,
  cycleNextList: [],
})

const trimLogForRender = (content: string, firstLine: number) => {
  if (content.length <= LOG_RENDER_MAX_CHARS) return { content, firstLine }

  const dropped = content.slice(0, content.length - LOG_RENDER_MAX_CHARS)
  const trimmed = content.slice(-LOG_RENDER_MAX_CHARS)
  const firstLineBreak = trimmed.indexOf('\n')
  const tail = firstLineBreak >= 0 ? trimmed.slice(firstLineBreak + 1) : trimmed
  return {
    content: `${t('scheduler.log.truncated')}\n\n${tail}`,
    firstLine: firstLine + dropped.split('\n').length - 1 + (firstLineBreak >= 0 ? 1 : 0) - 2,
  }
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
  selectedUserIds: tab.selectedUserIds ? [...tab.selectedUserIds] : undefined,
  // 刷新后要恢复队列任务的勾选，否则界面上显示的默认全选会和用户上次的选择不一致
  queueUserScope: { ...(tab.queueUserScope || {}) },
  userOptions: tab.userOptions ? [...tab.userOptions] : [],
  userOptionsLoading: false,
  userOptionsLoaded: false,
  taskId: tab.taskId,
  subscriptionIds: [],
  runningTaskLabel: tab.runningTaskLabel,
  runningModeLabel: tab.runningModeLabel,
  logMode: tab.logMode || 'follow',
  // 不存这个的话，刷新后模式选项里没有「循环运行」，已选的循环模式会被静默改回自动代理
  isCycleQueue: tab.isCycleQueue ?? false,
  ...getDefaultTabRuntimeState(),
})

const normalizePersistedTab = (
  tab: SchedulerTab & { selectedUserId?: string | null }
): SchedulerTab => ({
  ...tab,
  ...getDefaultTabRuntimeState(),
  resumeScriptOptions: tab.resumeScriptOptions || [],
  resumeScriptLoading: false,
  selectedUserIds: Array.isArray(tab.selectedUserIds)
    ? [...tab.selectedUserIds]
    : tab.selectedUserId
      ? [tab.selectedUserId]
      : undefined,
  userOptions: tab.userOptions || [],
  userOptionsLoading: false,
  userOptionsLoaded: false,
  queueUserScope: normalizePersistedQueueScope(tab.queueUserScope),
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
      selectedUserIds: undefined,
      userOptions: [],
      userOptionsLoading: false,
      userOptionsLoaded: false,
      taskId: null,
      logBuffer: '',
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

    // 同一队列 / 脚本上次用过的调度台空着就接着用，没有才新建
    const reusedTab = reuseSchedulerTab(taskId, queueId)
    const newTab =
      reusedTab ??
      addSchedulerTab({
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

    if (reusedTab) {
      logger.info(`已复用自动调度台: ${newTab.title}, 任务ID=${taskId}`)
      if (notifyUser) message.success(t('scheduler.toast.tabReused', { title: newTab.title }))
    } else {
      logger.info(`已创建新的自动调度台: ${newTab.title}, 任务ID=${taskId}`)
      if (notifyUser) message.success(t('scheduler.toast.tabAutoCreated', { title: newTab.title }))
    }

    saveTabsToStorage(schedulerTabs.value)
    return newTab
  }

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
      selectedUserIds: undefined,
      userOptions: [],
      userOptionsLoading: false,
      userOptionsLoaded: false,
      taskId: options?.taskId || null,
      logBuffer: '',
      lastLogContent: '',
    }
    schedulerTabs.value.push(tab)
    activeSchedulerTab.value = tab.key

    return tab
  }

  // 把新任务挂到可复用的调度台上（判据见 findReusableSchedulerTab），先清掉上一轮的日志与总览；
  // 没有可复用的返回 undefined，由调用方新建
  const reuseSchedulerTab = (taskId: string, selectedTaskId?: string) => {
    const tab = findReusableSchedulerTab(schedulerTabs.value, selectedTaskId, startingTabKeys)
    if (!tab) return undefined

    unsubscribeTab(tab)
    clearPendingLogUpdate(tab.key)
    pendingLogResyncs.delete(tab.key)
    tab.status = '运行'
    tab.taskId = taskId
    tab.logBuffer = ''
    tab.logSeq = undefined
    tab.logFirstLine = 1
    tab.displayLogFirstLine = 1
    tab.lastLogContent = ''
    tab.overviewData = undefined
    tab.cycleNextList = []
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

    const tab =
      reuseSchedulerTab(taskId, selectedTaskId) ??
      addSchedulerTab({
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

  /**
   * 队列项 → 去重后的托管列表，顺序与队列一致。
   * code 非 200 返回 null，由调用方决定是静默清空还是提示用户。
   */
  const fetchQueueScripts = async (
    queueId: string
  ): Promise<Array<{ scriptId: string; scriptName: string }> | null> => {
    await loadScriptLabelMap()
    const response = await Service.getItemApiQueueItemGetPost({ queueId })
    if (response.code !== 200) return null

    const scripts: Array<{ scriptId: string; scriptName: string }> = []
    const scriptSeen = new Set<string>()
    response.index.forEach(item => {
      const scriptId = response.data?.[item.uid]?.Info?.ScriptId
      // 未指定脚本（或脚本已失效）的队列项占位值是 "-"，后端同样跳过这类项
      if (!isRunnableQueueScriptId(scriptId) || scriptSeen.has(scriptId)) return
      scriptSeen.add(scriptId)
      scripts.push({
        scriptId,
        scriptName: scriptOptionsMap.value[scriptId] || scriptId,
      })
    })
    return scripts
  }

  const loadResumeScriptOptions = async (tab: SchedulerTab) => {
    if (!tab.selectedTaskId || !isQueueTask(tab)) {
      // 作废在途请求，并在这里收掉 loading：被作废的请求不会再去清它
      latestResumeOptionsRequest.delete(tab)
      tab.resumeScriptOptions = []
      tab.resumeFromScriptId = null
      tab.resumeScriptLoading = false
      return
    }

    latestResumeOptionsRequest.delete(tab)

    const requestedTaskId = tab.selectedTaskId
    const request = {}
    latestResumeOptionsRequest.set(tab, request)
    const isStale = () =>
      tab.selectedTaskId !== requestedTaskId || latestResumeOptionsRequest.get(tab) !== request

    tab.resumeScriptLoading = true
    try {
      const scripts = await fetchQueueScripts(requestedTaskId)
      if (isStale()) return
      if (scripts === null) {
        tab.resumeScriptOptions = []
        tab.resumeFromScriptId = null
        return
      }

      const options = scripts.map(script => ({ value: script.scriptId, label: script.scriptName }))
      tab.resumeScriptOptions = options
      if (tab.resumeFromScriptId && !options.some(item => item.value === tab.resumeFromScriptId)) {
        tab.resumeFromScriptId = null
      }
    } catch (error) {
      if (isStale()) return
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`加载恢复脚本列表失败: ${errorMsg}`)
      tab.resumeScriptOptions = []
      tab.resumeFromScriptId = null
      message.error(t('scheduler.toast.loadQueueScriptsFailed'))
    } finally {
      if (!isStale()) {
        tab.resumeScriptLoading = false
      }
    }
  }

  /**
   * 队列任务：拉取每个托管本次可运行的账号，供「本次运行范围」面板勾选。
   *
   * 加载失败必须显式暴露（queueScopeFailed），否则想取消某个账号的用户会以为已经
   * 排除了它，实际却按全量跑，所以启动按钮会拦住这种情况并让用户重试。
   */
  const loadQueueScope = async (tab: SchedulerTab) => {
    // 任务下拉还没加载完时判断不出任务类型，等选项可用后再刷新。
    if (!taskOptions.value.length) return

    if (!tab.selectedTaskId || !isQueueTask(tab)) {
      latestQueueScopeRequest.delete(tab)
      tab.queueScopeGroups = []
      tab.queueUserScope = {}
      tab.queueScopeLoading = false
      tab.queueScopeFailed = false
      return
    }

    const requestedTaskId = tab.selectedTaskId
    const request = {}
    latestQueueScopeRequest.set(tab, request)
    const isStale = () =>
      tab.selectedTaskId !== requestedTaskId || latestQueueScopeRequest.get(tab) !== request

    tab.queueScopeLoading = true
    tab.queueScopeFailed = false
    try {
      const scripts = await fetchQueueScripts(requestedTaskId)
      if (isStale()) return
      if (scripts === null) {
        tab.queueScopeGroups = []
        tab.queueScopeFailed = true
        return
      }

      const groups: QueueScopeGroup[] = []
      for (const script of scripts) {
        const response = await Service.getUserApiScriptsUserGetPost({
          scriptId: script.scriptId,
          userId: null,
        })
        if (isStale()) return
        if (response.code !== 200) {
          // 已经拿到的托管先留着，重试成功后会被整体替换
          tab.queueScopeGroups = groups
          tab.queueScopeFailed = true
          return
        }
        groups.push({
          scriptId: script.scriptId,
          scriptName: script.scriptName,
          users: toRunnableUserOptions(response),
        })
      }

      tab.queueScopeGroups = groups
      tab.queueUserScope = reconcileQueueScope(tab.queueUserScope || {}, groups)
    } catch (error) {
      if (isStale()) return
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`加载队列运行范围失败: ${errorMsg}`)
      tab.queueScopeGroups = []
      tab.queueScopeFailed = true
    } finally {
      if (!isStale()) {
        tab.queueScopeLoading = false
      }
    }
  }

  // 列表用于展示与校正显式子集；全选始终由后端执行时筛选可运行用户。
  const loadUserOptions = async (tab: SchedulerTab) => {
    // 任务下拉还没加载完时判断不出任务类型，此时保留当前选择，等选项可用后再刷新。
    if (!taskOptions.value.length) return

    if (!tab.selectedTaskId || !isScriptTask(tab)) {
      latestUserOptionsRequest.delete(tab)
      tab.userOptions = []
      tab.selectedUserIds = undefined
      tab.userOptionsLoading = false
      tab.userOptionsLoaded = false
      return
    }

    // 切换任务或重复刷新时，仅最新请求可以写回用户列表与选择。
    const requestedTaskId = tab.selectedTaskId
    const request = {}
    latestUserOptionsRequest.set(tab, request)
    const isStale = () =>
      tab.selectedTaskId !== requestedTaskId || latestUserOptionsRequest.get(tab) !== request

    tab.userOptionsLoading = true
    tab.userOptionsLoaded = false
    try {
      const response = await Service.getUserApiScriptsUserGetPost({
        scriptId: requestedTaskId,
        userId: null,
      })
      if (isStale()) return
      if (response.code !== 200) {
        message.error(t('scheduler.toast.loadScriptUsersFailed'))
        return
      }

      const options = toRunnableUserOptions(response)
      tab.userOptions = options
      tab.selectedUserIds = reconcileSelectedUserIds(tab.selectedUserIds, options)
      tab.userOptionsLoaded = true
    } catch (error) {
      if (isStale()) return
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`加载脚本用户列表失败: ${errorMsg}`)
      message.error(t('scheduler.toast.loadScriptUsersFailed'))
    } finally {
      if (!isStale()) {
        tab.userOptionsLoading = false
      }
    }
  }

  const handleTaskSelectionChange = async (tab: SchedulerTab, taskId: string | null) => {
    tab.selectedTaskId = taskId
    tab.resumeFromScriptId = null
    tab.selectedUserIds = undefined
    tab.userOptions = []
    tab.userOptionsLoaded = false
    // 换了任务就重新开始选，上一个队列的勾选不能带到新队列上
    tab.queueUserScope = {}
    tab.queueScopeGroups = []
    tab.queueScopeFailed = false
    await Promise.all([
      loadResumeScriptOptions(tab),
      loadUserOptions(tab),
      loadQueueScope(tab),
      loadCycleQueueFlag(tab),
    ])
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
        response.code === 200 && Boolean(response.data?.[tab.selectedTaskId]?.Info?.CycleEnabled)
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

    if (!taskOptions.value.some(option => option.value === tab.selectedTaskId)) {
      message.error(t('scheduler.toast.taskOptionsUnavailable'))
      return
    }

    if (
      tab.selectedMode === TaskCreateIn.mode.AUTO_PROXY &&
      isScriptTask(tab) &&
      tab.selectedUserIds !== undefined
    ) {
      if (!tab.userOptionsLoaded || tab.userOptionsLoading) {
        message.error(t('scheduler.toast.loadScriptUsersFailed'))
        return
      }
      if (!tab.selectedUserIds.length) {
        message.error(t('scheduler.toast.needRunUsers'))
        return
      }
    }

    if (isQueueTask(tab)) {
      if (tab.queueScopeLoading) {
        message.error(t('scheduler.toast.loadQueueRunUsersFailed'))
        return
      }
      if (tab.queueScopeFailed) {
        message.error(t('scheduler.control.runScopeLoadFailed'))
        return
      }
      const scopeGroups = tab.queueScopeGroups || []
      // 与启动按钮同口径：有可勾选账号却一个都没勾才拦住；队列里本来就没有可运行账号时，
      // 保持本 PR 之前的启动行为（交给各脚本自己报无用户）。
      if (
        countQueueUsers(scopeGroups) > 0 &&
        countQueueSelectedUsers(tab.queueUserScope || {}, scopeGroups) === 0
      ) {
        message.error(t('scheduler.toast.needQueueRunUsers'))
        return
      }
    }

    startingTabKeys.add(tab.key)
    try {
      const requestBody = buildStartTaskRequest(
        tab.selectedTaskId,
        tab.selectedMode,
        tab.resumeFromScriptId,
        isScriptTask(tab) ? tab.selectedUserIds : undefined,
        isQueueTask(tab)
          ? toQueueUserIds(tab.queueUserScope || {}, tab.queueScopeGroups || [])
          : undefined
      )

      const response = await Service.addTaskApiDispatchStartPost(requestBody)

      if (response.code === 200) {
        tab.status = '运行'
        tab.taskId = response.taskId

        // 确保清理任何可能存在的旧订阅
        unsubscribeTab(tab)

        // 清空之前的状态
        tab.logBuffer = ''
        tab.logSeq = undefined
        tab.logFirstLine = 1
        tab.displayLogFirstLine = 1
        pendingLogResyncs.delete(tab.key)
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
    } finally {
      startingTabKeys.delete(tab.key)
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
    const rendered = trimLogForRender(content, tab.logFirstLine ?? 1)
    tab.displayLogFirstLine = rendered.firstLine
    if (tab.lastLogContent !== rendered.content) {
      tab.lastLogContent = rendered.content
    }
  }

  const scheduleLogContentUpdate = (tab: SchedulerTab, content: string, immediate = false) => {
    pendingLogContents.set(tab.key, content)

    // 页面停用期间只攒着，激活时由 setSchedulerViewActive 一次性写入
    if (!schedulerViewActive) return

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

  // keep-alive 激活/停用：停用时不再驱动 Monaco 写入，激活时把攒下的内容一次性刷出
  const setSchedulerViewActive = (active: boolean) => {
    schedulerViewActive = active
    if (!active) {
      schedulerViewLeft = true
      return
    }
    for (const tab of schedulerTabs.value) {
      const content = pendingLogContents.get(tab.key)
      if (content !== undefined) {
        clearPendingLogUpdate(tab.key)
        applyLogContentUpdate(tab, content)
      }

      // 停在调度台以外时可能在队列配置页或托管管理里改了队列项/账号，回到调度台重新拉一次，
      // 否则旧列表会让「勾选=本次运行」失真（新加的账号默认不在运行范围内）。
      // 首次激活不重复拉：initialize 的预加载已经做过一次。
      if (schedulerViewLeft && tab.status !== '运行') {
        if (isQueueTask(tab)) {
          void loadResumeScriptOptions(tab)
          void loadQueueScope(tab)
        } else if (isScriptTask(tab)) {
          // 「本次运行范围」是脚本任务唯一的账号入口，不重拉就看不到已删账号
          void loadUserOptions(tab)
        }
      }
    }
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
    return true
  }

  // 序号对不上（没有基线或漏了消息）：丢掉本条，拉一次快照重建 buffer；
  // 等待期间到达的增量也丢，快照到达后由 applyRuntimeTaskSnapshot 重置 seq
  const requestLogResync = (tab: SchedulerTab, data: WSTaskLogUpdatedData) => {
    if (pendingLogResyncs.has(tab.key)) return
    pendingLogResyncs.add(tab.key)
    logger.info(`日志序号不连续，重拉运行快照: key=${tab.key}, seq=${data.seq}`)
    void refreshTaskRuntimeSnapshot().finally(() => pendingLogResyncs.delete(tab.key))
  }

  // 增量协议：append=false 整体替换；append=true 且 seq 连续则追加，否则重同步
  const handleTaskLogUpdated = (tab: SchedulerTab, data: WSTaskLogUpdatedData) => {
    if (typeof data.log !== 'string') return
    const result = applyTaskLogUpdate(tab, data)
    if (result === 'resync') {
      requestLogResync(tab, data)
      return
    }
    if (result === 'replace') pendingLogResyncs.delete(tab.key)
    scheduleLogContentUpdate(tab, tab.logBuffer)
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
      tab.logFirstLine = 1
      scheduleLogContentUpdate(tab, resultText, true)
      logger.info('已清空日志并显示任务结果')
    }

    // 切换日志模式为自由浏览
    tab.logMode = 'browse'
    logger.info('已切换日志模式为自由浏览')

    // outcome 只反映任务级错误：用户 / 脚本跑失败时后端仍报 success，这里再看 task_info
    const feedback = resolveTaskCompletionFeedback(data)

    // 使用Vue的响应式更新方式
    tab.status = feedback.kind === 'error' || feedback.kind === 'partialFailure' ? '异常' : '结束'
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
      // 刷新数组中的响应式对象，让外部启动或恢复的脚本也能直接再次运行。
      const currentTab = schedulerTabs.value[tabIndex]
      if (isScriptTask(currentTab)) {
        void loadUserOptions(currentTab)
      } else if (isQueueTask(currentTab)) {
        // 队列任务结束（含页面在运行中被重载的情形）后重拉一次运行范围：
        // groups 不持久化，不重拉就看不到账号，用户上次取消勾选的账号会被静默按全量跑
        void loadQueueScope(currentTab)
      }
    }

    const { playSound } = useAudioPlayer()
    if (feedback.kind === 'error') {
      await playSound('error_occurred')
      message.error(data.error || t('scheduler.toast.taskRunFailed'))
    } else if (feedback.kind === 'cancelled') {
      message.warning(t('scheduler.toast.taskCancelled'))
    } else if (feedback.kind === 'partialFailure') {
      await playSound('error_occurred')
      const { users, scripts } = feedback.failures
      message.warning(
        users > 0
          ? t('scheduler.toast.taskDoneWithFailedUsers', { count: users })
          : t('scheduler.toast.taskDoneWithFailedScripts', { count: scripts })
      )
    } else {
      await playSound('task_completed')
      message.success(t('scheduler.toast.taskDone'))
    }
    saveTabsToStorage(schedulerTabs.value)

    // 触发Vue的响应式更新
    schedulerTabs.value = [...schedulerTabs.value]
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
    // 这里只同步状态，不订阅：任务运行期每秒都会推送状态，在这里调用 subscribeToTask
    // 只会每次都命中「订阅已存在」分支刷日志。订阅由建台、启动与恢复路径
    // （createSchedulerTabForTask、trackStartedTask、startTask、initialize）负责。
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
    // 快照里的 log 是上次推送的完整日志尾部，直接作为 buffer 基线，与下一条增量衔接
    tab.logBuffer = trimLogBuffer(state.log ?? '')
    tab.logSeq = state.logSeq
    tab.logFirstLine = state.logFirstLine ?? 1
    pendingLogResyncs.delete(tab.key)
    if (tab.logBuffer || tab.lastLogContent) scheduleLogContentUpdate(tab, tab.logBuffer, true)
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
    // 完成消息缺失时，快照确认结束也要准备下一轮的用户选择。
    if (isScriptTask(tab)) {
      void loadUserOptions(tab)
    } else if (isQueueTask(tab)) {
      // 跑完一轮后账号可能已经不可运行，重新拉一次让面板显示真实可选范围
      void loadQueueScope(tab)
    }
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
  const initialize = async () => {
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

    // 为已有调度台预加载恢复脚本 / 用户选项，确保刷新后恢复交互可用。
    // isQueueTask / isScriptTask 靠任务选项判断类型，所以要先把选项拉回来
    await loadTaskOptions()
    schedulerTabs.value.forEach(tab => {
      if (tab.status === '运行') return
      if (isQueueTask(tab)) {
        loadResumeScriptOptions(tab)
        loadQueueScope(tab)
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
    pendingLogResyncs.clear()
    schedulerViewActive = true

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
    taskOptionsLoading,
    taskOptions,
    powerAction,

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
    loadQueueScope,

    // keep-alive 激活/停用
    setSchedulerViewActive,

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
