<template>
  <div class="history-header">
    <div class="header-title">
      <h1>历史记录</h1>
    </div>
  </div>

  <!-- 搜索筛选区域 -->
  <div class="search-section">
    <a-card size="small" title="筛选条件">
      <!-- 快捷时间选择 -->
      <div class="quick-time-section">
        <a-form-item label="快捷选择" style="margin-bottom: 16px">
          <a-space wrap>
            <a-button
              v-for="preset in timePresets"
              :key="preset.key"
              :type="currentPreset === preset.key ? 'primary' : 'default'"
              size="middle"
              @click="handleQuickTimeSelect(preset)"
            >
              {{ preset.label }}
            </a-button>
          </a-space>
        </a-form-item>
      </div>

      <!-- 详细筛选条件 -->
      <a-row :gutter="16" :align="'middle'">
        <a-col :span="6">
          <a-form-item label="合并模式" style="margin-bottom: 0">
            <a-select v-model:value="searchForm.mode" style="width: 100%">
              <a-select-option value="按日合并">按日合并</a-select-option>
              <a-select-option value="按周合并">按周合并</a-select-option>
              <a-select-option value="按月合并">按月合并</a-select-option>
            </a-select>
          </a-form-item>
        </a-col>
        <a-col :span="6">
          <a-form-item label="开始日期" style="margin-bottom: 0">
            <a-date-picker
              v-model:value="searchForm.startDate"
              style="width: 100%"
              format="YYYY-MM-DD"
              value-format="YYYY-MM-DD"
              @change="handleDateChange"
            />
          </a-form-item>
        </a-col>
        <a-col :span="6">
          <a-form-item label="结束日期" style="margin-bottom: 0">
            <a-date-picker
              v-model:value="searchForm.endDate"
              style="width: 100%"
              format="YYYY-MM-DD"
              value-format="YYYY-MM-DD"
              @change="handleDateChange"
            />
          </a-form-item>
        </a-col>
        <a-col :span="6">
          <a-form-item label=" " style="margin-bottom: 0" :colon="false">
            <a-space>
              <a-button type="primary" :loading="searchLoading" @click="handleSearch">
                <template #icon>
                  <SearchOutlined />
                </template>
                搜索
              </a-button>
              <a-button @click="handleReset">
                <template #icon>
                  <ClearOutlined />
                </template>
                重置
              </a-button>
            </a-space>
          </a-form-item>
        </a-col>
      </a-row>
    </a-card>
  </div>

  <!-- 历史记录内容区域 -->
  <div class="history-content">
    <a-spin :spinning="searchLoading">
      <div v-if="historyData.length === 0 && !searchLoading" class="empty-state">
        <img src="@/assets/NoData.png" alt="无数据" class="empty-image" />
      </div>

      <div v-else class="history-layout">
        <!-- 左侧日期列表 -->
        <div class="date-sidebar">
          <!-- 日期折叠列表 -->
          <div class="date-list">
            <a-collapse v-model:active-key="activeKeys" ghost accordion>
              <a-collapse-panel
                v-for="dateGroup in historyData"
                :key="dateGroup.date"
                class="date-panel"
              >
                <template #header>
                  <div class="date-header">
                    <span class="date-text">{{ dateGroup.date }}</span>
                  </div>
                </template>

                <div class="user-list">
                  <div
                    v-for="(userData, username) in dateGroup.users"
                    :key="username"
                    class="user-item"
                    :class="{ active: selectedUser === `${dateGroup.date}-${username}` }"
                    @click="handleSelectUser(dateGroup.date, username, userData)"
                  >
                    <div class="user-info">
                      <span class="username">{{ username }}</span>
                    </div>
                  </div>
                </div>
              </a-collapse-panel>
            </a-collapse>
          </div>
        </div>

        <!-- 右侧详情区域 -->
        <div class="detail-area">
          <div v-if="!selectedUserData" class="no-selection">
            <a-empty description="请选择左侧的用户查看详细信息">
              <template #image>
                <FileSearchOutlined style="font-size: 64px; color: #d9d9d9" />
              </template>
            </a-empty>
          </div>

          <div v-else class="detail-content">
            <!-- 中间：记录条目和统计数据 -->
            <div class="records-area">
              <!-- 记录条目列表 -->
              <div class="records-section">
                <a-card size="small" title="记录条目" class="records-card">
                  <template #extra>
                    <a-space>
                      <span class="record-count"
                        >{{ selectedUserData.index?.length || 0 }} 条记录</span
                      >
                      <a-popover>
                        <template #content>
                          <p>计时规则：4:00-28:00</p>
                        </template>
                        <HistoryOutlined />
                      </a-popover>
                    </a-space>
                  </template>
                  <div class="records-list">
                    <div
                      v-for="(record, index) in selectedUserData.index || []"
                      :key="record.jsonFile"
                      class="record-item"
                      :class="{
                        active: selectedRecordIndex === index,
                        success: record.status === '完成',
                        error: record.status === '异常',
                      }"
                      @click="handleSelectRecord(index, record)"
                    >
                      <div class="record-info">
                        <div class="record-header">
                          <span class="record-time">{{ record.date }}</span>
                          <a-tooltip
                            v-if="
                              record.status === '异常' &&
                              selectedUserData?.error_info &&
                              selectedUserData.error_info[record.date]
                            "
                            :title="selectedUserData.error_info[record.date]"
                            placement="topLeft"
                          >
                            <a-tag color="error" size="small" class="error-tag-with-tooltip">
                              {{ record.status }}
                            </a-tag>
                          </a-tooltip>
                          <a-tag
                            v-else
                            :color="record.status === '完成' ? 'success' : 'error'"
                            size="small"
                          >
                            {{ record.status }}
                          </a-tag>
                        </div>
                        <div class="record-file">{{ record.jsonFile }}</div>
                      </div>
                      <div class="record-indicator">
                        <RightOutlined v-if="selectedRecordIndex === index" />
                      </div>
                    </div>
                  </div>
                </a-card>
              </div>

              <!-- 统计数据 -->
              <div class="statistics-section">
                <!-- 公招统计 -->
                <a-card size="small" class="stat-card">
                  <template #title>
                    <span>公招统计</span>
                    <span v-if="selectedRecordIndex >= 0" class="stat-subtitle">（当前记录）</span>
                    <span v-else class="stat-subtitle">（用户总计）</span>
                  </template>
                  <template #extra>
                    <UserOutlined />
                  </template>
                  <div v-if="currentStatistics.recruit_statistics" class="recruit-stats">
                    <a-row :gutter="8">
                      <a-col
                        v-for="(count, star) in currentStatistics.recruit_statistics"
                        :key="star"
                        :span="8"
                      >
                        <a-statistic
                          :title="`${star}星`"
                          :value="count"
                          :value-style="{ fontSize: '16px' }"
                        />
                      </a-col>
                    </a-row>
                  </div>
                  <div v-else class="no-data">
                    <a-empty
                      description="暂无公招数据"
                      :image="NodataImage"
                      :image-style="{
                        height: '60px',
                      }"
                    />
                  </div>
                </a-card>

                <!-- 掉落统计 -->
                <a-card size="small" class="stat-card">
                  <template #title>
                    <span>掉落统计</span>
                    <span v-if="selectedRecordIndex >= 0" class="stat-subtitle">（当前记录）</span>
                    <span v-else class="stat-subtitle">（用户总计）</span>
                  </template>
                  <template #extra>
                    <GiftOutlined />
                  </template>
                  <div v-if="currentStatistics.drop_statistics" class="drop-stats">
                    <a-collapse size="small" ghost>
                      <a-collapse-panel
                        v-for="(drops, stage) in currentStatistics.drop_statistics"
                        :key="stage"
                        :header="stage"
                      >
                        <a-row :gutter="8">
                          <a-col v-for="(count, item) in drops" :key="item" :span="12">
                            <a-statistic
                              :title="item"
                              :value="count"
                              :value-style="{ fontSize: '14px' }"
                            />
                          </a-col>
                        </a-row>
                      </a-collapse-panel>
                    </a-collapse>
                  </div>
                  <div v-else class="no-data">
                    <a-empty
                      description="暂无掉落数据"
                      :image="NodataImage"
                      :image-style="{
                        height: '60px',
                      }"
                    />
                  </div>
                </a-card>
              </div>
            </div>

            <!-- 右侧：详细日志 -->
            <div class="log-area">
              <a-card size="small" title="详细日志" class="log-card">
                <template #extra>
                  <a-space>
                    <a-tooltip title="打开日志文件" :get-popup-container="tooltipContainer">
                      <a-button
                        size="small"
                        type="text"
                        :disabled="!currentJsonFile"
                        :class="{ 'no-hover-shift': true }"
                        :style="buttonFixedStyle"
                        @click="handleOpenLogFile"
                      >
                        <template #icon>
                          <FileOutlined />
                        </template>
                      </a-button>
                    </a-tooltip>
                    <a-tooltip title="打开日志文件所在目录" :get-popup-container="tooltipContainer">
                      <a-button
                        size="small"
                        type="text"
                        :disabled="!currentJsonFile"
                        :class="{ 'no-hover-shift': true }"
                        :style="buttonFixedStyle"
                        @click="handleOpenLogDirectory"
                      >
                        <template #icon>
                          <FolderOpenOutlined />
                        </template>
                      </a-button>
                    </a-tooltip>
                    <a-tooltip title="字体大小" :get-popup-container="tooltipContainer">
                      <a-select
                        v-model:value="logFontSize"
                        size="small"
                        class="log-font-size-select"
                        style="width: 72px"
                        :options="logFontSizeOptions.map(v => ({ value: v, label: v + 'px' }))"
                      />
                    </a-tooltip>
                    <a-tooltip title="搜索快捷键: Ctrl+F" :get-popup-container="tooltipContainer">
                      <a-button
                        size="small"
                        type="text"
                        :class="{ 'no-hover-shift': true }"
                        :style="buttonFixedStyle"
                      >
                        <template #icon>
                          <SearchOutlined />
                        </template>
                      </a-button>
                    </a-tooltip>
                  </a-space>
                </template>
                <a-spin :spinning="detailLoading">
                  <div
                    v-if="currentDetail?.log_content"
                    class="log-content"
                  >
                    <vue-monaco-editor
                      v-model:value="currentDetail.log_content"
                      :theme="logLanguage === 'logfile' ? (isDark ? 'log-dark' : 'log-light') : (isDark ? 'vs-dark' : 'vs')"
                      :options="monacoOptions"
                      height="100%"
                      :language="logLanguage"
                    />
                  </div>
                  <div v-else class="no-log">
                    <a-empty
                      description="未选择日志，请从左边记录条目中选择"
                      :image="NodataImage"
                      :image-style="{ height: '60px' }"
                    />
                  </div>
                </a-spin>
              </a-card>
            </div>
          </div>
        </div>
      </div>
    </a-spin>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue'
