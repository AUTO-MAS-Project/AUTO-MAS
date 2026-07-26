import { type HistoryData, HistorySearchIn } from '@/api'
import { Service } from '@/api/services/Service'
import { useLogHighlight } from '@/composables/useLogHighlight'
import { message } from 'ant-design-vue'
import dayjs from 'dayjs'
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'

const logger = window.electronAPI.getLogger('历史记录')
const LIVE_REFRESH_INTERVAL_MS = 15_000

// 历史记录日期分组接口
export interface HistoryDateGroup {
  date: string
  users: Record<string, HistoryData>
}

// 扩展 HistoryIndexItem，补充后端实际返回但 OpenAPI 未声明的 task 字段
type HistoryIndexItemWithTask = {
  date: string
  jsonFile: string
  status: string
  task?: string
}

// 扁平化后的日志记录条目（用于 Console.app 风格日志列表）
export interface FlatLogRecord {
  /** 记录所属日期分组 key */
  groupDate: string
  /** 用户名 */
  username: string
  /** 原始记录 */
  record: HistoryIndexItemWithTask
  /** 该记录的错误信息（如有） */
  errorMessage: string
  /** 派生级别：error / info（后端历史只有 DONE/ERROR 两态，ERROR→error，DONE→info） */
  level: 'error' | 'info'
  /** 派生脚本标签：record.task 或 '默认' */
  script: string
}

