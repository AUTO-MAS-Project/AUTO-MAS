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
              size="middle"
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
          <a-form-item label=" " style="margin-bottom: 0" :colon="false">
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
          <!--          &lt;!&ndash; 数据总览 &ndash;&gt;-->
          <!--          <div class="overview-section">-->
          <!--            <a-card size="small" title="数据总览" class="overview-card">-->
          <!--              <div class="overview-stats">-->
          <!--                <a-statistic-->
          <!--                  title="总公招数"-->
          <!--                  :value="totalOverview.totalRecruit"-->
          <!--                  :value-style="{ color: '#1890ff', fontSize: '18px' }"-->
          <!--                >-->
          <!--                  <template #prefix>-->
          <!--                    <UserOutlined />-->
          <!--                  </template>-->
          <!--                </a-statistic>-->
          <!--                <a-statistic-->
          <!--                  title="总掉落数"-->
          <!--                  :value="totalOverview.totalDrop"-->
          <!--                  :value-style="{ color: '#52c41a', fontSize: '18px' }"-->
          <!--                >-->
          <!--                  <template #prefix>-->
          <!--                    <GiftOutlined />-->
          <!--                  </template>-->
          <!--                </a-statistic>-->
          <!--              </div>-->
          <!--            </a-card>-->
          <!--          </div>-->

          <!-- 日期折叠列表 -->
          <div class="date-list">
            <a-collapse v-model:activeKey="activeKeys" ghost>
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
            <!-- 左侧：记录条目和统计数据 -->
            <div class="records-area">
              <!-- 记录条目列表 -->
              <div class="records-section">
                <a-card size="small" title="记录条目" class="records-card">
                  <template #extra>
                    <a-space>
                      <span class="record-count"
                        >{{ selectedUserData.index?.length || 0 }} 条记录</span
                      >
                      <HistoryOutlined />
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
                          <a-tag
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
                <a-row :gutter="16">
                  <!-- 公招统计 -->
                  <a-col :span="12">
                    <a-card size="small" class="stat-card">
                      <template #title>
                        <span>公招统计</span>
                        <span v-if="selectedRecordIndex >= 0" class="stat-subtitle"
                          >（当前记录）</span
                        >
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
                        <a-empty description="暂无公招数据" :image="false" />
                      </div>
                    </a-card>
                  </a-col>

                  <!-- 掉落统计 -->
                  <a-col :span="12">
                    <a-card size="small" class="stat-card">
                      <template #title>
                        <span>掉落统计</span>
                        <span v-if="selectedRecordIndex >= 0" class="stat-subtitle"
                          >（当前记录）</span
                        >
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
                        <a-empty description="暂无掉落数据" :image="false" />
                      </div>
                    </a-card>
                  </a-col>
                </a-row>
              </div>
            </div>

            <!-- 右侧：详细日志 -->
            <div class="log-area">
              <a-card size="small" title="详细日志" class="log-card">
                <template #extra>
                  <a-space>
                    <FileTextOutlined />
                    <a-button
                      type="link"
                      size="small"
                      @click="handleRefreshLog"
                      :loading="detailLoading"
                    >
                      刷新日志
                    </a-button>
                  </a-space>
                </template>
                <a-spin :spinning="detailLoading">
                  <div v-if="currentDetail?.log_content" class="log-content">
                    <pre>{{ currentDetail.log_content }}</pre>
                  </div>
                  <div v-else class="no-log">
                    <a-empty description="暂无日志内容" :image="false" />
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
  ReloadOutlined,
  SearchOutlined,
  ClearOutlined,
  HistoryOutlined,
  UserOutlined,
  GiftOutlined,
  ExclamationCircleOutlined,
  FileSearchOutlined,
  FileTextOutlined,
  RightOutlined,
} from '@ant-design/icons-vue'
import { Service } from '@/api/services/Service'
import type { HistorySearchIn, HistoryData, HistoryDataGetIn } from '@/api/models'
import dayjs from 'dayjs'

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
    mode: '按月合并' as HistorySearchIn.mode,
  },
  {
    key: 'halfYear',
    label: '最近半年',
    startDate: () => dayjs().subtract(6, 'month').format('YYYY-MM-DD'),
    endDate: () => dayjs().format('YYYY-MM-DD'),
    mode: '按月合并' as HistorySearchIn.mode,
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

// 计算总览数据
const totalOverview = computed(() => {
  let totalRecruit = 0
  let totalDrop = 0

  historyData.value.forEach(dateGroup => {
    Object.values(dateGroup.users).forEach(userData => {
      // 统计公招数据
      if (userData.recruit_statistics) {
        Object.values(userData.recruit_statistics).forEach((count: any) => {
          totalRecruit += count
        })
      }

      // 统计掉落数据
      if (userData.drop_statistics) {
        Object.values(userData.drop_statistics).forEach((stageDrops: any) => {
          Object.values(stageDrops).forEach((count: any) => {
            totalDrop += count
          })
        })
      }
    })
  })

  return {
    totalRecruit,
    totalDrop,
  }
})

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

// 选择用户处理
const handleSelectUser = async (date: string, username: string, userData: HistoryData) => {
  selectedUser.value = `${date}-${username}`
  selectedUserData.value = userData
  selectedRecordIndex.value = -1 // 重置记录选择
  currentDetail.value = null // 清空日志内容
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

// 刷新日志
const handleRefreshLog = async () => {
  if (currentJsonFile.value) {
    await loadUserLog(currentJsonFile.value)
  }
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
}

.header-title h1 {
  margin: 0;
  font-size: 24px;
  font-weight: 600;
}

.search-section {
  margin-bottom: 24px;
}

.history-content {
  height: calc(80vh - 200px);
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
  width: 320px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.overview-section {
  flex-shrink: 0;
}

.overview-card {
  border: 1px solid var(--ant-color-border);
  border-radius: 8px;
}

.overview-stats {
  display: flex;
  justify-content: space-around;
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
  background: var(--ant-color-bg-container-disabled);
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

.user-status {
  display: flex;
  gap: 4px;
}

/* 右侧详情区域 */
.detail-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.no-selection {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--ant-color-border);
  border-radius: 8px;
  background: var(--ant-color-bg-container);
}

.detail-content {
  flex: 1;
  display: flex;
  gap: 16px;
  min-height: 0;
}

/* 记录条目区域 */
.records-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-width: 0;
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
  background: var(--ant-color-bg-container-disabled);
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

.error-section {
  margin-top: 16px;
}

.error-card {
  border: 1px solid var(--ant-color-error-border);
  border-radius: 8px;
}

/* 日志区域 */
.log-area {
  width: 400px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
}

.log-card {
  flex: 1;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--ant-color-border);
  border-radius: 8px;
}

.log-card :deep(.ant-card-body) {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 12px;
}

.log-content {
  flex: 1;
  max-height: 500px;
  overflow-y: auto;
  background: var(--ant-color-bg-layout);
  border: 1px solid var(--ant-color-border);
  border-radius: 6px;
  padding: 12px;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 12px;
  line-height: 1.4;
}

.log-content pre {
  margin: 0;
  white-space: pre-wrap;
  word-wrap: break-word;
}

.no-log {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
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
    max-height: 400px;
  }
}

/* 统计数据标题样式 */
.stat-subtitle {
  font-size: 12px;
  color: var(--ant-color-text-secondary);
  font-weight: normal;
  margin-left: 8px;
}

/* 滚动条样式 */
.date-list::-webkit-scrollbar,
.log-content::-webkit-scrollbar,
.records-list::-webkit-scrollbar {
  width: 6px;
}

.date-list::-webkit-scrollbar-track,
.log-content::-webkit-scrollbar-track,
.records-list::-webkit-scrollbar-track {
  background: var(--ant-color-bg-container);
  border-radius: 3px;
}

.date-list::-webkit-scrollbar-thumb,
.log-content::-webkit-scrollbar-thumb,
.records-list::-webkit-scrollbar-thumb {
  background: var(--ant-color-border);
  border-radius: 3px;
}

.date-list::-webkit-scrollbar-thumb:hover,
.log-content::-webkit-scrollbar-thumb:hover,
.records-list::-webkit-scrollbar-thumb:hover {
  background: var(--ant-color-border-secondary);
}
</style>
