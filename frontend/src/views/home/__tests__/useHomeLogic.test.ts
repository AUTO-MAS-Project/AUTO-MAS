import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { TaskCreateIn } from '@/api/models/TaskCreateIn'

const logger = { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() }

const mockService = vi.hoisted(() => ({
  getTaskComboxApiInfoComboxTaskPost: vi.fn(),
  addTaskApiDispatchStartPost: vi.fn(),
  getOverviewApiInfoGetOverviewPost: vi.fn(),
  getQueuesApiQueueGetPost: vi.fn(),
  getItemApiQueueItemGetPost: vi.fn(),
  searchHistoryApiHistorySearchPost: vi.fn(),
  getNoticeInfoApiInfoNoticeGetPost: vi.fn(),
}))

const mockPlaySound = vi.hoisted(() => vi.fn())

const mockWsStatus = ref('已连接')
const mockBackendStatus = ref('running')
const mockIsBootstrapping = ref(false)

vi.mock('@/api/services/Service', () => ({ Service: mockService }))
vi.mock('@/composables/useAudioPlayer', () => ({
  useAudioPlayer: () => ({ playSound: mockPlaySound }),
}))
vi.mock('@/composables/useAppInitialization', () => ({
  useAppInitialization: () => ({ isBootstrapping: mockIsBootstrapping }),
}))
vi.mock('@/composables/useWebSocket', () => ({
  useWebSocket: () => ({
    status: mockWsStatus,
    backendStatus: mockBackendStatus,
  }),
}))
vi.mock('ant-design-vue', () => ({
  message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
}))

const loadUseHomeLogic = async () => {
  vi.stubGlobal('window', {
    electronAPI: { getLogger: () => logger },
  })
  vi.stubGlobal('localStorage', {
    getItem: vi.fn(),
    setItem: vi.fn(),
    removeItem: vi.fn(),
  })
  vi.resetModules()
  return import('../useHomeLogic')
}

const flushPromises = async () => {
  await Promise.resolve()
  await Promise.resolve()
}