import { message } from 'ant-design-vue'
import {
  SearchOutlined,
  ClearOutlined,
  HistoryOutlined,
  UserOutlined,
  GiftOutlined,
  FileSearchOutlined,
  RightOutlined,
  FolderOpenOutlined,
  FileOutlined,
} from '@ant-design/icons-vue'
import { Service } from '@/api/services/Service'
import { HistorySearchIn, type HistoryData } from '@/api' // 调整：枚举需要值导入
import dayjs from 'dayjs'
import NodataImage from '@/assets/NoData.png'
import { VueMonacoEditor } from '@guolao/vue-monaco-editor'
import { useTheme } from '@/composables/useTheme'
import * as monaco from 'monaco-editor'

// 响应式数据
const searchLoading = ref(false)
const detailLoading = ref(false)
const activeKeys = ref<string[]>([])
const currentPreset = ref('week') // 当前选中的快捷选项

// 主题相关
const { isDark } = useTheme()

// 选中的用户相关数据
const selectedUser = ref('')
const selectedUserData = ref<HistoryData | null>(null)
const selectedRecordIndex = ref(-1)
const currentDetail = ref<HistoryData | null>(null)
const currentJsonFile = ref('')

// 快捷时间选择预设（改用枚举值）
const timePresets = [
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

// 搜索表单（默认按日合并）
const searchForm = reactive({
  mode: HistorySearchIn.mode.DAILY as HistorySearchIn.mode,
  startDate: dayjs().subtract(7, 'day').format('YYYY-MM-DD'),
  endDate: dayjs().format('YYYY-MM-DD'),
})

// 历史记录数据
interface HistoryDateGroup {
  date: string
  users: Record<string, HistoryData>
}

const historyData = ref<HistoryDateGroup[]>([])

// 当前显示的统计数据（根据是否选中记录条目来决定显示用户总计还是单条记录的数据）
const currentStatistics = computed(() => {
  if (selectedRecordIndex.value >= 0 && currentDetail.value) {
    // 显示选中记录的统计数据
    return {
      recruit_statistics: currentDetail.value.recruit_statistics,
      drop_statistics: currentDetail.value.drop_statistics,
    }
  } else if (selectedUserData.value) {
    // 显示用户总计统计数据
    return {
      recruit_statistics: selectedUserData.value.recruit_statistics,
      drop_statistics: selectedUserData.value.drop_statistics,
    }
  } else {
    // 没有选中任何数据
    return {
      recruit_statistics: null,
      drop_statistics: null,
    }
  }
})

// 页面加载时自动搜索
onMounted(() => {
  // 注册自定义日志语言
  registerLogLanguage()
  handleSearch()
})

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
      // 转换数据格式
      historyData.value = Object.entries(response.data)
        .map(([date, users]) => ({
          date,
          users,
        }))
        .sort((a, b) => b.date.localeCompare(a.date)) // 按日期倒序排列

      message.success('搜索完成')
    } else {
      message.error(response.message || '搜索失败')
    }
  } catch (error) {
    console.error('搜索历史记录失败:', error)
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
}

