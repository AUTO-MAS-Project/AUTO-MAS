import { analyticsCountBucket } from '@/utils/analytics'
import { apiOutcome, observeFeature } from '@/utils/featureAnalytics'
import {
  type HistoryBucket,
  type HistoryDetail,
  type HistoryIndexItem,
  HistorySearchIn,
  ApiError,
  GetService,
} from '@/api'
import { useI18n } from 'vue-i18n'
import { Service } from '@/api/services/Service'
import { useLogHighlight } from '@/composables/useLogHighlight'
import { message } from 'ant-design-vue'
import dayjs from 'dayjs'
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'

const logger = window.electronAPI.getLogger('历史记录')

// 历史记录日期分组接口
export interface HistoryDateGroup {
  date: string
  users: Record<string, HistoryBucket>
}

// 快捷时间预设。label 仅为代码内可读标识，界面显示走 history.preset.<key>
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
  const { t } = useI18n()

  // 响应式数据
  const searchLoading = ref(false)
  const detailLoading = ref(false)
  const activeKeys = ref<string[]>([])
  const currentPreset = ref('week')

  // 卸载守卫：防止组件卸载后 async 回调写入响应式状态
  let isMounted = true

  // 日志高亮
  const { registerLogLanguage, editorTheme, editorConfig, setEditorConfig } = useLogHighlight()

  // 字体大小选项
  const fontSizeOptions = [11, 12, 13, 14, 15, 16, 18, 20]

  // 选中的用户相关数据
  const selectedUser = ref('')
  const selectedUserData = ref<HistoryBucket | null>(null)
  const currentDetail = ref<HistoryDetail | null>(null)
  const currentRecordId = ref<string | null>(null)

  // 同一天内记录条目的顺序，来自设置页「历史记录条目顺序」。只在进页面时读一次，和查询互不等待：
  // 设置回来之前按默认的最新在前显示，回来后只重排当前列表。读不到也按默认，不弹错误——
  // 排序只是偏好，不该挡住历史记录本身。
  const newestFirst = ref(true)
  const loadHistoryOrder = async () => {
    try {
      const response = await GetService.getScriptsApiSettingGetPost()
      if (isMounted && response.code === 200)
        newestFirst.value = response.data?.Function?.HistoryOrder !== 'asc'
    } catch {
      // 保持默认顺序
    }
  }

  // 后端按时间正序返回记录条目；默认倒过来，点进日志时最先看到的应该是最近一次
  const selectedRecords = computed<HistoryIndexItem[]>(() => {
    const records = selectedUserData.value?.index ?? []
    return newestFirst.value ? [...records].reverse() : records
  })
  // 按记录 id 找高亮位置，顺序晚到重排时高亮仍跟着同一条记录
  const selectedRecordIndex = computed(() =>
    currentRecordId.value === null
      ? -1
      : selectedRecords.value.findIndex(record => record.id === currentRecordId.value)
  )

  // 搜索表单
  const searchForm = reactive({
    mode: HistorySearchIn.mode.DAILY as HistorySearchIn.mode,
    startDate: dayjs().subtract(7, 'day').format('YYYY-MM-DD'),
    endDate: dayjs().format('YYYY-MM-DD'),
  })

  // 历史记录数据
  const historyData = ref<HistoryDateGroup[]>([])

  // 只有最新一轮搜索能写列表、结束加载：快捷筛选连点时，先发的慢请求不能把旧范围写回来
  let searchSeq = 0

  // 搜索历史记录
  const handleSearch = async () => {
    if (!searchForm.startDate || !searchForm.endDate) {
      message.error(t('core.history.toast.needDateRange'))
      return
    }

    const seq = ++searchSeq
    const isCurrent = () => isMounted && seq === searchSeq
    try {
      searchLoading.value = true
      const response = await observeFeature(
        'history_query_finished',
        { filter_kind: currentPreset.value === 'week' ? 'default' : 'filtered', count_bucket: '0' },
        () =>
          Service.searchHistoryApiHistorySearchPost({
            mode: searchForm.mode,
            start_date: searchForm.startDate,
            end_date: searchForm.endDate,
          }),
        result => ({
          outcome: apiOutcome(result),
          count_bucket: analyticsCountBucket(
            Object.values(result.data ?? {}).reduce(
              (sum, users) =>
                sum +
                Object.values(users).reduce((count, user) => count + (user.index?.length ?? 0), 0),
              0
            )
          ),
        })
      )

      if (!isCurrent()) return

      if (response.code === 200) {
        selectedUser.value = ''
        selectedUserData.value = null
        currentRecordId.value = null
        currentDetail.value = null
        // 记录条目保持后端的时间正序，显示顺序由 selectedRecords 按设置决定
        historyData.value = Object.entries(response.data)
          .map(([date, users]) => ({ date, users }))
          .sort((a, b) => b.date.localeCompare(a.date))

        const { useAudioPlayer } = await import('@/composables/useAudioPlayer')
        const { playSound } = useAudioPlayer()
        // 提示不等音频：播放前还要查设置、探文件，用户只关心结果已经出来了
        void playSound('history_query')

        if (!isCurrent()) return
        message.success(t('core.history.toast.searchDone'))
      } else {
        message.error(response.message || t('core.history.toast.searchFailed'))
      }
    } catch (error) {
      if (!isCurrent()) return
      const errorMsg =
        error instanceof ApiError && typeof error.body?.message === 'string'
          ? error.body.message
          : error instanceof Error
            ? error.message
            : String(error)
      logger.error(`搜索历史记录失败: ${errorMsg}`)
      message.error(t('core.history.toast.searchHistoryFailed'))
    } finally {
      if (isCurrent()) searchLoading.value = false
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
    currentDetail.value = null
    currentRecordId.value = null
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

  // 选择用户处理（key 由侧栏给出：日期与用户名）
  const handleSelectUser = async (key: string, userData: HistoryBucket) => {
    selectedUser.value = key
    selectedUserData.value = userData
    currentDetail.value = null
    currentRecordId.value = null
  }

  // 选择记录处理（高亮位置由 selectedRecordIndex 按 id 推出，这里只记 id）
  const handleSelectRecord = async (_index: number, record: HistoryIndexItem) => {
    currentRecordId.value = record.id
    currentDetail.value = null
    await loadUserLog(record.id)
  }

  // 加载用户日志
  const loadUserLog = async (recordId: string) => {
    try {
      detailLoading.value = true
      const response = await Service.getHistoryDetailApiHistoryDetailPost({ recordId })

      if (!isMounted || currentRecordId.value !== recordId) return

      if (response.code === 200) {
        currentDetail.value = response.data
      } else {
        message.error(response.message || t('core.history.toast.fetchLogFailed'))
        currentDetail.value = null
      }
    } catch (error) {
      if (!isMounted || currentRecordId.value !== recordId) return
      const errorMsg =
        error instanceof ApiError && typeof error.body?.message === 'string'
          ? error.body.message
          : error instanceof Error
            ? error.message
            : String(error)
      logger.error(`获取历史记录详情失败: ${errorMsg}`)
      message.error(t('core.history.toast.fetchDetailFailed'))
      currentDetail.value = null
    } finally {
      if (isMounted && currentRecordId.value === recordId) detailLoading.value = false
    }
  }

  // 完整日志可能仅存在数据库中，下载详情内容不依赖本机归档路径。
  const handleOpenLogFile = () => {
    if (currentDetail.value?.log_content == null) return
    const url = URL.createObjectURL(
      new Blob([currentDetail.value.log_content], { type: 'text/plain;charset=utf-8' })
    )
    const link = document.createElement('a')
    link.href = url
    link.download = `history-${currentRecordId.value}.log`
    link.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
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
    void loadHistoryOrder()
    handleSearch()
  })

  onUnmounted(() => {
    isMounted = false
  })

  return {
    // 状态
    searchLoading,
    detailLoading,
    activeKeys,
    currentPreset,
    selectedUser,
    selectedUserData,
    selectedRecords,
    selectedRecordIndex,
    currentDetail,
    currentRecordId,
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
    registerLogLanguage,
    setEditorConfig,
  }
}