describe('useHomeLogic', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockWsStatus.value = '已连接'
    mockBackendStatus.value = 'running'
    mockIsBootstrapping.value = false
    vi.stubGlobal('localStorage', {
      getItem: vi.fn(),
      setItem: vi.fn(),
      removeItem: vi.fn(),
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('加载概览、队列和近期结果数据', async () => {
    mockService.getOverviewApiInfoGetOverviewPost.mockResolvedValue({
      code: 200,
      data: {
        Proxy: {
          user1: {
            LastProxyDate: '2026-07-24T10:00:00',
            ErrorTimes: 0,
            ProxyTimes: 1,
            ErrorInfo: {},
          },
        },
      },
    })
    mockService.getQueuesApiQueueGetPost.mockResolvedValue({
      code: 200,
      index: [{ uid: 'q1', type: 'QueueConfig' }],
      data: { q1: { Info: { CycleEnabled: true } } },
    })
    mockService.getItemApiQueueItemGetPost.mockResolvedValue({
      code: 200,
      index: [{ uid: 'i1', type: 'QueueItem' }],
      data: {},
    })
    mockService.searchHistoryApiHistorySearchPost.mockResolvedValue({ code: 200, data: {} })

    const { useHomeLogic } = await loadUseHomeLogic()
    const { queueSummary, proxyData, recentRecords, loading, refresh } = useHomeLogic()

    await refresh()
    await flushPromises()

    expect(loading.value).toBe(false)
    expect(queueSummary.value).toEqual({ queueCount: 1, enabledQueueCount: 1, itemCount: 1 })
    expect(proxyData.value).toHaveProperty('user1')
    expect(recentRecords.value).toEqual([])
  })

  it('概览失败时记录错误但不阻塞其他数据', async () => {
    mockService.getOverviewApiInfoGetOverviewPost.mockRejectedValue(new Error('overview timeout'))
    mockService.getQueuesApiQueueGetPost.mockResolvedValue({
      code: 200,
      index: [{ uid: 'q1', type: 'QueueConfig' }],
      data: { q1: { Info: { StartUpEnabled: true } } },
    })
    mockService.getItemApiQueueItemGetPost.mockResolvedValue({
      code: 200,
      index: [],
      data: {},
    })
    mockService.searchHistoryApiHistorySearchPost.mockResolvedValue({ code: 200, data: {} })

    const { useHomeLogic } = await loadUseHomeLogic()
    const { queueSummary, loading, refresh } = useHomeLogic()

    await refresh()
    await flushPromises()

    expect(loading.value).toBe(false)
    expect(queueSummary.value).toEqual({ queueCount: 1, enabledQueueCount: 1, itemCount: 0 })
    expect(logger.error).toHaveBeenCalledWith(expect.stringContaining('overview timeout'))
  })

  it('状态汇总反映 WS、后端和代理错误', async () => {
    mockWsStatus.value = '已断开'
    mockBackendStatus.value = 'error'
    mockService.getOverviewApiInfoGetOverviewPost.mockResolvedValue({
      code: 200,
      data: { Proxy: { u1: { ErrorTimes: 1, ProxyTimes: 0, LastProxyDate: '', ErrorInfo: {} } } },
    })
    mockService.getQueuesApiQueueGetPost.mockResolvedValue({ code: 200, data: {} })
    mockService.searchHistoryApiHistorySearchPost.mockResolvedValue({ code: 200, data: {} })

    const { useHomeLogic } = await loadUseHomeLogic()
    const { statusSummary, refresh } = useHomeLogic()

    await refresh()
    await flushPromises()

    expect(statusSummary.value.ws).toBe('已断开')
    expect(statusSummary.value.backend).toBe('error')
    expect(statusSummary.value.hasErrors).toBe(true)
    expect(statusSummary.value.isReady).toBe(false)
  })

  it('默认顺序为 command→queue→recent→satellite→status→proxy 且 recent 紧邻 satellite', async () => {
    const { defaultHomeModuleOrder } = await loadUseHomeLogic()

    // 真机反馈的默认布局：快速开始 → 队列概览 → 最近活动+卫星并排 → 其余
    expect(defaultHomeModuleOrder).toEqual([
      'command',
      'queue',
      'recent',
      'satellite',
      'status',
      'proxy',
    ])
    // recent(span 4) 必须紧邻并先于 satellite(span 8)，两者才能稳定并排成一行
    const recentIndex = defaultHomeModuleOrder.indexOf('recent')
    expect(defaultHomeModuleOrder[recentIndex + 1]).toBe('satellite')
  })

  it('从 localStorage 读取并持久化布局配置', async () => {
    const { useHomeLogic, defaultHomeModuleOrder } = await loadUseHomeLogic()

    const localStorageMock = {
      getItem: vi.fn(),
      setItem: vi.fn(),
      removeItem: vi.fn(),
    }
    vi.stubGlobal('localStorage', localStorageMock)

    const { homeModuleOrder, setHomeModuleShown, moveHomeModule, isHomeModuleShown } =
      useHomeLogic()

    expect(homeModuleOrder.value).toEqual(defaultHomeModuleOrder)

    setHomeModuleShown('proxy', true)
    expect(isHomeModuleShown('proxy')).toBe(true)

    moveHomeModule('status', 'down')
    expect(homeModuleOrder.value).toEqual([
      'command',
      'queue',
      'recent',
      'satellite',
      'proxy',
      'status',
    ])

    expect(localStorageMock.setItem).toHaveBeenCalled()
    const lastCall = localStorageMock.setItem.mock.calls.at(-1)
    expect(lastCall?.[0]).toBe('auto-mas.home.layout')
    const saved = JSON.parse(lastCall?.[1] ?? '{}')
    expect(saved.hiddenModules).not.toContain('proxy')
    expect(saved.moduleOrder[0]).toBe('command')
  })

  it('默认展示卫星环绕，并为旧版布局自动补齐该模块', async () => {
    const { useHomeLogic, defaultHomeModuleOrder, moduleTitleMap, normalizeHomeModuleOrder } =
      await loadUseHomeLogic()
    const { hiddenHomeModules, isHomeModuleShown } = useHomeLogic()

    expect(defaultHomeModuleOrder).toContain('satellite')
    expect(moduleTitleMap.satellite).toBe('卫星环绕')
    expect(hiddenHomeModules.value).not.toContain('satellite')
    expect(isHomeModuleShown('satellite')).toBe(true)
    // 旧版布局里的 'quick'（常用入口）模块已迁移到页头工具行，规范化时被过滤；
    // 已自定义的顺序（proxy 在前）原样保留，缺失模块按新默认顺序补到末尾
    expect(normalizeHomeModuleOrder(['command', 'quick', 'proxy'])).toEqual([
      'command',
      'proxy',
      'queue',
      'recent',
      'satellite',
      'status',
    ])
  })

  it('拖拽排序写回时强制 command 置顶并持久化', async () => {
    const { useHomeLogic } = await loadUseHomeLogic()

    const localStorageMock = {
      getItem: vi.fn(),
      setItem: vi.fn(),
      removeItem: vi.fn(),
    }
    vi.stubGlobal('localStorage', localStorageMock)

    const { homeModuleOrder, reorderableHomeModules } = useHomeLogic()

    // getter 不包含固定置顶的 command
    expect(reorderableHomeModules.value).toEqual([
      'queue',
      'recent',
      'satellite',
      'status',
      'proxy',
    ])

    reorderableHomeModules.value = ['status', 'queue', 'recent', 'satellite', 'proxy']

    expect(homeModuleOrder.value).toEqual([
      'command',
      'status',
      'queue',
      'recent',
      'satellite',
      'proxy',
    ])
    expect(localStorageMock.setItem).toHaveBeenCalled()
    const lastCall = localStorageMock.setItem.mock.calls.at(-1)
    expect(lastCall?.[0]).toBe('auto-mas.home.layout')
    const saved = JSON.parse(lastCall?.[1] ?? '{}')
    expect(saved.moduleOrder[0]).toBe('command')
    expect(saved.moduleOrder[1]).toBe('status')
  })

  it('从旧版业务文案池生成独立于页头问候的动态标题', async () => {
    const { homeCommandMessages, pickHomeCommandMessage } = await loadUseHomeLogic()

    expect(homeCommandMessages).toHaveLength(16)
    expect(pickHomeCommandMessage(() => 0)).toBe(homeCommandMessages[0])
    expect(pickHomeCommandMessage(() => 0.999999)).toBe(homeCommandMessages.at(-1))
    expect(homeCommandMessages).not.toContain('早上好！欢迎使用 AUTO-MAS')
  })

  it('已持久化的自定义顺序在默认布局调整后原样保留', async () => {
    // 用户此前按旧默认自定义并持久化过的顺序（status 在前），
    // 新默认（queue 在前）不应覆盖它——仅无持久化记录的用户拿到新默认。
    // loadHomeLayoutConfig 仅在存在持久化记录时经 normalizeHomeModuleOrder 归一化，
    // 此处直接验证该归一化对合法自定义顺序是恒等的（不会被重排成新默认）
    const { normalizeHomeModuleOrder } = await loadUseHomeLogic()

    const legacyOrder = ['command', 'status', 'recent', 'satellite', 'queue', 'proxy']
    expect(normalizeHomeModuleOrder(legacyOrder)).toEqual(legacyOrder)
  })

  it('恢复默认布局时过滤非法模块键', async () => {
    // 持久化记录中非法/重复键被过滤，缺失模块按新默认顺序补齐，command 恒置顶
    const { normalizeHomeModuleOrder, defaultHomeModuleOrder } = await loadUseHomeLogic()

    expect(normalizeHomeModuleOrder(['invalid', 'status', 'status'])).toEqual([
      'command',
      'status',
      ...defaultHomeModuleOrder.filter(k => k !== 'command' && k !== 'status'),
    ])
  })

  it('加载并选择真实任务', async () => {
    mockService.getTaskComboxApiInfoComboxTaskPost.mockResolvedValue({
      code: 200,
      data: [{ label: 'Task A', value: 'task-a' }],
    })

    const { useHomeLogic } = await loadUseHomeLogic()
    const { schedulerTaskOptions, selectedHomeTaskId, onSchedulerDropdownVisibleChange } =
      useHomeLogic()

    await onSchedulerDropdownVisibleChange(true)
    await flushPromises()

    expect(schedulerTaskOptions.value).toEqual([
      { label: 'Task A', value: 'task-a', title: 'Task A' },
    ])
    expect(selectedHomeTaskId.value).toBe('task-a')
  })

  it('任务下拉不可用时进入真实错误态，不生成可误启动的占位任务', async () => {
    mockService.getTaskComboxApiInfoComboxTaskPost.mockRejectedValue(new Error('combox error'))

    const { useHomeLogic } = await loadUseHomeLogic()
    const {
      schedulerTaskOptions,
      selectedHomeTaskId,
      schedulerTasksError,
      onSchedulerDropdownVisibleChange,
    } = useHomeLogic()

    await onSchedulerDropdownVisibleChange(true)
    await flushPromises()

    expect(schedulerTaskOptions.value).toEqual([])
    expect(selectedHomeTaskId.value).toBeNull()
    expect(schedulerTasksError.value).toContain('combox error')
  })

  it('过滤后端未选择占位项，并按真实目标能力切换运行模式', async () => {
    mockService.getTaskComboxApiInfoComboxTaskPost.mockResolvedValue({
      code: 200,
      data: [
        { label: '未选择', value: null },
        {
          label: '脚本 - MaaEnd - 主账号',
          value: 'script-config',
          supported_modes: ['ScriptConfig'],
        },
        {
          label: '队列 - 夜间循环',
          value: 'queue-cycle',
          supported_modes: ['AutoProxy', 'CycleRun'],
        },
      ],
    })

    const { useHomeLogic } = await loadUseHomeLogic()
    const {
      schedulerTaskOptions,
      schedulerModeOptions,
      selectedHomeTaskId,
      selectedHomeMode,
      fetchSchedulerTaskOptions,
    } = useHomeLogic()

    await fetchSchedulerTaskOptions()
    await flushPromises()

    expect(schedulerTaskOptions.value.map(option => option.value)).toEqual([
      'script-config',
      'queue-cycle',
    ])
    expect(selectedHomeTaskId.value).toBe('script-config')
    expect(selectedHomeMode.value).toBe(TaskCreateIn.mode.SCRIPT_CONFIG)
    expect(schedulerModeOptions.value).toEqual([
      { label: '配置脚本', value: TaskCreateIn.mode.SCRIPT_CONFIG },
    ])

    selectedHomeTaskId.value = 'queue-cycle'
    await flushPromises()
    expect(schedulerModeOptions.value.map(option => option.value)).toEqual([
      TaskCreateIn.mode.AUTO_PROXY,
      TaskCreateIn.mode.CYCLE_RUN,
    ])
    expect(selectedHomeMode.value).toBe(TaskCreateIn.mode.AUTO_PROXY)
  })

  it('启动真实任务并播放音效', async () => {
    mockService.addTaskApiDispatchStartPost.mockResolvedValue({ code: 200 })

    const { useHomeLogic } = await loadUseHomeLogic()
    const { schedulerTaskOptions, selectedHomeTaskId, selectedHomeMode, startHomeTask } =
      useHomeLogic()

    schedulerTaskOptions.value = [
      {
        label: '脚本 - MAA - 主账号',
        title: '脚本 - MAA - 主账号',
        value: 'task-real',
        supported_modes: ['AutoProxy'],
      },
    ]
    selectedHomeTaskId.value = 'task-real'
    selectedHomeMode.value = TaskCreateIn.mode.AUTO_PROXY

    await startHomeTask()
    await flushPromises()

    expect(mockService.addTaskApiDispatchStartPost).toHaveBeenCalledWith({
      taskId: 'task-real',
      mode: TaskCreateIn.mode.AUTO_PROXY,
    })
    expect(mockPlaySound).toHaveBeenCalledWith('task_started')
  })

  it('未选择真实任务时不调用后端接口', async () => {
    const { useHomeLogic } = await loadUseHomeLogic()
    const { selectedHomeTaskId, startHomeTask } = useHomeLogic()

    selectedHomeTaskId.value = null

    await startHomeTask()
    await flushPromises()

    expect(mockService.addTaskApiDispatchStartPost).not.toHaveBeenCalled()
  })

  it('启动任务失败时停止 loading 并记录日志', async () => {
    mockService.addTaskApiDispatchStartPost.mockRejectedValue(new Error('dispatch down'))

    const { useHomeLogic } = await loadUseHomeLogic()
    const {
      schedulerTaskOptions,
      selectedHomeTaskId,
      startHomeTask,
      startingHomeTask,
      homeTaskStartError,
    } = useHomeLogic()

    schedulerTaskOptions.value = [
      {
        label: '脚本 - MAA - 主账号',
        title: '脚本 - MAA - 主账号',
        value: 'task-real',
        supported_modes: ['AutoProxy'],
      },
    ]
    selectedHomeTaskId.value = 'task-real'
    await startHomeTask()
    await flushPromises()

    expect(startingHomeTask.value).toBe(false)
    expect(homeTaskStartError.value).toContain('dispatch down')
    expect(logger.error).toHaveBeenCalledWith(expect.stringContaining('dispatch down'))
  })

  it('保留失败任务选择并通过重试再次调用真实启动接口', async () => {
    mockService.addTaskApiDispatchStartPost
      .mockRejectedValueOnce(new Error('dispatch down'))
      .mockResolvedValueOnce({ code: 200 })

    const { useHomeLogic } = await loadUseHomeLogic()
    const {
      schedulerTaskOptions,
      selectedHomeTaskId,
      startHomeTask,
      retryHomeTask,
      homeTaskStartError,
    } = useHomeLogic()

    schedulerTaskOptions.value = [
      {
        label: '队列 - 夜间任务',
        title: '队列 - 夜间任务',
        value: 'task-retry',
        supported_modes: ['AutoProxy'],
      },
    ]
    selectedHomeTaskId.value = 'task-retry'
    await startHomeTask()
    expect(homeTaskStartError.value).toContain('dispatch down')

    await retryHomeTask()

    expect(mockService.addTaskApiDispatchStartPost).toHaveBeenCalledTimes(2)
    expect(mockService.addTaskApiDispatchStartPost).toHaveBeenLastCalledWith({
      taskId: 'task-retry',
      mode: TaskCreateIn.mode.AUTO_PROXY,
    })
    expect(homeTaskStartError.value).toBeNull()
  })

  it('公告需要展示时打开弹窗并播放音效', async () => {
    mockService.getNoticeInfoApiInfoNoticeGetPost.mockResolvedValue({
      code: 200,
      if_need_show: true,
      data: { title: 'Announcement' },
    })

    const { useHomeLogic } = await loadUseHomeLogic()
    const { noticeVisible, noticeData, showNotice, noticeLoading } = useHomeLogic()

    await showNotice()
    await flushPromises()

    expect(noticeLoading.value).toBe(false)
    expect(noticeVisible.value).toBe(true)
    expect(noticeData.value).toEqual({ title: 'Announcement' })
    expect(mockPlaySound).toHaveBeenCalledWith('announcement_display')
  })

  it('确认公告关闭弹窗', async () => {
    const { useHomeLogic } = await loadUseHomeLogic()
    const { noticeVisible, onNoticeConfirmed } = useHomeLogic()

    noticeVisible.value = true
    onNoticeConfirmed()

    expect(noticeVisible.value).toBe(false)
  })
})
