import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick, ref } from 'vue'
import { HistorySearchIn } from '@/api'

const logger = { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() }

const mockService = vi.hoisted(() => ({
  searchHistoryApiHistorySearchPost: vi.fn(),
  getHistoryDataApiHistoryDataPost: vi.fn(),
}))

vi.mock('@/api/services/Service', () => ({ Service: mockService }))
vi.mock('ant-design-vue', () => ({
  message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
}))
vi.mock('@/composables/useLogHighlight', () => ({
  useLogHighlight: () => ({
    registerLogLanguage: vi.fn(),
    editorTheme: ref('vs'),
    editorConfig: ref({ fontSize: 14, lineHeight: 1.5 }),
    setEditorConfig: vi.fn(),
  }),
}))

const loadUseHistoryLogic = async () => {
  vi.stubGlobal('window', {
    electronAPI: {
      getLogger: () => logger,
      openFile: vi.fn(),
      showItemInFolder: vi.fn(),
    },
  })
  vi.resetModules()
  return import('../useHistoryLogic')
}

const flushPromises = async () => {
  await Promise.resolve()
  await Promise.resolve()
}

describe('useHistoryLogic', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  const makeSampleData = () => ({
    '2026-07-24': {
      alice: {
        index: [
          {
            date: '2026-07-24T10:00:00',
            jsonFile: '/logs/2026-07-24/alice.json',
            status: 'success',
            task: 'daily',
          },
          {
            date: '2026-07-24T11:00:00',
            jsonFile: '/logs/2026-07-24/alice_2.json',
            status: 'error',
            task: 'extra',
          },
        ],
        error_info: { '2026-07-24T11:00:00': 'timeout' },
      },
      bob: {
        index: [
          {
            date: '2026-07-24T09:00:00',
            jsonFile: '/logs/2026-07-24/bob.json',
            status: 'success',
            task: 'daily',
          },
        ],
        error_info: {},
      },
    },
    '2026-07-23': {
      alice: {
        index: [
          {
            date: '2026-07-23T10:00:00',
            jsonFile: '/logs/2026-07-23/alice.json',
            status: 'success',
            task: 'daily',
          },
        ],
        error_info: {},
      },
    },
  })

  it('调用搜索后按日期降序排列', async () => {
    mockService.searchHistoryApiHistorySearchPost.mockResolvedValue({
      code: 200,
      data: makeSampleData(),
    })

    const { useHistoryLogic } = await loadUseHistoryLogic()
    const { historyData, searchLoading, handleSearch } = useHistoryLogic()

    await handleSearch()
    await flushPromises()

    expect(searchLoading.value).toBe(false)
    expect(historyData.value).toHaveLength(2)
    expect(historyData.value[0].date).toBe('2026-07-24')
    expect(historyData.value[1].date).toBe('2026-07-23')
  })

  it('按用户名关键词本地过滤', async () => {
    mockService.searchHistoryApiHistorySearchPost.mockResolvedValue({
      code: 200,
      data: makeSampleData(),
    })

    const { useHistoryLogic } = await loadUseHistoryLogic()
    const { searchKeyword, filteredHistoryData, handleSearch } = useHistoryLogic()

    await handleSearch()
    await flushPromises()
    expect(filteredHistoryData.value.length).toBe(2)

    searchKeyword.value = 'bob'
    await nextTick()

    expect(filteredHistoryData.value).toHaveLength(1)
    expect(filteredHistoryData.value[0].users).toHaveProperty('bob')
  })

  it('按记录状态关键词本地过滤', async () => {
    mockService.searchHistoryApiHistorySearchPost.mockResolvedValue({
      code: 200,
      data: makeSampleData(),
    })

    const { useHistoryLogic } = await loadUseHistoryLogic()
    const { searchKeyword, filteredHistoryData, handleSearch } = useHistoryLogic()

    await handleSearch()
    await flushPromises()
    expect(filteredHistoryData.value.length).toBe(2)

    searchKeyword.value = 'error'
    await nextTick()

    expect(filteredHistoryData.value).toHaveLength(1)
    expect(filteredHistoryData.value[0].users).toHaveProperty('alice')
    expect(filteredHistoryData.value[0].users.alice.index).toHaveLength(2)
  })

  it('按错误信息关键词本地过滤', async () => {
    mockService.searchHistoryApiHistorySearchPost.mockResolvedValue({
      code: 200,
      data: makeSampleData(),
    })

    const { useHistoryLogic } = await loadUseHistoryLogic()
    const { searchKeyword, filteredHistoryData, handleSearch } = useHistoryLogic()

    await handleSearch()
    await flushPromises()
    expect(filteredHistoryData.value.length).toBe(2)

    searchKeyword.value = 'timeout'
    await nextTick()

    expect(filteredHistoryData.value).toHaveLength(1)
    expect(filteredHistoryData.value[0].users).toHaveProperty('alice')
  })

  it('级别选项仅有错误/信息两段，且与后端 DONE/ERROR 两态一一对应', async () => {
    mockService.searchHistoryApiHistorySearchPost.mockResolvedValue({
      code: 200,
      data: {
        '2026-07-24': {
          alice: {
            index: [
              {
                date: '2026-07-24T10:00:00',
                jsonFile: '/logs/2026-07-24/alice.json',
                status: 'DONE',
                task: 'daily',
              },
              {
                date: '2026-07-24T11:00:00',
                jsonFile: '/logs/2026-07-24/alice_2.json',
                status: 'ERROR',
                task: 'extra',
              },
            ],
            error_info: { '2026-07-24T11:00:00': 'timeout' },
          },
        },
      },
    })

    const { useHistoryLogic } = await loadUseHistoryLogic()
    const { levelFilter, levelFilterOptions, filteredFlatRecords, handleSearch } = useHistoryLogic()

    await handleSearch()
    await flushPromises()

    // 不再提供永远匹配不到的「调试」段
    expect(levelFilterOptions.value.map(o => o.key)).toEqual(['error', 'info'])
    expect(levelFilterOptions.value.map(o => o.label)).toEqual(['错误', '信息'])
    expect(levelFilterOptions.value.find(o => o.key === 'error')?.count).toBe(1)
    expect(levelFilterOptions.value.find(o => o.key === 'info')?.count).toBe(1)

    // 错误=ERROR
    levelFilter.value = 'error'
    await nextTick()
    expect(filteredFlatRecords.value).toHaveLength(1)
    expect(filteredFlatRecords.value[0].record.status).toBe('ERROR')
    expect(filteredFlatRecords.value[0].level).toBe('error')

    // 信息=DONE
    levelFilter.value = 'info'
    await nextTick()
    expect(filteredFlatRecords.value).toHaveLength(1)
    expect(filteredFlatRecords.value[0].record.status).toBe('DONE')
    expect(filteredFlatRecords.value[0].level).toBe('info')
  })

  it('重置清空所有状态', async () => {
    mockService.searchHistoryApiHistorySearchPost.mockResolvedValue({
      code: 200,
      data: makeSampleData(),
    })

    const { useHistoryLogic } = await loadUseHistoryLogic()
    const {
      searchKeyword,
      historyData,
      activeKeys,
      selectedUser,
      currentPreset,
      handleReset,
      handleSearch,
    } = useHistoryLogic()

    await handleSearch()
    await flushPromises()
    expect(historyData.value.length).toBe(2)
    searchKeyword.value = 'alice'
    activeKeys.value = ['key']
    selectedUser.value = 'some'

    handleReset()

    expect(searchKeyword.value).toBe('')
    expect(historyData.value).toEqual([])
    expect(activeKeys.value).toEqual([])
    expect(selectedUser.value).toBe('')
    expect(currentPreset.value).toBe('week')
  })

  it('快捷时间选择更新表单并触发搜索', async () => {
    mockService.searchHistoryApiHistorySearchPost.mockResolvedValue({ code: 200, data: {} })

    const { useHistoryLogic, timePresets } = await loadUseHistoryLogic()
    const { searchForm, currentPreset, handleQuickTimeSelect } = useHistoryLogic()

    const todayPreset = timePresets.find(p => p.key === 'today')
    expect(todayPreset).toBeDefined()

    handleQuickTimeSelect(todayPreset!)

    expect(currentPreset.value).toBe('today')
    expect(searchForm.mode).toBe(HistorySearchIn.mode.DAILY)
    expect(mockService.searchHistoryApiHistorySearchPost).toHaveBeenCalled()
  })

  it('搜索失败时设置错误状态', async () => {
    mockService.searchHistoryApiHistorySearchPost.mockRejectedValue(new Error('history down'))

    const { useHistoryLogic } = await loadUseHistoryLogic()
    const { searchError, searchLoading, handleSearch } = useHistoryLogic()

    await handleSearch()
    await flushPromises()

    expect(searchLoading.value).toBe(false)
    expect(searchError.value).toBe('history down')
    expect(logger.error).toHaveBeenCalledWith(expect.stringContaining('history down'))
  })

  it('选择用户后记录当前用户数据', async () => {
    mockService.searchHistoryApiHistorySearchPost.mockResolvedValue({
      code: 200,
      data: makeSampleData(),
    })

    const { useHistoryLogic } = await loadUseHistoryLogic()
    const { historyData, selectedUser, selectedUserData, handleSelectUser, handleSearch } =
      useHistoryLogic()

    await handleSearch()
    await flushPromises()

    const userData = historyData.value[0].users.alice
    await handleSelectUser('2026-07-24', 'alice', userData)

    expect(selectedUser.value).toBe('2026-07-24-alice')
    expect(selectedUserData.value).toBe(userData)
  })

  it('选择记录加载详情日志', async () => {
    mockService.searchHistoryApiHistorySearchPost.mockResolvedValue({
      code: 200,
      data: makeSampleData(),
    })
    mockService.getHistoryDataApiHistoryDataPost.mockResolvedValue({
      code: 200,
      data: { log_content: 'log line 1\nlog line 2' },
    })

    const { useHistoryLogic } = await loadUseHistoryLogic()
    const {
      historyData,
      currentDetail,
      currentJsonFile,
      detailLoading,
      handleSelectRecord,
      handleSearch,
    } = useHistoryLogic()

    await handleSearch()
    await flushPromises()

    const record = historyData.value[0]?.users?.alice?.index?.[0]
    expect(record).toBeDefined()
    if (!record) return
    await handleSelectRecord(0, record)
    await flushPromises()

    expect(currentJsonFile.value).toBe(record.jsonFile)
    expect(currentDetail.value).toEqual({ log_content: 'log line 1\nlog line 2' })
    expect(detailLoading.value).toBe(false)
  })

  it('详情加载失败时清空当前详情', async () => {
    mockService.searchHistoryApiHistorySearchPost.mockResolvedValue({
      code: 200,
      data: makeSampleData(),
    })
    mockService.getHistoryDataApiHistoryDataPost.mockRejectedValue(new Error('detail timeout'))

    const { useHistoryLogic } = await loadUseHistoryLogic()
    const { historyData, currentDetail, detailLoading, handleSelectRecord, handleSearch } =
      useHistoryLogic()

    await handleSearch()
    await flushPromises()

    const record = historyData.value[0]?.users?.alice?.index?.[0]
    expect(record).toBeDefined()
    if (!record) return
    await handleSelectRecord(0, record)
    await flushPromises()

    expect(detailLoading.value).toBe(false)
    expect(currentDetail.value).toBeNull()
    expect(logger.error).toHaveBeenCalledWith(expect.stringContaining('detail timeout'))
  })
})
