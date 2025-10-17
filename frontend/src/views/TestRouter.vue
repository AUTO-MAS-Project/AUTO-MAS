<template>
  <!--标题-->
  <div class="history-header">
    <div class="header-title">
      <h1>历史记录</h1>
    </div>
  </div>

  <a-flex vertical="vertical">
    <!-- 中上部：时间选择器 -->
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

    <!-- 中下部分：列表 -->
    <a-flex class="history-content">
      <div class="history-layout">
        <!-- 中下部分：左侧日期列表 -->
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
      </div>
      <!--这里有个spin-->
    </a-flex>
  </a-flex>
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

// 响应式数据
const searchLoading = ref(false)
const detailLoading = ref(false)
const activeKeys = ref<string[]>([])
const currentPreset = ref('week') // 当前选中的快捷选项

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
    message.error(`��开日志文件目录失败: ${error}`)
  }
}

// 日志字体大小（恢复）
const logFontSize = ref(14)
const logFontSizeOptions = [12, 13, 14, 16, 18, 20]

// Tooltip 容器：避免挂载到 body 造成全局滚动条闪烁与布局抖动
const tooltipContainer = (triggerNode: HTMLElement) => triggerNode?.parentElement || document.body
// 固定 button 尺寸，避免 hover/tooltip 状态导致宽度高度微调
const buttonFixedStyle = { width: '28px', height: '28px', padding: 0 }
</script>

<style scoped>
/*标题父元素的父元素（？？？）*/
.history-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 32px;
  padding: 0 8px;
}

/*标题父元素*/
.header-title {
  display: flex;
  align-items: center;
  gap: 16px;
}

/*标题*/
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

/* 中下部分:左侧日期列表 */
.history-content {
  height: calc(80vh - 200px);
  overflow: hidden;
}

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
</style>