// 快捷时间选择处理
const handleQuickTimeSelect = (preset: (typeof timePresets)[0]) => {
  currentPreset.value = preset.key
  searchForm.startDate = preset.startDate()
  searchForm.endDate = preset.endDate()
  searchForm.mode = preset.mode

  // 自动搜索
  handleSearch()
}

// 日期变化处理（手动选择日期时清除快捷选择状态）
const handleDateChange = () => {
  currentPreset.value = ''
}

// 选择用户处理（修正乱码注释）
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
    const response = await Service.getHistoryDataApiHistoryDataPost({
      jsonPath: jsonFile,
    })

    if (response.code === 200) {
      currentDetail.value = response.data
    } else {
      message.error(response.message || '获取详细日志失败')
      currentDetail.value = null
    }
  } catch (error) {
    console.error('获取历史记录详情失败:', error)
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
    // 将 .json 扩展名替换为 .log
    const logFilePath = currentJsonFile.value.replace(/\.json$/, '.log')

    console.log('尝试打开日志文件:', logFilePath)
    console.log('electronAPI 可用性:', !!window.electronAPI)
    console.log(
      'openFile 方法可用性:',
      !!(window.electronAPI && (window.electronAPI as any).openFile)
    )

    // 调用系统API打开文件
    if (window.electronAPI && (window.electronAPI as any).openFile) {
      await (window.electronAPI as any).openFile(logFilePath)
      message.success('日志文件已打开')
    } else {
      const errorMsg = !window.electronAPI
        ? '当前环境不支持打开文件功能（electronAPI 不可用）'
        : '当前环境不支持打开文件功能（openFile 方法不可用）'
      console.error(errorMsg)
      message.error(errorMsg)
    }
  } catch (error) {
    console.error('打开日志文件失败:', error)
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
    // 将 .json 扩展名替换为 .log
    const logFilePath = currentJsonFile.value.replace(/\.json$/, '.log')

    console.log('尝试打开日志文件目录:', logFilePath)
    console.log('electronAPI 可用性:', !!window.electronAPI)
    console.log(
      'showItemInFolder 方法可用性:',
      !!(window.electronAPI && (window.electronAPI as any).showItemInFolder)
    )

    // 调用系统API打开目录并选中文件
    if (window.electronAPI && (window.electronAPI as any).showItemInFolder) {
      await (window.electronAPI as any).showItemInFolder(logFilePath)
      message.success('日志文件目录已打开')
    } else {
      const errorMsg = !window.electronAPI
        ? '当前环境不支持打开目录功能（electronAPI 不可用）'
        : '当前环境不支持打开目录功能（showItemInFolder 方法不可用）'
      console.error(errorMsg)
      message.error(errorMsg)
    }
  } catch (error) {
    console.error('打开日志文件目录失败:', error)
    message.error(`打开日志文件目录失败: ${error}`)
  }
}

