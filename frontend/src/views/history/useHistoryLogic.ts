import { type HistoryData, HistorySearchIn } from '@/api'
import { Service } from '@/api/services/Service'
import { useLogHighlight } from '@/composables/useLogHighlight'
import { message } from 'ant-design-vue'
import dayjs from 'dayjs'
import { computed, onMounted, reactive, ref } from 'vue'

const logger = window.electronAPI.getLogger('历史记录')

// 历史记录日期分组接口
export interface HistoryDateGroup {
  date: string
  users: Record<string, HistoryData>
}

// 快捷时间预设
export const timePresets = [
  {
    key: 'today',
    label: '今天',
    startDate: () => dayjs().format('YYYY-MM-DD'),
    endDate: () => dayjs().format('YYYY-MM-DD'),
    mode: HistorySearchIn.mode.DAILY,
  },
  {
    key: 'yesterday',
    label: '昨天',
    startDate: () => dayjs().subtract(1, 'day').format('YYYY-MM-DD'),
    endDate: () => dayjs().subtract(1, 'day').format('YYYY-MM-DD'),
    mode: HistorySearchIn.mode.DAILY,
  },
  {
    key: 'week',
    label: '最近一周',
    startDate: () => dayjs().subtract(7, 'day').format('YYYY-MM-DD'),
    endDate: () => dayjs().format('YYYY-MM-DD'),
    mode: HistorySearchIn.mode.DAILY,
  },
  {
    key: 'month',
    label: '最近一个月',
    startDate: () => dayjs().subtract(1, 'month').format('YYYY-MM-DD'),
    endDate: () => dayjs().format('YYYY-MM-DD'),
    mode: HistorySearchIn.mode.WEEKLY,
  },
  {
    key: 'twoMonths',
    label: '最近两个月',
    startDate: () => dayjs().subtract(2, 'month').format('YYYY-MM-DD'),
    endDate: () => dayjs().format('YYYY-MM-DD'),
    mode: HistorySearchIn.mode.WEEKLY,
  },
  {
    key: 'threeMonths',
    label: '最近三个月',
    startDate: () => dayjs().subtract(3, 'month').format('YYYY-MM-DD'),
    endDate: () => dayjs().format('YYYY-MM-DD'),
    mode: HistorySearchIn.mode.MONTHLY,
  },
  {
    key: 'halfYear',
    label: '最近半年',
    startDate: () => dayjs().subtract(6, 'month').format('YYYY-MM-DD'),
    endDate: () => dayjs().format('YYYY-MM-DD'),
    mode: HistorySearchIn.mode.MONTHLY,
  },
]

export function useHistoryLogic() {
  // 响应式数据
  const searchLoading = ref(false)
  const detailLoading = ref(false)
  const activeKeys = ref<string[]>([])
  const currentPreset = ref('week')

  // 日志高亮
  const { registerLogLanguage, editorTheme, editorConfig, setEditorConfig } = useLogHighlight()

  // 字体大小选项
  const fontSizeOptions = [11, 12, 13, 14, 15, 16, 18, 20]

  // 选中的用户相关数据
  const selectedUser = ref('')
  const selectedUserData = ref<HistoryData | null>(null)
  const selectedRecordIndex = ref(-1)
  const currentDetail = ref<HistoryData | null>(null)
  const currentJsonFile = ref('')

  // 搜索表单
  const searchForm = reactive({
    mode: HistorySearchIn.mode.DAILY as HistorySearchIn.mode,
    startDate: dayjs().subtract(7, 'day').format('YYYY-MM-DD'),
    endDate: dayjs().format('YYYY-MM-DD'),
  })

  // 历史记录数据
  const historyData = ref<HistoryDateGroup[]>([])

  // 搜索历史记录
  const handleSearch = async () => {
    if (!searchForm.startDate || !searchForm.endDate) {
      message.error('请选择开始日期和结束日期')
      return
    }

    try {
      searchLoading.value = true
      const response = await Service.searchHistoryApiHistorySearchPost({
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
      logger.error('搜索历史记录失败:', error)
      message.error('搜索历史记录失败')
    } finally {
      searchLoading.value = false
    }
  }

  // 重置搜索条件
  const handleReset = () => {
    searchForm.mode = HistorySearchIn.mode.DAILY
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

  // 快捷时间选择处理
  const handleQuickTimeSelect = (preset: (typeof timePresets)[0]) => {
    currentPreset.value = preset.key
    searchForm.startDate = preset.startDate()
    searchForm.endDate = preset.endDate()
    searchForm.mode = preset.mode
    handleSearch()
  }

  // 日期变化处理
  const handleDateChange = () => {
    currentPreset.value = ''
  }

  // 选择用户处理
  const handleSelectUser = async (date: string, username: string, userData: HistoryData) => {
    selectedUser.value = `${date}-${username}`
    selectedUserData.value = userData
    selectedRecordIndex.value = -1
    currentDetail.value = null
    currentJsonFile.value = ''
  }

  // 选择记录处理
  const handleSelectRecord = async (index: number, record: any) => {
    selectedRecordIndex.value = index
    currentJsonFile.value = record.jsonFile
    await loadUserLog(record.jsonFile)
  }

  // 加载用户日志
  const loadUserLog = async (jsonFile: string) => {
    try {
      detailLoading.value = true
      const response = await Service.getHistoryDataApiHistoryDataPost({ jsonPath: jsonFile })

      if (response.code === 200) {
        currentDetail.value = response.data
      } else {
        message.error(response.message || '获取详细日志失败')
        currentDetail.value = null
      }
    } catch (error) {
      logger.error('获取历史记录详情失败:', error)
      message.error('获取历史记录详情失败')
      currentDetail.value = null
    } finally {
      detailLoading.value = false
    }
  }

  // 打开日志文件
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
      logger.error('打开日志文件失败:', error)
      message.error(`打开日志文件失败: ${error}`)
    }
  }

  // 打开日志文件所在目录
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
      logger.error('打开日志文件目录失败:', error)
      message.error(`打开日志文件目录失败: ${error}`)
    }
  }

  // Monaco Editor 配置
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

  // 页面加载时自动搜索
  onMounted(() => {
    handleSearch()
  })

  return {
    // 状态
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

    // 配置
    fontSizeOptions,
    editorConfig,
    editorTheme,
    monacoOptions,

    // 方法
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
