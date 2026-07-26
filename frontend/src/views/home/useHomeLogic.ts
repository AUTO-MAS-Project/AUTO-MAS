import { computed, onMounted, ref, watch } from 'vue'
import dayjs from 'dayjs'
import { message } from 'ant-design-vue'
import { Service } from '@/api/services/Service'
import { TaskCreateIn } from '@/api/models/TaskCreateIn'
import { HistorySearchIn } from '@/api/models/HistorySearchIn'
import type { ComboBoxItem, HistoryData } from '@/api'
import { useAudioPlayer } from '@/composables/useAudioPlayer'
import { useAppInitialization } from '@/composables/useAppInitialization'
import { useWebSocket } from '@/composables/useWebSocket'
import { formatBackendDateTime } from '@/utils/dateDisplay'

const logger = window.electronAPI.getLogger('首页')

export interface ProxyInfo {
  LastProxyDate: string
  ProxyTimes: number
  ErrorTimes: number
  ErrorInfo: Record<string, any>
}

export interface HomeQueueSummary {
  queueCount: number
  enabledQueueCount: number
  itemCount: number
}

export interface HomeRecentRecord {
  date: string
  username: string
  record: {
    date: string
    jsonFile: string
    status: string
  }
}

export interface HomeTaskOption extends ComboBoxItem {
  value: string
  title: string
}

export interface HomeTaskModeOption {
  label: string
  value: TaskCreateIn.mode
}

export const homeTaskModeOptions: readonly HomeTaskModeOption[] = [
  { label: '自动代理', value: TaskCreateIn.mode.AUTO_PROXY },
  { label: '人工排查', value: TaskCreateIn.mode.MANUAL_REVIEW },
  { label: '配置脚本', value: TaskCreateIn.mode.SCRIPT_CONFIG },
  { label: '循环运行', value: TaskCreateIn.mode.CYCLE_RUN },
]

export const normalizeHomeTaskOptions = (options: readonly ComboBoxItem[]): HomeTaskOption[] =>
  options
    .filter(
      (option): option is ComboBoxItem & { value: string } =>
        typeof option.value === 'string' &&
        option.value.trim().length > 0 &&
        (option.supported_modes == null || option.supported_modes.length > 0)
    )
    .map(option => ({
      ...option,
      value: option.value.trim(),
      title: option.label,
    }))

export type HomeModuleKey = 'status' | 'command' | 'recent' | 'queue' | 'satellite' | 'proxy'
export type HomeModuleDirection = 'up' | 'down'

interface HomeLayoutConfig {
  moduleOrder: HomeModuleKey[]
  hiddenModules: HomeModuleKey[]
}

const HOME_LAYOUT_STORAGE_KEY = 'auto-mas.home.layout'

// 默认顺序即视觉顺序：DOM 顺序驱动网格布局（不再依赖 CSS order），
// 真机反馈的默认布局：快速开始（置顶）→ 队列概览 → 最近活动(span 4)+卫星(span 8) 并排 → 其余。
// recent 必须紧邻 satellite 且在其前，二者 4+8=12 列才能稳定并排成一行。
// 原 'quick'（常用入口）模块已上移到页头工具行。
export const defaultHomeModuleOrder: HomeModuleKey[] = [
  'command',
  'queue',
  'recent',
  'satellite',
  'status',
  'proxy',
]

export const moduleTitleMap: Record<HomeModuleKey, string> = {
  status: '运行状态',
  command: '快速开始',
  recent: '最近活动',
  queue: '队列概览',
  satellite: '卫星环绕',
  proxy: '代理状态',
}

export const homeCommandMessages = [
  '坐和放宽，脚本正在为你努力运行中。',
  '启动前请确认脚本路径已正确，否则它将无法找到自己。',
  '请勿™强制关闭AUTO-MAS，正在处理一些事情。',
  '好东西就要来了……别来无恙啊！',
  'AUTO-MAS正在为你的设备匹配专属脚本设置。',
  '启动AUTO-MAS脚本系统，不要说我们没有警告过你。',
  '需要重启脚本是正常现象，请不要惊慌。',
  '你的设备正在准备就绪，准备好迎接脚本运行了吗？',
  '运行完成后，你的游戏进度可能会发生位移。',
  '我们的脚本协议更新了，你只能同意不能不同意。',
  '请耐心等待，进度条只是看起来不动而已。',
  '感谢你使用AUTO-MAS，你永远可以相信脚本的力量。',
  '正在应用最适合当前宇宙版本的脚本设置。',
  '你的请求很重要，AUTO-MAS正在以看似安静的方式处理它。',
  'AUTO-MAS检测到一切正常，除非稍后它不正常。',
  '请稍候，系统正在把复杂问题包装成一个按钮。',
] as const