// 日志字体大小（恢复）
const logFontSize = ref(14)
const logFontSizeOptions = [12, 13, 14, 16, 18, 20]

// 语言注册状态
let isLanguageRegistered = false

// 注册自定义日志语言
const registerLogLanguage = () => {
  if (isLanguageRegistered) return
  
  try {
    // 注册日志语言
    monaco.languages.register({ id: 'logfile' })

    // 定义语法高亮规则
    monaco.languages.setMonarchTokensProvider('logfile', {
      tokenizer: {
        root: [
          // 时间戳 (各种格式)
          [/\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}:\d{2}(\.\d{3})?/, 'timestamp'],
          [/\d{2}:\d{2}:\d{2}(\.\d{3})?/, 'timestamp'],
          [/\[\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}:\d{2}(\.\d{3})?\]/, 'timestamp'],
          
          // 日志级别
          [/\b(ERROR|FATAL|CRITICAL)\b/i, 'log-error'],
          [/\b(WARN|WARNING)\b/i, 'log-warning'],
          [/\b(INFO|INFORMATION)\b/i, 'log-info'],
          [/\b(DEBUG|TRACE|VERBOSE)\b/i, 'log-debug'],
          
          // 括号内的内容 (通常是模块名或线程名)
          [/\[[^\]]+\]/, 'log-module'],
          [/\([^)]+\)/, 'log-module'],
          
          // IP 地址
          [/\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b/, 'log-ip'],
          
          // URL
          [/https?:\/\/[^\s]+/, 'log-url'],
          
          // 文件路径
          [/[A-Za-z]:[\\\/][^\s]+/, 'log-path'],
          [/\/[^\s]*\.[a-zA-Z0-9]+/, 'log-path'],
          
          // 数字
          [/\b\d+\b/, 'log-number'],
          
          // 异常和错误关键词
          [/\b(Exception|Error|Failed|Failure|Timeout|Abort)\b/i, 'log-error-keyword'],
          
          // 成功关键词
          [/\b(Success|Complete|Completed|OK|Done|Finished)\b/i, 'log-success'],
        ]
      }
    })

    // 定义主题颜色
    monaco.editor.defineTheme('log-light', {
      base: 'vs',
      inherit: true,
      rules: [
        { token: 'timestamp', foreground: '0066cc', fontStyle: 'bold' },
        { token: 'log-error', foreground: 'ff0000', fontStyle: 'bold' },
        { token: 'log-warning', foreground: 'ff8800', fontStyle: 'bold' },
        { token: 'log-info', foreground: '0088cc', fontStyle: 'bold' },
        { token: 'log-debug', foreground: '888888' },
        { token: 'log-module', foreground: '8800cc' },
        { token: 'log-ip', foreground: '00aa00' },
        { token: 'log-url', foreground: '0066cc', textDecoration: 'underline' },
        { token: 'log-path', foreground: '666666' },
        { token: 'log-number', foreground: '0066cc' },
        { token: 'log-error-keyword', foreground: 'cc0000' },
        { token: 'log-success', foreground: '00aa00' },
      ],
      colors: {}
    })

    monaco.editor.defineTheme('log-dark', {
      base: 'vs-dark',
      inherit: true,
      rules: [
        { token: 'timestamp', foreground: '4fc3f7', fontStyle: 'bold' },
        { token: 'log-error', foreground: 'f44336', fontStyle: 'bold' },
        { token: 'log-warning', foreground: 'ff9800', fontStyle: 'bold' },
        { token: 'log-info', foreground: '2196f3', fontStyle: 'bold' },
        { token: 'log-debug', foreground: '9e9e9e' },
        { token: 'log-module', foreground: '9c27b0' },
        { token: 'log-ip', foreground: '4caf50' },
        { token: 'log-url', foreground: '03dac6', textDecoration: 'underline' },
        { token: 'log-path', foreground: 'bdbdbd' },
        { token: 'log-number', foreground: '64b5f6' },
        { token: 'log-error-keyword', foreground: 'ef5350' },
        { token: 'log-success', foreground: '66bb6a' },
      ],
      colors: {}
    })

    isLanguageRegistered = true
    console.log('Log language registered successfully')
  } catch (error) {
    console.error('Failed to register log language:', error)
  }
}