// 级别筛选选项（仅错误/信息，与后端 DONE/ERROR 两态对应）
export type LevelFilter = 'all' | 'error' | 'info'

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
  const searchError = ref<string | null>(null)
  const activeKeys = ref<string[]>([])
  const currentPreset = ref('week')
  const searchKeyword = ref('')

  // 卸载守卫：防止组件卸载后 async 回调写入响应式状态
  let isMounted = true
  // 详情加载竞态防护：每次新请求递增 generation，旧响应自动丢弃
  let detailGeneration = 0

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

  // ==================== Console.app 风格筛选状态 ====================
  // 级别筛选（与工具栏分段控件联动）
  const levelFilter = ref<LevelFilter>('all')
  // 脚本筛选（侧栏「脚本」分组，多选）
  const selectedScripts = ref<Set<string>>(new Set())
  // 用户筛选（侧栏「用户」分组，单选；空字符串表示全部）
  const selectedUserFilter = ref<string>('')
  // 是否展示 Inspector 详情面板
  const inspectorVisible = ref(false)
  // 日志表格行高内开关：时间戳 / 自动换行 / 实时刷新
  const showTimestamp = ref(true)
  const wrapText = ref(false)
  const liveRefresh = ref(true)
  // 自动滚动到底部
  const autoScroll = ref(true)

  // 关键词筛选（本地过滤，不触发后端请求）
  const normalizedKeyword = computed(() => searchKeyword.value.trim().toLowerCase())
  const filteredHistoryData = computed<HistoryDateGroup[]>(() => {
    const kw = normalizedKeyword.value
    if (!kw) return historyData.value

    return historyData.value
      .map(group => {
        const filteredUsers: Record<string, HistoryData> = {}
        Object.entries(group.users).forEach(([username, userData]) => {
          if (username.toLowerCase().includes(kw)) {
            filteredUsers[username] = userData
            return
          }

          const records = userData.index ?? []
          const recordMatch = records.some(record => {
            const haystack = [record.jsonFile, record.status, record.date].filter(Boolean).join(' ')
            return haystack.toLowerCase().includes(kw)
          })

          const errorMatch = Object.values(userData.error_info ?? {}).some(msg =>
            msg.toLowerCase().includes(kw)
          )

          if (recordMatch || errorMatch) {
            filteredUsers[username] = userData
          }
        })

        return Object.keys(filteredUsers).length > 0
          ? { date: group.date, users: filteredUsers }
          : null
      })
      .filter((group): group is HistoryDateGroup => group !== null)
  })

  // ==================== Console.app 风格扁平化日志列表 ====================
  // 将 historyData (按日期/用户分组) 展平为单条日志记录列表，用于日志表格展示
  const flatRecords = computed<FlatLogRecord[]>(() => {
    const result: FlatLogRecord[] = []
    filteredHistoryData.value.forEach(group => {
      Object.entries(group.users).forEach(([username, userData]) => {
        const records = userData.index ?? []
        const errorInfo = userData.error_info ?? {}
        records.forEach(record => {
          // 后端实际返回的 task 字段未在 OpenAPI 中声明，此处做类型拓宽以读取
          const task = (record as HistoryIndexItemWithTask).task
          const errMsg = errorInfo[record.date] ?? ''
          const status = (record.status ?? '').toUpperCase()
          // 后端状态映射到日志级别：ERROR/FAILED → error；其余视为 info
          const level: FlatLogRecord['level'] =
            status === 'ERROR' || status === 'FAILED' ? 'error' : 'info'
          const script = task && task.trim() ? task : '默认'
          result.push({
            groupDate: group.date,
            username,
            record: record as HistoryIndexItemWithTask,
            errorMessage: errMsg,
            level,
            script,
          })
        })
      })
    })
    // 按时间倒序排列（最新的在前）
    return result.sort((a, b) => b.record.date.localeCompare(a.record.date))
  })

  // 应用侧栏筛选后的日志记录（级别 + 脚本 + 用户）
  const filteredFlatRecords = computed<FlatLogRecord[]>(() => {
    return flatRecords.value.filter(item => {
      // 级别筛选
      if (levelFilter.value !== 'all' && item.level !== levelFilter.value) return false
      // 脚本筛选（多选；为空表示全部）
      if (selectedScripts.value.size > 0 && !selectedScripts.value.has(item.script)) return false
      // 用户筛选（单选；空字符串表示全部）
      if (selectedUserFilter.value && item.username !== selectedUserFilter.value) return false
      return true
    })
  })

  // 侧栏「脚本」分组选项及计数
  const scriptFilterOptions = computed(() => {
    const counts = new Map<string, number>()
    flatRecords.value.forEach(item => {
      counts.set(item.script, (counts.get(item.script) ?? 0) + 1)
    })
    return Array.from(counts.entries()).map(([name, count]) => ({ name, count }))
  })

  // 侧栏「级别」分组选项及计数（错误=ERROR，信息=DONE）
  const levelFilterOptions = computed(() => {
    const counts = { error: 0, info: 0 }
    flatRecords.value.forEach(item => {
      counts[item.level] += 1
    })
    return [
      { key: 'error' as const, label: '错误', count: counts.error },
      { key: 'info' as const, label: '信息', count: counts.info },
    ]
  })

  // 侧栏「用户」分组选项及计数
  const userFilterOptions = computed(() => {
    const counts = new Map<string, number>()
    flatRecords.value.forEach(item => {
      counts.set(item.username, (counts.get(item.username) ?? 0) + 1)
    })
    return Array.from(counts.entries()).map(([name, count]) => ({ name, count }))
  })

  // 侧栏「日期」分组选项及计数（基于 historyData 各分组记录数）
  const dateFilterOptions = computed(() => {
    return filteredHistoryData.value.map(group => {
      let count = 0
      Object.values(group.users).forEach(userData => {
        count += (userData.index ?? []).length
      })
      return { date: group.date, count }
    })
  })

  // 当前选中的日志记录详情（供 Inspector 面板展示）
  const selectedRecordDetail = computed<FlatLogRecord | null>(() => {
    if (selectedRecordIndex.value < 0) return null
    const list = filteredFlatRecords.value
    if (selectedRecordIndex.value >= list.length) return null
    return list[selectedRecordIndex.value]
  })

  // 当前激活的筛选 chips 列表（用于子工具栏展示可移除的筛选条件）
  const activeFilterChips = computed(() => {
    const chips: Array<{ key: string; label: string; value: string; tone?: 'error' | 'info' }> = []
    if (levelFilter.value !== 'all') {
      const opt = levelFilterOptions.value.find(o => o.key === levelFilter.value)
      chips.push({
        key: 'level',
        label: '级别',
        value: opt?.label ?? levelFilter.value,
        tone: levelFilter.value === 'error' ? 'error' : 'info',
      })
    }
    selectedScripts.value.forEach(name => {
      chips.push({ key: `script:${name}`, label: '脚本', value: name })
    })
    if (selectedUserFilter.value) {
      chips.push({ key: 'user', label: '用户', value: selectedUserFilter.value })
    }
    if (currentPreset.value) {
      const preset = timePresets.find(p => p.key === currentPreset.value)
      if (preset) chips.push({ key: 'date', label: '日期', value: preset.label })
    }
    return chips
  })

  // 切换脚本筛选（多选）
  const toggleScriptFilter = (name: string) => {
    const next = new Set(selectedScripts.value)
    if (next.has(name)) next.delete(name)
    else next.add(name)
    selectedScripts.value = next
  }

  // 切换用户筛选（单选；再次点击同一用户取消）
  const toggleUserFilter = (name: string) => {
    selectedUserFilter.value = selectedUserFilter.value === name ? '' : name
  }

  // 移除指定筛选 chip
  const removeFilterChip = (key: string) => {
    if (key === 'level') {
      levelFilter.value = 'all'
    } else if (key === 'user') {
      selectedUserFilter.value = ''
    } else if (key === 'date') {
      currentPreset.value = ''
    } else if (key.startsWith('script:')) {
      const name = key.slice('script:'.length)
      const next = new Set(selectedScripts.value)
      next.delete(name)
      selectedScripts.value = next
    }
  }

  // 清空所有筛选
  const clearAllFilters = () => {
    levelFilter.value = 'all'
    selectedScripts.value = new Set()
    selectedUserFilter.value = ''
    searchKeyword.value = ''
  }

  // 搜索历史记录
  const handleSearch = async (options: { silent?: boolean } = {}) => {
    const silent = options.silent ?? false
    if (!searchForm.startDate || !searchForm.endDate) {
      if (!silent) message.error('请选择开始日期和结束日期')
      return
    }

    try {
      if (!silent) {
        searchLoading.value = true
        searchError.value = null
      }
      const response = await Service.searchHistoryApiHistorySearchPost({
        mode: searchForm.mode,
        start_date: searchForm.startDate,
        end_date: searchForm.endDate,
      })

      if (!isMounted) return

      if (response.code === 200) {
        historyData.value = Object.entries(response.data)
          .map(([date, users]) => ({ date, users }))
          .sort((a, b) => b.date.localeCompare(a.date))

        if (!silent) {
          const { useAudioPlayer } = await import('@/composables/useAudioPlayer')
          const { playSound } = useAudioPlayer()
          await playSound('history_query')

          if (!isMounted) return
          message.success('搜索完成')
        }
      } else {
        const msg = response.message || '搜索失败'
        if (silent) {
          logger.warn(`自动刷新历史记录失败: ${msg}`)
        } else {
          searchError.value = msg
          message.error(msg)
        }
      }
    } catch (error) {
      if (!isMounted) return
      const errorMsg = error instanceof Error ? error.message : String(error)
      if (silent) {
        logger.warn(`自动刷新历史记录异常: ${errorMsg}`)
      } else {
        searchError.value = errorMsg
        logger.error(`搜索历史记录失败: ${errorMsg}`)
        message.error('搜索历史记录失败')
      }
    } finally {
      if (isMounted && !silent) searchLoading.value = false
    }
  }

  // 重置搜索条件
  const handleReset = () => {
    searchForm.mode = HistorySearchIn.mode.DAILY
    searchForm.startDate = dayjs().subtract(7, 'day').format('YYYY-MM-DD')
    searchForm.endDate = dayjs().format('YYYY-MM-DD')
    searchKeyword.value = ''
    searchError.value = null
    historyData.value = []
    activeKeys.value = []
    selectedUser.value = ''
    selectedUserData.value = null
    selectedRecordIndex.value = -1
    currentDetail.value = null
    currentJsonFile.value = ''
    currentPreset.value = 'week'
    // 重置 Console.app 风格筛选状态
    levelFilter.value = 'all'
    selectedScripts.value = new Set()
    selectedUserFilter.value = ''
    inspectorVisible.value = false
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

  // 加载用户日志（带竞态防护）
  const loadUserLog = async (jsonFile: string) => {
    const gen = ++detailGeneration
    try {
      detailLoading.value = true
      const response = await Service.getHistoryDataApiHistoryDataPost({ jsonPath: jsonFile })

      if (!isMounted) return
      // 竞态检查：如果 generation 不匹配，说明有更新的请求已发起
      if (gen !== detailGeneration) return

      if (response.code === 200) {
        currentDetail.value = response.data
      } else {
        message.error(response.message || '获取详细日志失败')
        currentDetail.value = null
      }
    } catch (error) {
      if (!isMounted) return
      if (gen !== detailGeneration) return
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`获取历史记录详情失败: ${errorMsg}`)
      message.error('获取历史记录详情失败')
      currentDetail.value = null
    } finally {
      if (isMounted && gen === detailGeneration) detailLoading.value = false
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
      if (window.electronAPI && window.electronAPI.openFile) {
        await window.electronAPI.openFile(logFilePath)
        message.success('日志文件已打开')
      } else {
        message.error('当前环境不支持打开文件功能')
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`打开日志文件失败: ${errorMsg}`)
      message.error(`打开日志文件失败: ${errorMsg}`)
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
      if (window.electronAPI && window.electronAPI.showItemInFolder) {
        await window.electronAPI.showItemInFolder(logFilePath)
        message.success('日志文件目录已打开')
      } else {
        message.error('当前环境不支持打开目录功能')
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`打开日志文件目录失败: ${errorMsg}`)
      message.error(`打开日志文件目录失败: ${errorMsg}`)
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

  let liveRefreshTimer: ReturnType<typeof setInterval> | null = null

  const stopLiveRefresh = () => {
    if (liveRefreshTimer === null) return
    clearInterval(liveRefreshTimer)
    liveRefreshTimer = null
  }

  const startLiveRefresh = () => {
    stopLiveRefresh()
    if (!liveRefresh.value || !isMounted) return
    liveRefreshTimer = setInterval(() => {
      if (!searchLoading.value) void handleSearch({ silent: true })
    }, LIVE_REFRESH_INTERVAL_MS)
  }

  watch(liveRefresh, enabled => {
    if (enabled) startLiveRefresh()
    else stopLiveRefresh()
  })

  // 页面加载时自动搜索，并仅在启用“实时”时后台静默刷新。
  onMounted(() => {
    void handleSearch()
    startLiveRefresh()
  })

  onUnmounted(() => {
    isMounted = false
    stopLiveRefresh()
  })

  return {
    // 状态
    searchLoading,
    detailLoading,
    searchError,
    activeKeys,
    currentPreset,
    selectedUser,
    selectedUserData,
    selectedRecordIndex,
    currentDetail,
    currentJsonFile,
    searchForm,
    searchKeyword,
    historyData,
    filteredHistoryData,

    // Console.app 风格筛选状态
    levelFilter,
    selectedScripts,
    selectedUserFilter,
    inspectorVisible,
    showTimestamp,
    wrapText,
    liveRefresh,
    autoScroll,

    // Console.app 风格派生数据
    flatRecords,
    filteredFlatRecords,
    scriptFilterOptions,
    levelFilterOptions,
    userFilterOptions,
    dateFilterOptions,
    selectedRecordDetail,
    activeFilterChips,

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

    // Console.app 风格筛选方法
    toggleScriptFilter,
    toggleUserFilter,
    removeFilterChip,
    clearAllFilters,
  }
}