export const pickHomeCommandMessage = (random: () => number = Math.random): string => {
  const index = Math.floor(random() * homeCommandMessages.length)
  return homeCommandMessages[index] ?? homeCommandMessages[0]
}

const isHomeModuleKey = (value: unknown): value is HomeModuleKey => {
  return typeof value === 'string' && defaultHomeModuleOrder.includes(value as HomeModuleKey)
}

/**
 * 归一化持久化的模块顺序。
 * 旧布局迁移策略：仅当 localStorage 无持久化记录时才使用新默认顺序
 * （loadHomeLayoutConfig 不会在无记录时调用本函数）；已自定义的顺序原样保留，
 * 本函数只过滤非法键、去重，并把缺失模块按新默认顺序补到末尾，command 恒置顶。
 */
export const normalizeHomeModuleOrder = (order: unknown): HomeModuleKey[] => {
  const configuredOrder = Array.isArray(order) ? order.filter(isHomeModuleKey) : []
  const uniqueOrder = configuredOrder.filter((key, index, array) => array.indexOf(key) === index)
  const missingOrder = defaultHomeModuleOrder.filter(key => !uniqueOrder.includes(key))
  const normalizedOrder = [...uniqueOrder, ...missingOrder].filter(key => key !== 'command')
  return ['command', ...normalizedOrder]
}

const normalizeHomeHiddenModules = (hiddenModules: unknown): HomeModuleKey[] => {
  const configuredHiddenModules = Array.isArray(hiddenModules)
    ? hiddenModules.filter(isHomeModuleKey)
    : []
  return configuredHiddenModules.filter((key, index, array) => array.indexOf(key) === index)
}