// 智能检测日志语言
const logLanguage = computed(() => {
  if (!currentDetail.value?.log_content) return 'logfile'
  
  const content = currentDetail.value.log_content
  
  // 检测其他特殊格式
  if (content.includes('<?xml') || content.includes('<html')) return 'xml'
  if (content.includes('{') && content.includes('}') && content.includes('"')) return 'json'
  if (content.includes('#!/bin/bash') || content.includes('#!/bin/sh')) return 'shell'
  
  // 默认使用日志语言，因为大部分内容都是日志
  return 'logfile'
})

// Monaco Editor 配置
const monacoOptions = computed(() => ({
  readOnly: true,
  fontSize: logFontSize.value,
  fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace',
  lineHeight: 1.5,
  wordWrap: 'on',
  scrollBeyondLastLine: false,
  minimap: { enabled: false },
  scrollbar: {
    vertical: 'auto',
    horizontal: 'auto',
    verticalScrollbarSize: 8,
    horizontalScrollbarSize: 8,
  },
  find: {
    addExtraSpaceOnTop: false,
  },
  automaticLayout: true,
}))

// Tooltip 容器：避免挂载到 body 造成全局滚动条闪烁与布局抖动
const tooltipContainer = (triggerNode: HTMLElement) => triggerNode?.parentElement || document.body
// 固定 button 尺寸，避免 hover/tooltip 状态导致宽度高度微调
const buttonFixedStyle = { width: '28px', height: '28px', padding: 0 }
</script>

