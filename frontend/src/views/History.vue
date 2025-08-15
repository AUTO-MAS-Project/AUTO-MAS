<template>
  <div class="history-header">
    <div class="header-title">
      <h1>历史记录</h1>
    </div>
    <a-space size="middle">
      <a-button size="large" @click="handleRefresh" class="default">
        <template #icon>
          <ReloadOutlined />
        </template>
        刷新
      </a-button>
    </a-space>
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
              size="small"
              @click="handleQuickTimeSelect(preset)"
            >
              {{ preset.label }}
            </a-button>
          </a-space>
        </a-form-item>
      </div>

      <!-- 详细筛选条件 -->
      <a-row :gutter="16" align="middle">
        <a-col :span="6">
          <a-form-item label="合并模式" style="margin-bottom: 0">
            <a-select v-model:value="searchForm.mode" style="width: 100%">
              <a-select-option value="按日合并">按日合并</a-select-option>
              <a-select-option value="按周合并">按周合并</a-select-option>
              <a-select-option value="按年月并">按月合并</a-select-option>
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
          <a-space>
            <a-button type="primary" @click="handleSearch" :loading="searchLoading">
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
        </a-col>
      </a-row>
    </a-card>
  </div>

  <!-- 历史记录列表 -->
  <div class="history-content">
    <a-spin :spinning="searchLoading">
      <div v-if="historyData.length === 0 && !searchLoading" class="empty-state">
        <a-empty description="暂无历史记录数据">
          <template #image>
            <HistoryOutlined style="font-size: 64px; color: #d9d9d9" />
          </template>
        </a-empty>
      </div>

      <div v-else class="history-list">
        <a-collapse v-model:activeKey="activeKeys" ghost>
          <a-collapse-panel
            v-for="dateGroup in historyData"
            :key="dateGroup.date"
            :header="dateGroup.date"
            class="date-panel"
          >
            <template #extra>
              <a-tag :color="getDateStatusColor(dateGroup.users)">
                {{ Object.keys(dateGroup.users).length }} 个用户
              </a-tag>
            </template>

            <div class="user-list">
              <a-card
                v-for="(userData, username) in dateGroup.users"
                :key="username"
                size="small"
                class="user-card"
                :title="username"
              >
                <template #extra>
                  <a-space>
                    <a-tag
                      v-for="item in userData.index || []"
                      :key="item.jsonFile"
                      :color="item.status === '完成' ? 'success' : 'error'"
                    >
                      {{ item.status }}
                    </a-tag>
                    <a-button
                      type="link"
                      size="small"
                      @click="handleViewDetails(userData, username, dateGroup.date)"
                    >
                      查看详情
                    </a-button>
                  </a-space>
                </template>

                <!-- 统计信息 -->
                <div class="statistics-section">
                  <!-- 公招统计 -->
                  <div v-if="userData.recruit_statistics" class="stat-item">
                    <h4>
                      <UserOutlined />
                      公招统计
                    </h4>
                    <a-row :gutter="8">
                      <a-col
                        v-for="(count, star) in userData.recruit_statistics"
                        :key="star"
                        :span="4"
                      >
                        <a-statistic
                          :title="`${star}星`"
                          :value="count"
                          :value-style="{ fontSize: '14px' }"
                        />
                      </a-col>
                    </a-row>
                  </div>

                  <!-- 掉落统计 -->
                  <div v-if="userData.drop_statistics" class="stat-item">
                    <h4>
                      <GiftOutlined />
                      掉落统计
                    </h4>
                    <a-collapse size="small" ghost>
                      <a-collapse-panel
                        v-for="(drops, stage) in userData.drop_statistics"
                        :key="stage"
                        :header="stage"
                      >
                        <a-row :gutter="8">
                          <a-col v-for="(count, item) in drops" :key="item" :span="6">
                            <a-statistic
                              :title="item"
                              :value="count"
                              :value-style="{ fontSize: '12px' }"
                            />
                          </a-col>
                        </a-row>
                      </a-collapse-panel>
                    </a-collapse>
                  </div>

                  <!-- 错误信息 -->
                  <div
                    v-if="userData.error_info && Object.keys(userData.error_info).length > 0"
                    class="stat-item"
                  >
                    <h4>
                      <ExclamationCircleOutlined style="color: #ff4d4f" />
                      错误信息
                    </h4>
                    <a-list size="small" :data-source="Object.entries(userData.error_info)">
                      <template #renderItem="{ item }">
                        <a-list-item>
                          <a-list-item-meta>
                            <template #title>
                              <span style="color: #ff4d4f">{{
                                new Date(parseInt(item[0])).toLocaleString()
                              }}</span>
                            </template>
                            <template #description>
                              {{ item[1] }}
                            </template>
                          </a-list-item-meta>
                        </a-list-item>
                      </template>
                    </a-list>
                  </div>
                </div>
              </a-card>
            </div>
          </a-collapse-panel>
        </a-collapse>
      </div>
    </a-spin>
  </div>

  <!-- 详情弹窗 -->
  <a-modal
    v-model:open="detailModalVisible"
    :title="`${currentUser} - ${currentDate} 详细日志`"
    width="80%"
    :footer="null"
    class="detail-modal"
  >
    <a-spin :spinning="detailLoading">
      <div v-if="currentDetail?.log_content" class="log-content">
        <pre>{{ currentDetail.log_content }}</pre>
      </div>
      <div v-else class="no-log">
        <a-empty description="暂无日志内容" />
      </div>
    </a-spin>
  </a-modal>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import {
  ReloadOutlined,
  SearchOutlined,
  ClearOutlined,
  HistoryOutlined,
  UserOutlined,
  GiftOutlined,
  ExclamationCircleOutlined,
} from '@ant-design/icons-vue'
import { Service } from '@/api/services/Service'
import type { HistorySearchIn, HistoryData, HistoryDataGetIn } from '@/api/models'
import dayjs from 'dayjs'