export function useHomeLogic() {
  const { isBootstrapping } = useAppInitialization()
  const { playSound } = useAudioPlayer()
  const { status: wsStatus, backendStatus } = useWebSocket()

  const loading = ref(false)
  const homeDataError = ref<string | null>(null)
  const schedulerTasksLoading = ref(false)
  const startingHomeTask = ref(false)
  const homeTaskStartError = ref<string | null>(null)
  const layoutEditing = ref(false)

  const homeModuleOrder = ref<HomeModuleKey[]>([...defaultHomeModuleOrder])
  const hiddenHomeModules = ref<HomeModuleKey[]>(['proxy'])

  const proxyData = ref<Record<string, ProxyInfo>>({})
  const queueSummary = ref<HomeQueueSummary | null>(null)
  const recentRecords = ref<HomeRecentRecord[]>([])

  const schedulerTaskOptions = ref<HomeTaskOption[]>([])
  const selectedHomeTaskId = ref<string | null>(null)
  const selectedHomeMode = ref<TaskCreateIn.mode>(TaskCreateIn.mode.AUTO_PROXY)
  const schedulerTasksError = ref<string | null>(null)

  const noticeVisible = ref(false)
  const noticeData = ref<Record<string, string>>({})
  const noticeLoading = ref(false)
  const commandTitle = ref(pickHomeCommandMessage())

  const selectedHomeTaskOption = computed(() =>
    schedulerTaskOptions.value.find(option => option.value === selectedHomeTaskId.value)
  )
  const schedulerModeOptions = computed<HomeTaskModeOption[]>(() => {
    const supportedModes = selectedHomeTaskOption.value?.supported_modes
    if (supportedModes == null) {
      return [...homeTaskModeOptions]
    }
    return homeTaskModeOptions.filter(option => supportedModes.includes(option.value))
  })

  const greeting = computed(() => {
    const hour = new Date().getHours()
    if (hour >= 5 && hour < 11) return '早上好！欢迎使用 AUTO-MAS'
    if (hour >= 11 && hour < 14) return '中午好！欢迎使用 AUTO-MAS'
    if (hour >= 14 && hour < 18) return '下午好！欢迎使用 AUTO-MAS'
    if (hour >= 18 && hour < 23) return '晚上好！欢迎使用 AUTO-MAS'
    return '夜深了，欢迎使用 AUTO-MAS'
  })

  const statusSummary = computed(() => {
    const ws = wsStatus.value
    const backend = backendStatus.value
    const hasErrors = Object.values(proxyData.value).some(p => p.ErrorTimes > 0)
    return {
      ws,
      backend,
      hasErrors,
      isReady: ws === '已连接' && backend === 'running',
    }
  })

  const loadHomeLayoutConfig = () => {
    try {
      const rawConfig = localStorage.getItem(HOME_LAYOUT_STORAGE_KEY)
      if (rawConfig) {
        const config = JSON.parse(rawConfig) as Partial<HomeLayoutConfig>
        homeModuleOrder.value = normalizeHomeModuleOrder(config.moduleOrder)
        hiddenHomeModules.value = normalizeHomeHiddenModules(config.hiddenModules)
      }
    } catch (error) {
      logger.warn(`读取首页布局配置失败: ${error instanceof Error ? error.message : String(error)}`)
    }
  }

  const persistHomeLayoutConfig = () => {
    try {
      const config: HomeLayoutConfig = {
        moduleOrder: homeModuleOrder.value,
        hiddenModules: hiddenHomeModules.value,
      }
      localStorage.setItem(HOME_LAYOUT_STORAGE_KEY, JSON.stringify(config))
    } catch (error) {
      logger.warn(`保存首页布局配置失败: ${error instanceof Error ? error.message : String(error)}`)
    }
  }

  const toggleLayoutEditing = () => {
    layoutEditing.value = !layoutEditing.value
  }

  const canMoveHomeModule = (key: HomeModuleKey, direction: HomeModuleDirection) => {
    const currentIndex = homeModuleOrder.value.indexOf(key)
    if (currentIndex < 0) return false
    if (key === 'command') return false
    return direction === 'up' ? currentIndex > 1 : currentIndex < homeModuleOrder.value.length - 1
  }

  const moveHomeModule = (key: HomeModuleKey, direction: HomeModuleDirection) => {
    if (!canMoveHomeModule(key, direction)) return
    const currentIndex = homeModuleOrder.value.indexOf(key)
    const targetIndex = direction === 'up' ? currentIndex - 1 : currentIndex + 1
    const nextOrder = [...homeModuleOrder.value]
    const currentModule = nextOrder[currentIndex]
    const targetModule = nextOrder[targetIndex]
    if (!currentModule || !targetModule) return
    nextOrder[currentIndex] = targetModule
    nextOrder[targetIndex] = currentModule
    homeModuleOrder.value = nextOrder
    persistHomeLayoutConfig()
  }

  /**
   * 供拖拽排序（vuedraggable）读写的模块列表。
   * command 固定置顶、不参与拖拽，因此 getter 排除它；
   * setter 写回时统一走 normalizeHomeModuleOrder 强制 command 置顶并持久化。
   */
  const reorderableHomeModules = computed<HomeModuleKey[]>({
    get: () => homeModuleOrder.value.filter(key => key !== 'command'),
    set: value => {
      homeModuleOrder.value = normalizeHomeModuleOrder(['command', ...value])
      persistHomeLayoutConfig()
    },
  })

  const isHomeModuleShown = (key: HomeModuleKey) => !hiddenHomeModules.value.includes(key)

  const setHomeModuleShown = (key: HomeModuleKey, checked: boolean | string | number) => {
    const shouldShow = Boolean(checked)
    if (shouldShow) {
      hiddenHomeModules.value = hiddenHomeModules.value.filter(hiddenKey => hiddenKey !== key)
    } else if (!hiddenHomeModules.value.includes(key)) {
      hiddenHomeModules.value = [...hiddenHomeModules.value, key]
    }
    persistHomeLayoutConfig()
  }

  const isHomeModuleVisible = (key: HomeModuleKey) => layoutEditing.value || isHomeModuleShown(key)

  const fetchSchedulerTaskOptions = async (options?: { quiet?: boolean }): Promise<boolean> => {
    schedulerTasksLoading.value = true
    schedulerTasksError.value = null
    try {
      const response = await Service.getTaskComboxApiInfoComboxTaskPost()
      const usableOptions =
        response.code === 200 ? normalizeHomeTaskOptions(response.data ?? []) : []
      if (usableOptions.length > 0) {
        schedulerTaskOptions.value = usableOptions
        if (
          !selectedHomeTaskId.value ||
          !usableOptions.some(item => item.value === selectedHomeTaskId.value)
        ) {
          selectedHomeTaskId.value = usableOptions[0]?.value ?? null
        }
        return true
      }
      schedulerTaskOptions.value = []
      selectedHomeTaskId.value = null
      schedulerTasksError.value =
        response.code === 200 ? '暂无可运行任务' : response.message || '任务列表加载失败'
      if (!options?.quiet) {
        message.warning(schedulerTasksError.value)
      }
      return response.code === 200
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error)
      logger.warn(`获取首页任务列表失败: ${msg}`)
      schedulerTaskOptions.value = []
      selectedHomeTaskId.value = null
      schedulerTasksError.value = msg
      if (!options?.quiet) {
        message.warning('任务列表加载失败')
      }
      return false
    } finally {
      schedulerTasksLoading.value = false
    }
  }

  const onSchedulerDropdownVisibleChange = (open: boolean) => {
    if (open) {
      void fetchSchedulerTaskOptions({ quiet: true })
    }
  }

  const startHomeTask = async (): Promise<boolean> => {
    if (startingHomeTask.value) {
      return false
    }
    if (!selectedHomeTaskId.value) {
      message.error('请选择任务项')
      return false
    }
    const selectedTask = selectedHomeTaskOption.value
    if (!selectedTask) {
      message.error('所选任务已失效，请重新选择')
      return false
    }
    if (!schedulerModeOptions.value.some(option => option.value === selectedHomeMode.value)) {
      message.error('所选任务不支持当前运行模式')
      return false
    }
    homeTaskStartError.value = null
    startingHomeTask.value = true
    try {
      const response = await Service.addTaskApiDispatchStartPost({
        taskId: selectedHomeTaskId.value,
        mode: selectedHomeMode.value,
      })
      if (response.code === 200) {
        message.success('任务已开始')
        await playSound('task_started')
        return true
      } else {
        homeTaskStartError.value = response.message || '开始任务失败'
        message.error(homeTaskStartError.value)
        return false
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error)
      logger.error(`首页开始任务失败: ${errorMessage}`)
      homeTaskStartError.value = `开始任务失败: ${errorMessage}`
      message.error(homeTaskStartError.value)
      return false
    } finally {
      startingHomeTask.value = false
    }
  }

  const retryHomeTask = async () => startHomeTask()

  watch(
    schedulerModeOptions,
    options => {
      if (options.some(option => option.value === selectedHomeMode.value)) return
      selectedHomeMode.value = options[0]?.value ?? TaskCreateIn.mode.AUTO_PROXY
    },
    { immediate: true }
  )

  const fetchOverviewData = async (): Promise<boolean> => {
    try {
      const response = await Service.getOverviewApiInfoGetOverviewPost()
      if (response.code === 200) {
        const data = response.data as { Proxy?: Record<string, ProxyInfo> }
        proxyData.value = data.Proxy ?? {}
        return true
      } else {
        logger.warn(`获取首页概览失败: ${response.message || '获取数据失败'}`)
        return false
      }
    } catch (err) {
      logger.error(`获取首页概览失败: ${err instanceof Error ? err.message : String(err)}`)
      return false
    }
  }

  const fetchQueueSummary = async (): Promise<boolean> => {
    try {
      const response = await Service.getQueuesApiQueueGetPost({ queueId: null })
      if (response.code === 200 && response.data) {
        const queueIds = response.index?.map(item => item.uid) ?? Object.keys(response.data)
        const queues = queueIds
          .map(queueId => response.data[queueId])
          .filter(queue => queue != null)
        const itemCounts = await Promise.all(
          queueIds.map(async queueId => {
            try {
              const itemResponse = await Service.getItemApiQueueItemGetPost({
                queueId,
                queueItemId: null,
              })
              return itemResponse.code === 200 ? itemResponse.index.length : 0
            } catch (error) {
              logger.warn(
                `获取队列 ${queueId} 的队列项失败: ${
                  error instanceof Error ? error.message : String(error)
                }`
              )
              return 0
            }
          })
        )
        queueSummary.value = {
          queueCount: queues.length,
          enabledQueueCount: queues.filter(queue => {
            const info = queue.Info
            return Boolean(info?.TimeEnabled || info?.StartUpEnabled || info?.CycleEnabled)
          }).length,
          itemCount: itemCounts.reduce((sum, count) => sum + count, 0),
        }
        return true
      } else {
        queueSummary.value = null
        return response.code === 200
      }
    } catch (err) {
      queueSummary.value = null
      logger.warn(`获取队列概览失败: ${err instanceof Error ? err.message : String(err)}`)
      return false
    }
  }

  const fetchRecentRecords = async (): Promise<boolean> => {
    try {
      const response = await Service.searchHistoryApiHistorySearchPost({
        mode: HistorySearchIn.mode.DAILY,
        start_date: dayjs().subtract(7, 'day').format('YYYY-MM-DD'),
        end_date: dayjs().format('YYYY-MM-DD'),
      })
      if (response.code === 200 && response.data) {
        const records: HomeRecentRecord[] = []
        Object.entries(response.data).forEach(([date, users]) => {
          Object.entries(users as Record<string, HistoryData>).forEach(([username, userData]) => {
            const index = userData.index ?? []
            index.forEach((record: any) => {
              records.push({ date, username, record })
            })
          })
        })
        records.sort((a, b) => b.record.date.localeCompare(a.record.date))
        recentRecords.value = records.slice(0, 6)
        return true
      }
      return false
    } catch (err) {
      logger.warn(`获取近期结果失败: ${err instanceof Error ? err.message : String(err)}`)
      return false
    }
  }

  const fetchNoticeData = async () => {
    try {
      const response = await Service.getNoticeInfoApiInfoNoticeGetPost()
      if (response.code === 200) {
        if (response.if_need_show && response.data && Object.keys(response.data).length > 0) {
          noticeData.value = response.data
          noticeVisible.value = true
          await playSound('announcement_display')
        }
      } else {
        logger.warn(`获取公告失败: ${response.message}`)
      }
    } catch (error) {
      logger.error(`获取公告失败: ${error instanceof Error ? error.message : String(error)}`)
    } finally {
      noticeLoading.value = false
    }
  }

  const showNotice = async () => {
    noticeLoading.value = true
    try {
      const response = await Service.getNoticeInfoApiInfoNoticeGetPost()
      if (response.code === 200) {
        if (response.data && Object.keys(response.data).length > 0) {
          noticeData.value = response.data
          noticeVisible.value = true
          await playSound('announcement_display')
        } else {
          message.info('暂无公告信息')
        }
      } else {
        message.error(response.message || '获取公告失败')
      }
    } catch (error) {
      logger.error(`显示公告失败: ${error instanceof Error ? error.message : String(error)}`)
      message.error('显示公告失败，请稍后重试')
    } finally {
      noticeLoading.value = false
    }
  }

  const onNoticeConfirmed = () => {
    noticeVisible.value = false
  }

  const loadHomeData = async () => {
    loading.value = true
    homeDataError.value = null
    try {
      const results = await Promise.all([
        fetchOverviewData(),
        fetchQueueSummary(),
        fetchRecentRecords(),
        fetchSchedulerTaskOptions({ quiet: true }),
      ])
      if (results.some(result => !result)) {
        homeDataError.value = '部分首页数据加载失败，请重试刷新。'
      }
    } finally {
      loading.value = false
    }
  }

  const refresh = async () => {
    await loadHomeData()
    if (homeDataError.value) {
      message.warning(homeDataError.value)
    } else {
      message.success('首页数据已刷新')
    }
  }

  const formatProxyDisplay = (dateStr: string) => {
    if (dateStr === '暂无代理数据') return dateStr
    return formatBackendDateTime(dateStr)
  }

  onMounted(() => {
    loadHomeLayoutConfig()
    if (isBootstrapping.value) {
      loading.value = true
      noticeLoading.value = true
      const stopWatching = watch(isBootstrapping, bootstrapping => {
        if (bootstrapping) return
        stopWatching()
        loadHomeData()
        fetchNoticeData()
      })
      return
    }
    loadHomeData()
    fetchNoticeData()
  })

  return {
    loading,
    homeDataError,
    schedulerTasksLoading,
    startingHomeTask,
    homeTaskStartError,
    layoutEditing,
    homeModuleOrder,
    reorderableHomeModules,
    hiddenHomeModules,
    proxyData,
    queueSummary,
    recentRecords,
    schedulerTaskOptions,
    schedulerModeOptions,
    selectedHomeTaskId,
    selectedHomeMode,
    schedulerTasksError,
    noticeVisible,
    noticeData,
    noticeLoading,
    greeting,
    commandTitle,
    isBootstrapping,
    statusSummary,
    wsStatus,
    backendStatus,
    toggleLayoutEditing,
    canMoveHomeModule,
    moveHomeModule,
    isHomeModuleShown,
    setHomeModuleShown,
    isHomeModuleVisible,
    fetchSchedulerTaskOptions,
    onSchedulerDropdownVisibleChange,
    startHomeTask,
    retryHomeTask,
    loadHomeData,
    refresh,
    showNotice,
    onNoticeConfirmed,
    formatProxyDisplay,
  }
}
