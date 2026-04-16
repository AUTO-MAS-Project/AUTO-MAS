import { message } from 'ant-design-vue'
import dayjs from 'dayjs'
import { computed, onMounted, reactive, ref } from 'vue'

import { HISTORY_SEARCH_MODE, historyApi, type HistoryData, type HistorySearchMode } from '@/api'
import { useLogHighlight } from '@/composables/useLogHighlight'

const logger = window.electronAPI.getLogger('history')

export interface HistoryDateGroup {
  date: string
  users: Record<string, HistoryData>
}

export const timePresets = [
  {
    key: 'today',
    label: '今天',
    startDate: () => dayjs().format('YYYY-MM-DD'),
    endDate: () => dayjs().format('YYYY-MM-DD'),
    mode: HISTORY_SEARCH_MODE.DAILY,
  },
  {
    key: 'yesterday',
    label: '昨天',
    startDate: () => dayjs().subtract(1, 'day').format('YYYY-MM-DD'),
    endDate: () => dayjs().subtract(1, 'day').format('YYYY-MM-DD'),
    mode: HISTORY_SEARCH_MODE.DAILY,
  },
  {
    key: 'week',
    label: '最近一周',
    startDate: () => dayjs().subtract(7, 'day').format('YYYY-MM-DD'),
    endDate: () => dayjs().format('YYYY-MM-DD'),
    mode: HISTORY_SEARCH_MODE.DAILY,
  },
  {
    key: 'month',
    label: '最近一个月',
    startDate: () => dayjs().subtract(1, 'month').format('YYYY-MM-DD'),
    endDate: () => dayjs().format('YYYY-MM-DD'),
    mode: HISTORY_SEARCH_MODE.WEEKLY,
  },
  {
    key: 'twoMonths',
    label: '最近两个月',
    startDate: () => dayjs().subtract(2, 'month').format('YYYY-MM-DD'),
    endDate: () => dayjs().format('YYYY-MM-DD'),
    mode: HISTORY_SEARCH_MODE.WEEKLY,
  },
  {
    key: 'threeMonths',
    label: '最近三个月',
    startDate: () => dayjs().subtract(3, 'month').format('YYYY-MM-DD'),
    endDate: () => dayjs().format('YYYY-MM-DD'),
    mode: HISTORY_SEARCH_MODE.MONTHLY,
  },
  {
    key: 'halfYear',
    label: '最近半年',
    startDate: () => dayjs().subtract(6, 'month').format('YYYY-MM-DD'),
    endDate: () => dayjs().format('YYYY-MM-DD'),
    mode: HISTORY_SEARCH_MODE.MONTHLY,
  },
]