// 响应式数据
const searchLoading = ref(false)
const detailLoading = ref(false)
const detailModalVisible = ref(false)
const activeKeys = ref<string[]>([])
const currentPreset = ref('week') // 当前选中的快捷选项

// 快捷时间选择预设
const timePresets = [
  {
    key: 'today',
    label: '今天',
    startDate: () => dayjs().format('YYYY-MM-DD'),
    endDate: () => dayjs().format('YYYY-MM-DD'),
    mode: '按日合并' as HistorySearchIn.mode,
  },
  {
    key: 'yesterday',
    label: '昨天',
    startDate: () => dayjs().subtract(1, 'day').format('YYYY-MM-DD'),
    endDate: () => dayjs().subtract(1, 'day').format('YYYY-MM-DD'),
    mode: '按日合并' as HistorySearchIn.mode,
  },
  {
    key: 'week',
    label: '最近一周',
    startDate: () => dayjs().subtract(7, 'day').format('YYYY-MM-DD'),
    endDate: () => dayjs().format('YYYY-MM-DD'),
    mode: '按日合并' as HistorySearchIn.mode,
  },
  {
    key: 'month',
    label: '最近一个月',
    startDate: () => dayjs().subtract(1, 'month').format('YYYY-MM-DD'),
    endDate: () => dayjs().format('YYYY-MM-DD'),
    mode: '按周合并' as HistorySearchIn.mode,
  },
  {
    key: 'twoMonths',
    label: '最近两个月',
    startDate: () => dayjs().subtract(2, 'month').format('YYYY-MM-DD'),
    endDate: () => dayjs().format('YYYY-MM-DD'),
    mode: '按周合并' as HistorySearchIn.mode,
  },
  {
    key: 'threeMonths',
    label: '最近三个月',
    startDate: () => dayjs().subtract(3, 'month').format('YYYY-MM-DD'),
    endDate: () => dayjs().format('YYYY-MM-DD'),
    mode: '按年月并' as HistorySearchIn.mode,
  },
  {
    key: 'halfYear',
    label: '最近半年',
    startDate: () => dayjs().subtract(6, 'month').format('YYYY-MM-DD'),
    endDate: () => dayjs().format('YYYY-MM-DD'),
    mode: '按年月并' as HistorySearchIn.mode,
  },
]

