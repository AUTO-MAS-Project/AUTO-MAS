import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// MUST set up window BEFORE any imports, since useQueueLogic.ts accesses window.electronAPI at module level
const logger = { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() }

// Mock API service
const mockApi = vi.hoisted(() => ({
  getQueuesApiQueueGetPost: vi.fn(),
  getTimeSetApiQueueTimeGetPost: vi.fn(),
  getItemApiQueueItemGetPost: vi.fn(),
  addQueueApiQueueAddPost: vi.fn(),
  deleteQueueApiQueueDeletePost: vi.fn(),
  updateQueueApiQueueUpdatePost: vi.fn(),
  reorderItemApiQueueItemOrderPost: vi.fn(),
  getScriptComboxApiInfoComboxScriptPost: vi.fn(),
}))
const playSoundMock = vi.hoisted(() => vi.fn())

vi.mock('@/api', () => ({
  Service: mockApi,
}))

// Mock ant-design-vue message to avoid document is not defined in jsdom-less env
vi.mock('ant-design-vue', () => ({
  message: { info: vi.fn(), success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

// Mock useAudioPlayer
vi.mock('@/composables/useAudioPlayer', () => ({
  useAudioPlayer: () => ({
    playSound: playSoundMock,
  }),
}))

// Dynamic import to avoid static hoisting - must import after stubs are set up
const loadUseQueueLogic = async () => {
  vi.resetModules()
  return await import('../useQueueLogic')
}

describe('useQueueLogic', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // 默认 mock：避免 fetchQueues → loadQueueData → refreshTimeSets/refreshQueueItems
    // 调用未 mock 的 API 返回 undefined 导致 TypeError 链
    mockApi.getTimeSetApiQueueTimeGetPost.mockResolvedValue({ code: 200, index: [], data: {} })
    mockApi.getItemApiQueueItemGetPost.mockResolvedValue({ code: 200, index: [], data: {} })
    mockApi.getScriptComboxApiInfoComboxScriptPost.mockResolvedValue({ code: 200, data: [] })
    playSoundMock.mockResolvedValue(undefined)
    vi.stubGlobal('window', {
      electronAPI: {
        getLogger: () => logger,
      },
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  describe('fetchQueues', () => {
    it('成功获取队列列表', async () => {
      mockApi.getQueuesApiQueueGetPost.mockResolvedValue({
        code: 200,
        index: [{ uid: 'queue-1' }, { uid: 'queue-2' }],
        data: {
          'queue-1': { Info: { Name: '队列A' } },
          'queue-2': { Info: { Name: '队列B' } },
        },
      })

      const { useQueueLogic } = await loadUseQueueLogic()
      const { queueList, loading, fetchQueues } = useQueueLogic()
      await fetchQueues()

      expect(queueList.value).toHaveLength(2)
      expect(queueList.value[0].name).toBe('队列A')
      expect(queueList.value[1].name).toBe('队列B')
      expect(loading.value).toBe(false)
    })

    it('API 返回错误时列表为空', async () => {
      mockApi.getQueuesApiQueueGetPost.mockResolvedValue({
        code: 500,
        message: '服务器错误',
      })

      const { useQueueLogic } = await loadUseQueueLogic()
      const { queueList, loading, fetchQueues } = useQueueLogic()
      await fetchQueues()

      expect(queueList.value).toHaveLength(0)
      expect(loading.value).toBe(false)
    })

    it('API 异常时列表为空', async () => {
      mockApi.getQueuesApiQueueGetPost.mockRejectedValue(new Error('网络错误'))

      const { useQueueLogic } = await loadUseQueueLogic()
      const { queueList, loading, fetchQueues } = useQueueLogic()
      await fetchQueues()

      expect(queueList.value).toHaveLength(0)
      expect(loading.value).toBe(false)
    })

    it('空队列列表', async () => {
      mockApi.getQueuesApiQueueGetPost.mockResolvedValue({
        code: 200,
        index: [],
        data: {},
      })

      const { useQueueLogic } = await loadUseQueueLogic()
      const { queueList, loading, fetchQueues } = useQueueLogic()
      await fetchQueues()

      expect(queueList.value).toHaveLength(0)
      expect(loading.value).toBe(false)
    })
  })

  describe('refreshQueueItems - PR #268 循环语义', () => {
    it('无 Schedule/Data 字段时使用可恢复的规范默认值', async () => {
      mockApi.getQueuesApiQueueGetPost.mockResolvedValue({
        code: 200,
        index: [],
        data: {},
      })
      mockApi.getItemApiQueueItemGetPost.mockResolvedValue({
        code: 200,
        index: [{ uid: 'item-1' }],
        data: {
          'item-1': {
            Info: {
              ScriptId: 'script-a',
            },
          },
        },
      })

      const { useQueueLogic } = await loadUseQueueLogic()
      const { activeQueueId, currentQueueItems, fetchQueues, refreshQueueItems } = useQueueLogic()
      await fetchQueues()
      activeQueueId.value = 'queue-1'
      await refreshQueueItems()

      expect(currentQueueItems.value).toHaveLength(1)
      expect(currentQueueItems.value[0]).toEqual({
        id: 'item-1',
        script: 'script-a',
        scheduleEnabled: true,
        scheduleMode: 'fixed_time',
        scheduleDays: [],
        scheduleTime: '00:00',
        intervalMinutes: 480,
        intervalAnchor: 'start',
        nextRunAt: '2000-01-01 00:00:00',
        lastCycleStartedAt: '2000-01-01 00:00:00',
        lastCycleFinishedAt: '2000-01-01 00:00:00',
        cycleRunId: '',
        cycleState: 'idle',
        cycleRevision: 0,
        cycleResult: '',
        cycleError: '',
        cycleUpdatedAt: '2000-01-01 00:00:00',
      })
    })

    it('从正式 Schedule/Data 根提取循环配置与运行状态', async () => {
      mockApi.getQueuesApiQueueGetPost.mockResolvedValue({
        code: 200,
        index: [],
        data: {},
      })
      mockApi.getItemApiQueueItemGetPost.mockResolvedValue({
        code: 200,
        index: [{ uid: 'item-1' }],
        data: {
          'item-1': {
            Info: {
              ScriptId: 'script-a',
            },
            Schedule: {
              Enabled: false,
              Mode: 'interval',
              Days: ['Monday', 'Wednesday'],
              Time: '08:15',
              IntervalMinutes: 30,
              IntervalAnchor: 'start',
              NextRunAt: '2026-07-25 08:00:00',
            },
            Data: {
              LastCycleStartedAt: '2026-07-25 07:30:00',
              LastCycleFinishedAt: '2026-07-25 07:45:00',
              CycleRunId: '12345678-1234-1234-1234-123456789abc',
              CycleState: 'failed',
              CycleRevision: 4,
              CycleResult: 'error',
              CycleError: 'InterruptedError: host exited',
              CycleUpdatedAt: '2026-07-25 07:45:01',
            },
          },
        },
      })

      const { useQueueLogic } = await loadUseQueueLogic()
      const { activeQueueId, currentQueueItems, fetchQueues, refreshQueueItems } = useQueueLogic()
      await fetchQueues()
      activeQueueId.value = 'queue-1'
      await refreshQueueItems()

      expect(currentQueueItems.value).toHaveLength(1)
      const item = currentQueueItems.value[0]
      expect(item.scheduleEnabled).toBe(false)
      expect(item.scheduleMode).toBe('interval')
      expect(item.scheduleDays).toEqual(['Monday', 'Wednesday'])
      expect(item.scheduleTime).toBe('08:15')
      expect(item.intervalMinutes).toBe(30)
      expect(item.intervalAnchor).toBe('start')
      expect(item.nextRunAt).toBe('2026-07-25 08:00:00')
      expect(item.lastCycleStartedAt).toBe('2026-07-25 07:30:00')
      expect(item.lastCycleFinishedAt).toBe('2026-07-25 07:45:00')
      expect(item.cycleRunId).toBe('12345678-1234-1234-1234-123456789abc')
      expect(item.cycleState).toBe('failed')
      expect(item.cycleRevision).toBe(4)
      expect(item.cycleResult).toBe('error')
      expect(item.cycleError).toContain('host exited')
      expect(item.cycleUpdatedAt).toBe('2026-07-25 07:45:01')
    })

    it('快速切换队列时旧请求不得覆盖当前队列', async () => {
      const { useQueueLogic } = await loadUseQueueLogic()
      const { activeQueueId, currentQueueItems, refreshQueueItems } = useQueueLogic()
      let resolveQueueA!: (value: any) => void
      const queueAResponse = new Promise(resolve => {
        resolveQueueA = resolve
      })
      mockApi.getItemApiQueueItemGetPost
        .mockImplementationOnce(() => queueAResponse)
        .mockResolvedValueOnce({
          code: 200,
          index: [{ uid: 'item-b' }],
          data: {
            'item-b': {
              Info: { ScriptId: 'script-b' },
              Schedule: { Mode: 'interval', IntervalMinutes: 15 },
            },
          },
        })

      activeQueueId.value = 'queue-a'
      const staleRequest = refreshQueueItems('queue-a')
      activeQueueId.value = 'queue-b'
      await refreshQueueItems('queue-b')
      expect(currentQueueItems.value.map(item => item.id)).toEqual(['item-b'])

      resolveQueueA({
        code: 200,
        index: [{ uid: 'item-a' }],
        data: { 'item-a': { Info: { ScriptId: 'script-a' } } },
      })
      await staleRequest

      expect(currentQueueItems.value.map(item => item.id)).toEqual(['item-b'])
    })
  })

  describe('handleAddQueue', () => {
    it('成功创建队列', async () => {
      mockApi.getQueuesApiQueueGetPost.mockResolvedValue({
        code: 200,
        index: [],
        data: {},
      })
      mockApi.addQueueApiQueueAddPost.mockResolvedValue({
        code: 200,
        queueId: 'new-queue',
      })

      const { useQueueLogic } = await loadUseQueueLogic()
      const { queueList, activeQueueId, fetchQueues, handleAddQueue } = useQueueLogic()
      await fetchQueues()
      const created = await handleAddQueue()

      expect(created).toBe(true)
      expect(queueList.value).toHaveLength(1)
      expect(queueList.value[0].id).toBe('new-queue')
      expect(activeQueueId.value).toBe('new-queue')
      expect(mockApi.updateQueueApiQueueUpdatePost).not.toHaveBeenCalled()
    })

    it('创建循环队列时先写入 CycleEnabled 再展示队列', async () => {
      mockApi.getQueuesApiQueueGetPost.mockResolvedValue({
        code: 200,
        index: [],
        data: {},
      })
      mockApi.addQueueApiQueueAddPost.mockResolvedValue({
        code: 200,
        queueId: 'cycle-queue',
      })
      mockApi.updateQueueApiQueueUpdatePost.mockResolvedValue({ code: 200 })

      const { useQueueLogic } = await loadUseQueueLogic()
      const { queueList, fetchQueues, handleAddQueue } = useQueueLogic()
      await fetchQueues()
      const created = await handleAddQueue(true)

      expect(created).toBe(true)
      expect(mockApi.updateQueueApiQueueUpdatePost).toHaveBeenCalledWith({
        queueId: 'cycle-queue',
        data: { Info: { CycleEnabled: true } },
      })
      expect(queueList.value.map(queue => queue.id)).toEqual(['cycle-queue'])
    })

    it('循环队列初始化失败时删除半成品并保持列表不变', async () => {
      mockApi.getQueuesApiQueueGetPost.mockResolvedValue({
        code: 200,
        index: [],
        data: {},
      })
      mockApi.addQueueApiQueueAddPost.mockResolvedValue({
        code: 200,
        queueId: 'partial-cycle-queue',
      })
      mockApi.updateQueueApiQueueUpdatePost.mockResolvedValue({
        code: 500,
        message: '循环配置保存失败',
      })
      mockApi.deleteQueueApiQueueDeletePost.mockResolvedValue({ code: 200 })

      const { useQueueLogic } = await loadUseQueueLogic()
      const { queueList, fetchQueues, handleAddQueue } = useQueueLogic()
      await fetchQueues()
      const created = await handleAddQueue(true)

      expect(created).toBe(false)
      expect(mockApi.deleteQueueApiQueueDeletePost).toHaveBeenCalledWith({
        queueId: 'partial-cycle-queue',
      })
      expect(queueList.value).toHaveLength(0)
    })

    it('循环队列初始化请求抛异常时同样删除半成品并保持列表不变', async () => {
      mockApi.getQueuesApiQueueGetPost.mockResolvedValue({
        code: 200,
        index: [],
        data: {},
      })
      mockApi.addQueueApiQueueAddPost.mockResolvedValue({
        code: 200,
        queueId: 'exception-cycle-queue',
      })
      mockApi.updateQueueApiQueueUpdatePost.mockRejectedValue(new Error('连接中断'))
      mockApi.deleteQueueApiQueueDeletePost.mockResolvedValue({ code: 200 })

      const { useQueueLogic } = await loadUseQueueLogic()
      const { queueList, fetchQueues, handleAddQueue } = useQueueLogic()
      await fetchQueues()
      const created = await handleAddQueue(true)

      expect(created).toBe(false)
      expect(mockApi.deleteQueueApiQueueDeletePost).toHaveBeenCalledWith({
        queueId: 'exception-cycle-queue',
      })
      expect(queueList.value).toHaveLength(0)
    })

    it('创建失败时列表不变', async () => {
      mockApi.getQueuesApiQueueGetPost.mockResolvedValue({
        code: 200,
        index: [],
        data: {},
      })
      mockApi.addQueueApiQueueAddPost.mockResolvedValue({
        code: 500,
        message: '创建失败',
      })

      const { useQueueLogic } = await loadUseQueueLogic()
      const { queueList, fetchQueues, handleAddQueue } = useQueueLogic()
      await fetchQueues()
      const created = await handleAddQueue()

      expect(created).toBe(false)
      expect(queueList.value).toHaveLength(0)
    })
  })

  describe('handleRemoveQueue', () => {
    it('成功删除队列', async () => {
      mockApi.getQueuesApiQueueGetPost.mockResolvedValue({
        code: 200,
        index: [{ uid: 'queue-1' }],
        data: { 'queue-1': { Info: { Name: '队列A' } } },
      })
      mockApi.deleteQueueApiQueueDeletePost.mockResolvedValue({
        code: 200,
      })

      const { useQueueLogic } = await loadUseQueueLogic()
      const { queueList, fetchQueues, handleRemoveQueue } = useQueueLogic()
      await fetchQueues()
      await handleRemoveQueue('queue-1')

      expect(queueList.value).toHaveLength(0)
    })

    it('删除接口失败时保留现有队列', async () => {
      mockApi.getQueuesApiQueueGetPost.mockResolvedValue({
        code: 200,
        index: [{ uid: 'queue-1' }],
        data: { 'queue-1': { Info: { Name: '队列A' } } },
      })
      mockApi.deleteQueueApiQueueDeletePost.mockResolvedValue({
        code: 500,
        message: '仍在运行',
      })

      const { useQueueLogic } = await loadUseQueueLogic()
      const { queueList, fetchQueues, handleRemoveQueue } = useQueueLogic()
      await fetchQueues()
      await handleRemoveQueue('queue-1')

      expect(queueList.value).toEqual([{ id: 'queue-1', name: '队列A' }])
    })

    it('删除提示音失败时仍保留后端删除成功结果', async () => {
      mockApi.getQueuesApiQueueGetPost.mockResolvedValue({
        code: 200,
        index: [{ uid: 'queue-1' }],
        data: { 'queue-1': { Info: { Name: '队列A' } } },
      })
      mockApi.deleteQueueApiQueueDeletePost.mockResolvedValue({ code: 200 })
      playSoundMock.mockRejectedValueOnce(new Error('audio unavailable'))

      const { useQueueLogic } = await loadUseQueueLogic()
      const { queueList, fetchQueues, handleRemoveQueue } = useQueueLogic()
      await fetchQueues()
      await handleRemoveQueue('queue-1')

      expect(queueList.value).toHaveLength(0)
      expect(logger.warn).toHaveBeenCalledWith(
        expect.stringContaining('队列已删除，但删除提示音播放失败')
      )
    })
  })

  describe('队列配置保存失败回滚', () => {
    const queueResponse = {
      code: 200,
      index: [{ uid: 'queue-a' }, { uid: 'queue-b' }],
      data: {
        'queue-a': {
          Info: {
            Name: '稳定队列',
            StartUpEnabled: false,
            TimeEnabled: true,
            CycleEnabled: false,
            AfterAccomplish: 'NoAction',
          },
        },
        'queue-b': {
          Info: {
            Name: '候选队列',
            StartUpEnabled: true,
            TimeEnabled: false,
            CycleEnabled: true,
            AfterAccomplish: 'Shutdown',
          },
        },
      },
    }

    it('名称保存失败时恢复输入框和列表名称，并保持编辑态', async () => {
      mockApi.getQueuesApiQueueGetPost.mockResolvedValue(queueResponse)
      mockApi.updateQueueApiQueueUpdatePost.mockResolvedValue({
        code: 500,
        message: '名称冲突',
      })

      const { useQueueLogic } = await loadUseQueueLogic()
      const logic = useQueueLogic()
      logic.queueList.value = [{ id: 'queue-a', name: '稳定队列' }]
      logic.activeQueueId.value = 'queue-a'
      await logic.loadQueueData('queue-a')
      logic.currentQueueName.value = '冲突名称'
      logic.isEditingQueueName.value = true

      await logic.finishEditQueueName()

      expect(logic.currentQueueName.value).toBe('稳定队列')
      expect(logic.queueList.value[0].name).toBe('稳定队列')
      expect(logic.isEditingQueueName.value).toBe(true)
    })

    it('开关和完成后操作保存失败时恢复最后一次服务端值', async () => {
      mockApi.getQueuesApiQueueGetPost.mockResolvedValue(queueResponse)
      mockApi.updateQueueApiQueueUpdatePost.mockResolvedValue({
        code: 500,
        message: '保存失败',
      })

      const { useQueueLogic } = await loadUseQueueLogic()
      const logic = useQueueLogic()
      logic.queueList.value = [{ id: 'queue-a', name: '稳定队列' }]
      logic.activeQueueId.value = 'queue-a'
      await logic.loadQueueData('queue-a')

      logic.currentCycleEnabled.value = true
      logic.currentAfterAccomplish.value = 'Shutdown'
      expect(await logic.handleConfigChange('CycleEnabled', true)).toBe(false)
      expect(await logic.handleConfigChange('AfterAccomplish', 'Shutdown')).toBe(false)

      expect(logic.currentCycleEnabled.value).toBe(false)
      expect(logic.currentAfterAccomplish.value).toBe('NoAction')
    })

    it('切换目标队列加载失败时完整恢复原队列和子项', async () => {
      mockApi.getQueuesApiQueueGetPost.mockResolvedValueOnce(queueResponse).mockResolvedValueOnce({
        code: 200,
        index: [{ uid: 'queue-a' }, { uid: 'queue-b' }],
        data: { 'queue-a': queueResponse.data['queue-a'] },
      })
      mockApi.getTimeSetApiQueueTimeGetPost.mockResolvedValue({
        code: 200,
        index: [{ uid: 'time-a' }],
        data: { 'time-a': { Info: { Time: '08:30', Enabled: true, Days: ['Monday'] } } },
      })
      mockApi.getItemApiQueueItemGetPost.mockResolvedValue({
        code: 200,
        index: [{ uid: 'item-a' }],
        data: { 'item-a': { Info: { ScriptId: 'script-a' } } },
      })

      const { useQueueLogic } = await loadUseQueueLogic()
      const logic = useQueueLogic()
      logic.queueList.value = [
        { id: 'queue-a', name: '稳定队列' },
        { id: 'queue-b', name: '候选队列' },
      ]
      logic.activeQueueId.value = 'queue-a'
      await logic.loadQueueData('queue-a')

      await logic.onQueueChange('queue-b')

      expect(logic.activeQueueId.value).toBe('queue-a')
      expect(logic.currentQueueName.value).toBe('稳定队列')
      expect(logic.currentTimeSets.value.map(item => item.id)).toEqual(['time-a'])
      expect(logic.currentQueueItems.value.map(item => item.id)).toEqual(['item-a'])
    })
  })

  describe('reorderQueueItems - 拖拽重排序与失败回滚', () => {
    it('成功重排序返回 true', async () => {
      mockApi.getQueuesApiQueueGetPost.mockResolvedValue({
        code: 200,
        index: [],
        data: {},
      })
      mockApi.reorderItemApiQueueItemOrderPost.mockResolvedValue({
        code: 200,
      })

      const { useQueueLogic } = await loadUseQueueLogic()
      const { reorderQueueItems, fetchQueues } = useQueueLogic()
      await fetchQueues()

      const rollbackFn = vi.fn().mockResolvedValue(undefined)
      const result = await reorderQueueItems('queue-1', ['item-2', 'item-1'], rollbackFn)

      expect(result).toBe(true)
      expect(mockApi.reorderItemApiQueueItemOrderPost).toHaveBeenCalledWith({
        queueId: 'queue-1',
        indexList: ['item-2', 'item-1'],
      })
      expect(rollbackFn).not.toHaveBeenCalled()
    })

    it('API 返回非 200 时触发回滚', async () => {
      mockApi.getQueuesApiQueueGetPost.mockResolvedValue({
        code: 200,
        index: [],
        data: {},
      })
      mockApi.reorderItemApiQueueItemOrderPost.mockResolvedValue({
        code: 500,
        message: '服务器错误',
      })

      const { useQueueLogic } = await loadUseQueueLogic()
      const { reorderQueueItems, fetchQueues } = useQueueLogic()
      await fetchQueues()

      const rollbackFn = vi.fn().mockResolvedValue(undefined)
      const result = await reorderQueueItems('queue-1', ['item-2', 'item-1'], rollbackFn)

      expect(result).toBe(false)
      expect(rollbackFn).toHaveBeenCalledTimes(1)
      expect(logger.error).toHaveBeenCalledWith(expect.stringContaining('队列项排序失败'))
    })

    it('API 抛出异常时触发回滚', async () => {
      mockApi.getQueuesApiQueueGetPost.mockResolvedValue({
        code: 200,
        index: [],
        data: {},
      })
      mockApi.reorderItemApiQueueItemOrderPost.mockRejectedValue(new Error('网络断开'))

      const { useQueueLogic } = await loadUseQueueLogic()
      const { reorderQueueItems, fetchQueues } = useQueueLogic()
      await fetchQueues()

      const rollbackFn = vi.fn().mockResolvedValue(undefined)
      const result = await reorderQueueItems('queue-1', ['item-2', 'item-1'], rollbackFn)

      expect(result).toBe(false)
      expect(rollbackFn).toHaveBeenCalledTimes(1)
      expect(logger.error).toHaveBeenCalledWith(expect.stringContaining('队列项排序请求失败'))
    })

    it('回滚函数本身失败时不抛异常', async () => {
      mockApi.getQueuesApiQueueGetPost.mockResolvedValue({
        code: 200,
        index: [],
        data: {},
      })
      mockApi.reorderItemApiQueueItemOrderPost.mockResolvedValue({
        code: 500,
        message: '服务器错误',
      })

      const { useQueueLogic } = await loadUseQueueLogic()
      const { reorderQueueItems, fetchQueues } = useQueueLogic()
      await fetchQueues()

      const rollbackFn = vi.fn().mockRejectedValue(new Error('回滚自身失败'))
      const result = await reorderQueueItems('queue-1', ['item-2', 'item-1'], rollbackFn)

      expect(result).toBe(false)
      expect(rollbackFn).toHaveBeenCalledTimes(1)
      // 回滚失败不应导致 reorderQueueItems 抛出异常
    })

    it('拖拽位置无变化时不需要调用 API（由 QueueItemManager 在 onDragEnd 中处理）', async () => {
      // 此测试验证 oldIndex === newIndex 时的语义由组件层处理
      // reorderQueueItems 本身不处理此逻辑，由 QueueItemManager.onDragEnd 的 early return 负责
      // 这里只验证 reorderQueueItems 可被正常调用
      mockApi.getQueuesApiQueueGetPost.mockResolvedValue({
        code: 200,
        index: [],
        data: {},
      })
      mockApi.reorderItemApiQueueItemOrderPost.mockResolvedValue({
        code: 200,
      })

      const { useQueueLogic } = await loadUseQueueLogic()
      const { reorderQueueItems, fetchQueues } = useQueueLogic()
      await fetchQueues()

      const rollbackFn = vi.fn().mockResolvedValue(undefined)
      const result = await reorderQueueItems('queue-1', ['item-1'], rollbackFn)

      expect(result).toBe(true)
      expect(mockApi.reorderItemApiQueueItemOrderPost).toHaveBeenCalledWith({
        queueId: 'queue-1',
        indexList: ['item-1'],
      })
    })
  })

  describe('cleanup', () => {
    it('cleanup 后调用不抛错', async () => {
      mockApi.getQueuesApiQueueGetPost.mockResolvedValue({
        code: 200,
        index: [],
        data: {},
      })

      const { useQueueLogic } = await loadUseQueueLogic()
      const { cleanup, fetchQueues } = useQueueLogic()
      cleanup()

      await fetchQueues()
    })
  })
})