export function useHistoryLogic() {
  const searchLoading = ref(false)
  const detailLoading = ref(false)
  const activeKeys = ref<string[]>([])
  const currentPreset = ref('week')

  const { registerLogLanguage, editorTheme, editorConfig, setEditorConfig } = useLogHighlight()

  const fontSizeOptions = [11, 12, 13, 14, 15, 16, 18, 20]

  const selectedUser = ref('')
  const selectedUserData = ref<HistoryData | null>(null)
  const selectedRecordIndex = ref(-1)
  const currentDetail = ref<HistoryData | null>(null)
  const currentJsonFile = ref('')

  const searchForm = reactive<{
    mode: HistorySearchMode
    startDate: string
    endDate: string
  }>({
    mode: HISTORY_SEARCH_MODE.DAILY,
    startDate: dayjs().subtract(7, 'day').format('YYYY-MM-DD'),
    endDate: dayjs().format('YYYY-MM-DD'),
  })

  const historyData = ref<HistoryDateGroup[]>([])

  const handleSearch = async () => {
    if (!searchForm.startDate || !searchForm.endDate) {
      message.error('请选择开始日期和结束日期')
      return
    }

    try {
      searchLoading.value = true
      const response = await historyApi.search({
        mode: searchForm.mode,
        start_date: searchForm.startDate,
        end_date: searchForm.endDate,
      })

      if (response.code === 200) {
        historyData.value = Object.entries(response.data)
          .map(([date, users]) => ({ date, users }))
          .sort((a, b) => b.date.localeCompare(a.date))

        const { useAudioPlayer } = await import('@/composables/useAudioPlayer')
        const { playSound } = useAudioPlayer()
        await playSound('history_query')

        message.success('搜索完成')
      } else {
        message.error(response.message || '搜索失败')
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`Search history failed: ${errorMsg}`)
      message.error('搜索历史记录失败')
    } finally {
      searchLoading.value = false
    }
  }

  const handleReset = () => {
    searchForm.mode = HISTORY_SEARCH_MODE.DAILY
    searchForm.startDate = dayjs().subtract(7, 'day').format('YYYY-MM-DD')
    searchForm.endDate = dayjs().format('YYYY-MM-DD')
    historyData.value = []
    activeKeys.value = []
    selectedUser.value = ''
    selectedUserData.value = null
    selectedRecordIndex.value = -1
    currentDetail.value = null
    currentJsonFile.value = ''
    currentPreset.value = 'week'
  }

  const handleQuickTimeSelect = (preset: (typeof timePresets)[0]) => {
    currentPreset.value = preset.key
    searchForm.startDate = preset.startDate()
    searchForm.endDate = preset.endDate()
    searchForm.mode = preset.mode
    handleSearch()
  }

  const handleDateChange = () => {
    currentPreset.value = ''
  }

  const handleSelectUser = async (date: string, username: string, userData: HistoryData) => {
    selectedUser.value = `${date}-${username}`
    selectedUserData.value = userData
    selectedRecordIndex.value = -1
    currentDetail.value = null
    currentJsonFile.value = ''
  }

  const handleSelectRecord = async (index: number, record: any) => {
    selectedRecordIndex.value = index
    currentJsonFile.value = record.jsonFile
    await loadUserLog(record.jsonFile)
  }

  const loadUserLog = async (jsonFile: string) => {
    try {
      detailLoading.value = true
      const response = await historyApi.getData({ jsonPath: jsonFile })

      if (response.code === 200) {
        currentDetail.value = response.data
      } else {
        message.error(response.message || '获取详细日志失败')
        currentDetail.value = null
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`Load history detail failed: ${errorMsg}`)
      message.error('获取历史记录详情失败')
      currentDetail.value = null
    } finally {
      detailLoading.value = false
    }
  }

  const handleOpenLogFile = async () => {
    if (!currentJsonFile.value) {
      message.warning('请先选择一条记录')
      return
    }

    try {
      const logFilePath = currentJsonFile.value.replace(/\.json$/, '.log')
      if (window.electronAPI && (window.electronAPI as any).openFile) {
        await (window.electronAPI as any).openFile(logFilePath)
        message.success('日志文件已打开')
      } else {
        message.error('当前环境不支持打开文件功能')
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`Open log file failed: ${errorMsg}`)
      message.error(`打开日志文件失败: ${errorMsg}`)
    }
  }

  const handleOpenLogDirectory = async () => {
    if (!currentJsonFile.value) {
      message.warning('请先选择一条记录')
      return
    }

    try {
      const logFilePath = currentJsonFile.value.replace(/\.json$/, '.log')
      if (window.electronAPI && (window.electronAPI as any).showItemInFolder) {
        await (window.electronAPI as any).showItemInFolder(logFilePath)
        message.success('日志文件目录已打开')
      } else {
        message.error('当前环境不支持打开目录功能')
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`Open log directory failed: ${errorMsg}`)
      message.error(`打开日志文件目录失败: ${errorMsg}`)
    }
  }

  const monacoOptions = computed(() => ({
    readOnly: true,
    fontSize: editorConfig.value.fontSize,
    fontFamily: 'SFMono-Regular, Consolas, Liberation Mono, Menlo, Courier, monospace',
    lineHeight: editorConfig.value.lineHeight * editorConfig.value.fontSize,
    wordWrap: 'on' as const,
    scrollBeyondLastLine: false,
    minimap: { enabled: false },
    scrollbar: {
      vertical: 'auto' as const,
      horizontal: 'auto' as const,
      verticalScrollbarSize: 8,
      horizontalScrollbarSize: 8,
    },
    find: { addExtraSpaceOnTop: false },
    automaticLayout: true,
    unicodeHighlight: {
      ambiguousCharacters: false,
      invisibleCharacters: false,
    },
  }))

  onMounted(() => {
    handleSearch()
  })

  return {
    searchLoading,
    detailLoading,
    activeKeys,
    currentPreset,
    selectedUser,
    selectedUserData,
    selectedRecordIndex,
    currentDetail,
    currentJsonFile,
    searchForm,
    historyData,

    fontSizeOptions,
    editorConfig,
    editorTheme,
    monacoOptions,

    handleSearch,
    handleReset,
    handleQuickTimeSelect,
    handleDateChange,
    handleSelectUser,
    handleSelectRecord,
    handleOpenLogFile,
    handleOpenLogDirectory,
    registerLogLanguage,
    setEditorConfig,
  }
}