// 搜索表单
const searchForm = reactive({
  mode: '按日合并' as HistorySearchIn.mode,
  startDate: dayjs().subtract(7, 'day').format('YYYY-MM-DD'),
  endDate: dayjs().format('YYYY-MM-DD'),
})

// 历史记录数据
interface HistoryDateGroup {
  date: string
  users: Record<string, HistoryData>
}

const historyData = ref<HistoryDateGroup[]>([])
const currentDetail = ref<HistoryData | null>(null)
const currentUser = ref('')
const currentDate = ref('')

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
  searchForm.mode = '按日合并'
  searchForm.startDate = dayjs().subtract(7, 'day').format('YYYY-MM-DD')
  searchForm.endDate = dayjs().format('YYYY-MM-DD')
  historyData.value = []
  activeKeys.value = []
}

// 刷新数据
const handleRefresh = () => {
  handleSearch()
}

// 查看详情
const handleViewDetails = async (userData: HistoryData, username: string, date: string) => {
  if (!userData.index || userData.index.length === 0) {
    message.warning('该记录没有详细日志文件')
    return
  }

  try {
    detailLoading.value = true
    detailModalVisible.value = true
    currentUser.value = username
    currentDate.value = date

    // 获取第一个JSON文件的详细内容
    const jsonFile = userData.index[0].jsonFile
    const response = await Service.getHistoryDataApiHistoryDataPost({
      jsonPath: jsonFile,
    })

    if (response.code === 200) {
      currentDetail.value = response.data
    } else {
      message.error(response.message || '获取详细日志失败')
    }
  } catch (error) {
    console.error('获取历史记录详情失败:', error)
    message.error('获取历史记录详情失败')
  } finally {
    detailLoading.value = false
  }
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

// 获取日期状态颜色
const getDateStatusColor = (users: Record<string, HistoryData>) => {
  const hasError = Object.values(users).some(
    user =>
      user.index?.some(item => item.status === '异常') ||
      (user.error_info && Object.keys(user.error_info).length > 0)
  )
  return hasError ? 'error' : 'success'
}
</script>

<style scoped>
.history-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
  padding: 0 24px;
}

.header-title h1 {
  margin: 0;
  font-size: 24px;
  font-weight: 600;
}

.search-section {
  margin-bottom: 24px;
  padding: 0 24px;
}

.history-content {
  padding: 0 24px;
}

.empty-state {
  text-align: center;
  padding: 60px 0;
}

.history-list {
  min-height: 400px;
}

.date-panel {
  margin-bottom: 16px;
}

.user-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.user-card {
  border: 1px solid var(--ant-color-border);
  border-radius: 8px;
}

.statistics-section {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.stat-item h4 {
  margin: 0 0 8px 0;
  font-size: 14px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 8px;
}

.detail-modal .log-content {
  max-height: 60vh;
  overflow-y: auto;
  background: var(--ant-color-bg-container);
  border: 1px solid var(--ant-color-border);
  border-radius: 6px;
  padding: 16px;
}

.detail-modal .log-content pre {
  margin: 0;
  white-space: pre-wrap;
  word-wrap: break-word;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 12px;
  line-height: 1.4;
}

.no-log {
  text-align: center;
  padding: 40px 0;
}

/* 按钮样式 */
.default {
  border-color: var(--ant-color-border);
  color: var(--ant-color-text);
}

.default:hover {
  border-color: var(--ant-color-primary);
  color: var(--ant-color-primary);
}
</style>