<style scoped>
.history-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 32px;
  padding: 0 8px;
}

.header-title {
  display: flex;
  align-items: center;
  gap: 16px;
}

.header-title h1 {
  margin: 0;
  font-size: 32px;
  font-weight: 700;
  color: var(--ant-color-text);
  background: linear-gradient(135deg, var(--ant-color-primary), var(--ant-color-primary-hover));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.search-section {
  margin-bottom: 24px;
}

.history-content {
  height: 53vh;
  overflow: auto;
}

.empty-state {
  text-align: center;
  padding: 60px 0;
}

/* 新的布局样式 */
.history-layout {
  display: flex;
  gap: 16px;
  height: 100%;
}

/* 左侧日期栏 */
.date-sidebar {
  width: 200px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.date-list {
  flex: 1;
  overflow-y: auto;
  border: 1px solid var(--ant-color-border);
  border-radius: 8px;
  background: var(--ant-color-bg-container);
}

.date-panel {
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.date-panel:last-child {
  border-bottom: none;
}

.date-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.date-text {
  font-weight: 600;
  font-size: 14px;
}

.user-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px 0;
}

.user-item {
  padding: 8px 12px;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s ease;
  border: 1px solid transparent;
}

.user-item:hover {
  background: rgba(0, 0, 0, 0.04); /* 移除未知 CSS 变量 */
  border-color: var(--ant-color-border);
}

.user-item.active {
  background: var(--ant-color-primary-bg);
  border-color: var(--ant-color-primary);
}

.user-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.username {
  font-weight: 500;
  font-size: 13px;
}

/* 右侧详情区域 */
.detail-area {
  flex: 1;
  display: flex;
  flex-direction: column;
}

/* 隐藏所有滚动条 */
*::-webkit-scrollbar {
  display: none; /* Chrome, Safari and Opera */
}

.no-selection {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--ant-color-border);
  border-radius: 8px;
  background: var(--ant-color-bg-container);
  min-height: 400px;
}

.detail-content {
  flex: 1;
  display: flex;
  gap: 16px;
  min-height: 0;
  min-width: 0; /* 确保子项 flex:1 时可以收缩 */
  overflow: hidden; /* 避免被长行撑出 */
}

/* 记录条目区域 */
.records-area {
  width: 400px;
  flex-shrink: 1; /* 新增: 允许一定程度收缩 */
  min-width: 260px; /* 给一个合理下限 */
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.records-section {
  flex-shrink: 0;
}

.records-card {
  border: 1px solid var(--ant-color-border);
  border-radius: 8px;
}

.record-count {
  font-size: 12px;
  color: var(--ant-color-text-secondary);
}

.records-list {
  max-height: 300px;
  overflow-y: auto;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 6px;
  background: var(--ant-color-bg-layout);
}

.record-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
  cursor: pointer;
  transition: all 0.2s ease;
  position: relative;
}

.record-item:last-child {
  border-bottom: none;
}

.record-item:hover {
  background: rgba(0, 0, 0, 0.04); /* 移除未知 CSS 变量 */
}

.record-item.active {
  background: var(--ant-color-primary-bg);
  border-left: 3px solid var(--ant-color-primary);
}

.record-item.success {
  border-left: 3px solid var(--ant-color-success);
}

.record-item.error {
  border-left: 3px solid var(--ant-color-error);
}

.record-item.active.success {
  border-left: 3px solid var(--ant-color-primary);
}

.record-item.active.error {
  border-left: 3px solid var(--ant-color-primary);
}

.record-info {
  flex: 1;
  min-width: 0;
}

.record-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.record-time {
  font-size: 13px;
  font-weight: 500;
  color: var(--ant-color-text);
}

.record-file {
  font-size: 11px;
  color: var(--ant-color-text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.record-indicator {
  flex-shrink: 0;
  width: 16px;
  display: flex;
  justify-content: center;
  align-items: center;
  color: var(--ant-color-primary);
}

.statistics-section {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.stat-card {
  border: 1px solid var(--ant-color-border);
  border-radius: 8px;
  height: fit-content;
}

.recruit-stats,
.drop-stats {
  min-height: 120px;
}

.no-data {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 120px;
}

/* 日志区域 */
.log-area {
  flex: 1;
  /* 允许在父级 flex 宽度不足时压缩，避免整体被撑出视口 */
  min-width: 0; /* 修改: 原来是 300px，导致在内容渲染后无法收缩 */
  display: flex;
  flex-direction: column;
}

.log-card {
  flex: 1;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--ant-color-border);
  border-radius: 8px;
  height: 600px;
}

.log-card :deep(.ant-card-body) {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 12px;
  height: calc(100% - 60px);
}

.log-content {
  flex: 1;
  height: 500px;
  min-height: 500px;
  overflow: hidden;
  border-radius: 6px;
  border: 1px solid var(--ant-color-border-secondary);
}

.log-content :deep(.monaco-editor) {
  border-radius: 6px;
}

.log-content :deep(.monaco-editor .margin) {
  background-color: transparent;
}

.log-content :deep(.monaco-editor .monaco-editor-background) {
  background-color: var(--ant-color-bg-container);
}

/* 恢复字体选择器样式 */
.log-font-size-select :deep(.ant-select-selector) {
  padding: 0 4px;
  text-align: center;
}

/* 按钮样式 */
/* 移除未使用 .title-icon */
/* 移除 unused overview-section / overview-card / overview-stats / user-status / error-section / error-card */
.default {
  border-color: var(--ant-color-border);
  color: var(--ant-color-text);
}

.default:hover {
  border-color: var(--ant-color-primary);
  color: var(--ant-color-primary);
}

/* 防止按钮在获得焦点/激活时出现位移（如出现 outline 或行高变化导致的抖动） */
.no-hover-shift {
  line-height: 1; /* 固定行高 */
}
.no-hover-shift :deep(.ant-btn-icon) {
  display: flex;
  align-items: center;
  justify-content: center;
}

/* 约束 tooltip 在本容器内时的最大宽度，减少撑开 */
:deep(.ant-tooltip) {
  max-width: 260px;
  word-break: break-word;
}

/* 响应式设计 */
@media (max-width: 1200px) {
  .history-layout {
    flex-direction: column;
  }

  .date-sidebar {
    width: 100%;
    max-height: 300px;
  }

  .detail-content {
    flex-direction: column;
  }

  .log-area {
    width: 100%;
    min-width: 0;
  }
}

/* 针对极窄窗口再降级为纵向布局，提前触发布局切换，避免出现水平滚动 */
@media (max-width: 1000px) {
  .history-layout {
    flex-direction: column;
  }
  .records-area {
    width: 100%;
    min-width: 0;
  }
  .log-area {
    width: 100%;
    min-width: 0;
  }
}
</style>
