<template>
  <div class="header">
    <a-typography-title>{{ greeting }}</a-typography-title>
    <!-- 右上角公告按钮 -->
    <div class="header-actions">
      <a-button
        type="primary"
        ghost
        @click="showNotice"
        :loading="noticeLoading"
        class="notice-button"
      >
        <template #icon>
          <BellOutlined />
        </template>
        查看公告
      </a-button>
    </div>
  </div>

  <!-- 公告模态框 -->
  <NoticeModal
    v-model:visible="noticeVisible"
    :notice-data="noticeData"
    @confirmed="onNoticeConfirmed"
  />

  <div class="content">
    <!-- 当期活动关卡 -->
    <a-card
      v-if="activityData?.length"
      title="当期活动关卡"
      class="activity-card"
      :loading="loading"
    >
      <template #extra>
        <a-button type="text" @click="refreshActivity" :loading="loading">
          <template #icon>
            <ReloadOutlined />
          </template>
          刷新
        </a-button>
      </template>

      <div v-if="error" class="error-message">
        <a-alert :message="error" type="error" show-icon closable @close="error = ''" />
      </div>

      <!-- 活动信息展示 -->
      <div v-if="currentActivity && !loading" class="activity-info">
        <div class="activity-header">
          <div class="activity-left">
            <div class="activity-name">
              <span class="activity-title">{{ currentActivity.Tip }}</span>
              <!--              <a-tag color="blue" class="activity-tip">{{ currentActivity.StageName }}</a-tag>-->
            </div>
            <div class="activity-end-time">
              <ClockCircleOutlined class="time-icon" />
              <span class="time-label">结束时间：</span>
              <span class="time-value">{{ formatTime(currentActivity.UtcExpireTime) }}</span>
            </div>
          </div>

          <div class="activity-right">
            <!-- 剩余时间小于两天时显示红色倒计时 -->
            <a-statistic-countdown
              v-if="isLessThanTwoDays(currentActivity.UtcExpireTime)"
              title="当期活动剩余时间"
              :value="getCountdownValue(currentActivity.UtcExpireTime)"
              format="活动时间仅剩 D 天 H 时 m 分 ss 秒 SSS 毫秒，请尽快完成喵~"
              :value-style="{
                color: '#ff4d4f',
                fontWeight: 'bold',
                fontSize: '18px',
              }"
              @finish="onCountdownFinish"
            />

            <!-- 剩余时间大于等于两天时显示常规倒计时 -->
            <a-statistic-countdown
              v-else
              title="当期活动剩余时间"
              :value="getCountdownValue(currentActivity.UtcExpireTime)"
              format="D 天 H 时 m 分"
              :value-style="{
                color: 'var(--ant-color-text)',
                fontWeight: '600',
                fontSize: '20px',
              }"
              @finish="onCountdownFinish"
            />
          </div>
        </div>
      </div>

      <div class="activity-list">
        <div v-for="item in activityData" :key="item.Value" class="activity-item">
          <div class="stage-info">
            <div class="stage-name">{{ item.Display }}</div>
          </div>

          <div class="drop-info">
            <div class="drop-image">
              <img
                v-if="getMaterialImage(item.DropName.startsWith('DESC:') ? '30012' : item.DropName)"
                :src="
                  item.DropName.startsWith('DESC:')
                    ? getMaterialImage('30012')
                    : getMaterialImage(item.Drop)
                "
                :alt="item.DropName.startsWith('DESC:') ? '30012' : item.DropName"
                @error="handleImageError"
              />
            </div>

            <div class="drop-details">
              <div class="drop-name">
                {{ item.DropName.startsWith('DESC:') ? item.DropName.substring(5) : item.DropName }}
              </div>
            </div>
          </div>
        </div>
      </div>
    </a-card>

    <!-- 资源收集关卡 -->
    <a-card title="今日开放资源收集关卡" class="resource-card" :loading="loading">
      <div v-if="error" class="error-message">
        <a-alert :message="error" type="error" show-icon closable @close="error = ''" />
      </div>

      <div v-if="resourceData?.length" class="resource-list">
        <div v-for="item in resourceData" :key="item.Value" class="resource-item">
          <div class="stage-info">
            <div class="stage-name">{{ item.Display }}</div>
          </div>

          <div class="drop-info">
            <div class="drop-image">
              <img
                v-if="getMaterialImage(item.Drop)"
                :src="getMaterialImage(item.Drop)"
                :alt="item.DropName"
                @error="handleImageError"
              />
            </div>

            <div class="drop-details">
              <div class="drop-name">{{ item.DropName }}</div>
              <div class="drop-tip">{{ item.Activity.Tip }}</div>
            </div>
          </div>
        </div>
      </div>

      <div v-else-if="!loading" class="empty-state">
        <img src="@/assets/NoData.png" alt="无数据" class="empty-image" />
      </div>
    </a-card>

    <!-- 代理状态 -->
    <a-card title="代理状态" class="proxy-card" :loading="loading">
      <template #extra>
        <a-tag :color="getProxyStatusColor()"> {{ Object.keys(proxyData).length }} 个用户</a-tag>
      </template>

      <div v-if="Object.keys(proxyData).length > 0" class="proxy-list">
        <a-row :gutter="16">
          <a-col v-for="(proxy, username) in proxyData" :key="username" :span="8">
            <div class="proxy-item">
              <div class="proxy-header">
                <div class="proxy-username">
                  <UserOutlined class="user-icon" />
                  <span class="username">{{ username }}</span>
                </div>
                <!--                <div class="proxy-status">-->
                <!--                  <a-tag :color="proxy.ErrorTimes > 0 ? 'error' : 'success'" size="small">-->
                <!--                    {{ proxy.ErrorTimes > 0 ? '有错误' : '正常' }}-->
                <!--                  </a-tag>-->
                <!--                </div>-->
              </div>

              <div class="proxy-stats">
                <!-- 第一行：最后代理时间，独占一行 -->
                <div class="stat-item full-width">
                  <a-statistic
                    title="最后代理时间"
                    :value="formatProxyDisplay(proxy.LastProxyDate)"
                  />
                </div>

                <!-- 第二行：代理次数 和 错误次数 -->
                <div class="stat-item half-width">
                  <a-statistic title="代理次数" :value="proxy.ProxyTimes" />
                </div>
                <div class="stat-item half-width">
                  <a-statistic
                    title="错误次数"
                    :value="proxy.ErrorTimes"
                    :value-style="{ color: proxy.ErrorTimes > 0 ? '#ff4d4f' : undefined }"
                  />
                </div>
              </div>

              <!--              &lt;!&ndash; 错误信息 &ndash;&gt;-->
              <!--              <div-->
              <!--                v-if="proxy.ErrorTimes > 0 && Object.keys(proxy.ErrorInfo).length > 0"-->
              <!--                class="proxy-errors"-->
              <!--              >-->
              <!--                <a-alert message="错误信息" type="error" show-icon size="small" class="error-alert">-->
              <!--                  <template #description>-->
              <!--                    <div class="error-list">-->
              <!--                      <div-->
              <!--                        v-for="(errorMsg, errorKey) in proxy.ErrorInfo"-->
              <!--                        :key="errorKey"-->
              <!--                        class="error-item"-->
              <!--                      >-->
              <!--                        <strong>{{ errorKey }}:</strong> {{ errorMsg }}-->
              <!--                      </div>-->
              <!--                    </div>-->
              <!--                  </template>-->
              <!--                </a-alert>-->
              <!--              </div>-->
            </div>
          </a-col>
        </a-row>
      </div>

      <div v-else-if="!loading" class="empty-state">
        <img src="@/assets/NoData.png" alt="无数据" class="empty-image" />
      </div>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { message } from 'ant-design-vue'
import {
  ReloadOutlined,
  ClockCircleOutlined,
  UserOutlined,
  BellOutlined,
} from '@ant-design/icons-vue'
import { Service } from '@/api/services/Service'
import NoticeModal from '@/components/NoticeModal.vue'
import dayjs from 'dayjs'
import { API_ENDPOINTS } from '@/config/mirrors.ts'


interface ActivityInfo {
  Tip: string
  StageName: string
  UtcStartTime: string
  UtcExpireTime: string
  TimeZone: number
}

interface ActivityItem {
  Display: string
  Value: string
  Drop: string
  DropName: string
  Activity: ActivityInfo
}

interface ProxyInfo {
  LastProxyDate: string
  ProxyTimes: number
  ErrorTimes: number
  ErrorInfo: Record<string, any>
}

interface ApiResponse {
  Stage: {
    Activity: ActivityItem[]
    Resource: ResourceItem[]
  }
  Proxy: Record<string, ProxyInfo>
}

interface ResourceItem {
  Display: string
  Value: string
  Drop: string
  DropName: string
  Activity: {
    Tip: string
    StageName: string
  }
}

const loading = ref(false)
const error = ref('')
const activityData = ref<ActivityItem[]>([])
const resourceData = ref<ResourceItem[]>([])
const proxyData = ref<Record<string, ProxyInfo>>({})

// 公告系统相关状态
const noticeVisible = ref(false)
const noticeData = ref<Record<string, string>>({})
const noticeLoading = ref(false)

// 获取当前活动信息
const currentActivity = computed(() => {
  if (!activityData.value.length) return null
  return activityData.value[0]?.Activity
})

const formatProxyDisplay = (dateStr: string) => {
  const ts = getProxyTimestamp(dateStr)
  return dayjs(ts).format('YYYY-MM-DD HH:mm:ss') // 需要别的格式可改这里
}

// 格式化时间显示 - 直接使用给定时间，不进行时区转换
const formatTime = (timeString: string) => {
  try {
    // 直接使用给定的时间字符串，因为已经是中国时间
    const date = new Date(timeString)
    return date.toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return timeString
  }
}

// 获取倒计时的目标时间戳
const getCountdownValue = (expireTime: string) => {
  try {
    return new Date(expireTime).getTime()
  } catch {
    return Date.now()
  }
}

// 检查剩余时间是否小于两天
const isLessThanTwoDays = (expireTime: string) => {
  try {
    const expire = new Date(expireTime)
    const now = new Date()
    const remaining = expire.getTime() - now.getTime()
    const twoDaysInMs = 2 * 24 * 60 * 60 * 1000
    return remaining <= twoDaysInMs
  } catch {
    return false
  }
}

// 获取倒计时样式 - 如果剩余时间小于2天则显示红色
const getCountdownStyle = (expireTime: string) => {
  try {
    const expire = new Date(expireTime)
    const now = new Date()
    const remaining = expire.getTime() - now.getTime()
    const twoDaysInMs = 2 * 24 * 60 * 60 * 1000

    if (remaining <= twoDaysInMs) {
      return {
        color: '#ff4d4f',
        fontWeight: 'bold',
        fontSize: '18px',
      }
    }

    return {
      color: 'var(--ant-color-text)',
      fontWeight: '600',
      fontSize: '20px',
    }
  } catch {
    return {
      color: 'var(--ant-color-text)',
      fontWeight: '600',
      fontSize: '20px',
    }
  }
}

const getProxyTimestamp = (dateStr: string) => {
  if (!dateStr) return Date.now()

  //  兜底：尝试让浏览器自己解析
  const t = new Date(dateStr).getTime()
  return Number.isNaN(t) ? Date.now() : t
}

// 倒计时结束回调
const onCountdownFinish = () => {
  message.warning('活动已结束')
  // 重新获取数据
  fetchActivityData()
}

const getMaterialImage = (dropName: string) => {
  if (!dropName) {
    return ''
  }
  // 直接拼接后端图片接口地址
  return `${API_ENDPOINTS.local}/api/res/materials/${dropName}.png`
}

const handleImageError = (event: Event) => {
  const img = event.target as HTMLImageElement
  img.style.display = 'none'
}

const fetchActivityData = async () => {
  loading.value = true
  error.value = ''

  try {
    const response = await Service.getOverviewApiInfoGetOverviewPost()

    if (response.code === 200) {
      const data = response.data as ApiResponse
      if (data.Stage) {
        activityData.value = data.Stage.Activity || []
        resourceData.value = data.Stage.Resource || []
      }
      if (data.Proxy) {
        proxyData.value = data.Proxy
      }
    } else {
      error.value = response.message || '获取数据失败'
    }
  } catch (err) {
    console.error('获取数据失败:', err)
    error.value = '网络请求失败，请检查连接'
  } finally {
    loading.value = false
  }
}

const refreshActivity = async () => {
  await fetchActivityData()
  if (error.value) {
    message.error(error.value)
  }
}

// 获取代理状态颜色
const getProxyStatusColor = () => {
  const hasError = Object.values(proxyData.value).some(proxy => proxy.ErrorTimes > 0)
  return hasError ? 'error' : 'success'
}

const greeting = computed(() => {
  const hour = new Date().getHours()
  if (hour >= 5 && hour < 11) {
    return '主人早上好喵~'
  } else if (hour >= 11 && hour < 14) {
    return '主人中午好喵~'
  } else if (hour >= 14 && hour < 18) {
    return '主人下午好喵~'
  } else if (hour >= 18 && hour < 23) {
    return '主人晚上好喵~'
  } else {
    return '主人夜深了喵~早点休息喵~'
  }
})

// 获取公告信息
const fetchNoticeData = async () => {
  try {
    const response = await Service.getNoticeInfoApiInfoNoticeGetPost()

    if (response.code === 200) {
      // 检查是否需要显示公告
      if (response.if_need_show && response.data && Object.keys(response.data).length > 0) {
        noticeData.value = response.data
        noticeVisible.value = true
      }
    } else {
      console.warn('获取公告失败:', response.message)
    }
  } catch (error) {
    console.error('获取公告失败:', error)
  }
}

// 公告确认回调
const onNoticeConfirmed = () => {
  noticeVisible.value = false
  // message.success('公告已确认')
}

// 显示公告的处理函数
const showNotice = async () => {
  noticeLoading.value = true
  try {
    const response = await Service.getNoticeInfoApiInfoNoticeGetPost()

    if (response.code === 200) {
      // 忽略 if_need_show 字段，只要有公告数据就显示
      if (response.data && Object.keys(response.data).length > 0) {
        noticeData.value = response.data
        noticeVisible.value = true
      } else {
        message.info('暂无公告信息')
      }
    } else {
      message.error(response.message || '获取公告失败')
    }
  } catch (error) {
    console.error('显示公告失败:', error)
    message.error('显示公告失败，请稍后重试')
  } finally {
    noticeLoading.value = false
  }
}

onMounted(() => {
  fetchActivityData()
  fetchNoticeData()
})
</script>

<style scoped>
.header {
  margin-bottom: 24px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header h1 {
  margin: 0;
  color: var(--ant-color-text);
  font-size: 24px;
  font-weight: 600;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.notice-button {
  min-width: 120px;
}

/* 公告相关样式 */
.notice-modal {
  /* 自定义公告模态框样式 */
}

.activity-card {
  margin-bottom: 24px;
}

.resource-card {
  margin-bottom: 24px;
}

.activity-card :deep(.ant-card-head-title) {
  font-size: 18px;
  font-weight: 600;
}

.resource-card :deep(.ant-card-head-title) {
  font-size: 18px;
  font-weight: 600;
}

.resource-list {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.resource-item {
  display: flex;
  align-items: center;
  padding: 16px;
  background: var(--ant-color-bg-container);
  border: 1px solid var(--ant-color-border);
  border-radius: 8px;
  transition: all 0.2s ease;
}

.resource-item:hover {
  border-color: var(--ant-color-primary);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.drop-tip {
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
  margin-top: 2px;
}

.error-message {
  margin-bottom: 16px;
}

.activity-info {
  margin-bottom: 24px;
  padding: 16px;
  background: var(--ant-color-bg-container);
  border: 1px solid var(--ant-color-border);
  border-radius: 8px;
}

.activity-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 24px;
}

.activity-left {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.activity-right {
  flex-shrink: 0;
  text-align: right;
}

.activity-end-time {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
}

.activity-name {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.activity-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.activity-tip {
  font-size: 12px;
}

.time-icon {
  font-size: 14px;
  color: var(--ant-color-text-secondary);
}

.time-label {
  color: var(--ant-color-text-secondary);
  min-width: 80px;
}

.time-value {
  color: var(--ant-color-text);
  font-weight: 500;
}

.time-value.remaining {
  color: var(--ant-color-warning);
  font-weight: 600;
}

.activity-list {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.activity-item {
  display: flex;
  align-items: center;
  padding: 16px;
  background: var(--ant-color-bg-container);
  border: 1px solid var(--ant-color-border);
  border-radius: 8px;
  transition: all 0.2s ease;
}

.activity-item:hover {
  border-color: var(--ant-color-primary);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.stage-info {
  flex-shrink: 0;
  margin-right: 16px;
  text-align: center;
  min-width: 80px;
}

.stage-name {
  font-size: 16px;
  font-weight: 600;
  color: var(--ant-color-text);
  margin-bottom: 4px;
}

.stage-value {
  font-size: 12px;
  color: var(--ant-color-text-secondary);
}

.drop-info {
  display: flex;
  align-items: center;
  flex: 1;
}

.drop-image {
  flex-shrink: 0;
  width: 48px;
  height: 48px;
  margin-right: 12px;
  display: flex;
  align-items: center;
  justify-content: center;

  border-radius: 6px;
  overflow: hidden;
}

.drop-image img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.desc-icon {
  font-size: 24px;
  color: var(--ant-color-primary);
}

.drop-details {
  flex: 1;
  min-width: 0;
}

.drop-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--ant-color-text);
  margin-bottom: 4px;
  word-break: break-all;
}

.drop-id {
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
}

.empty-state {
  text-align: center;
  padding: 40px 0;
}

@media (max-width: 1200px) {
  .activity-list,
  .resource-list {
    grid-template-columns: repeat(3, 1fr);
  }
}

@media (max-width: 900px) {
  .activity-list,
  .resource-list {
    grid-template-columns: repeat(2, 1fr);
  }
}

/* 代理状态样式 */
.proxy-card {
  margin-bottom: 24px;
}

.proxy-card :deep(.ant-card-head-title) {
  font-size: 18px;
  font-weight: 600;
}

.proxy-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.proxy-item {
  padding: 16px;
  background: var(--ant-color-bg-container);
  border: 1px solid var(--ant-color-border);
  border-radius: 8px;
  transition: all 0.2s ease;
}

.proxy-item:hover {
  border-color: var(--ant-color-primary);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.proxy-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.proxy-username {
  display: flex;
  align-items: center;
  gap: 8px;
}

.user-icon {
  font-size: 16px;
  color: var(--ant-color-primary);
}

.username {
  font-size: 16px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.proxy-status {
  flex-shrink: 0;
}

.proxy-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  margin-bottom: 12px;
}

.stat-item {
  flex: 1;
  min-width: 0;
}

.stat-item.full-width {
  flex: 0 0 100%;
  /* 占满整行 */
}

.stat-item.half-width {
  flex: 0 0 calc(50% - 8px);
  /* 每个占一半宽度，减去间距 */
}

.stat-item {
  flex: 1;
  min-width: 0;
}

/* 小屏时自动折行成两列或一列 */
@media (max-width: 768px) {
  .proxy-stats {
    flex-wrap: wrap;
  }

  .stat-item {
    flex: 1 1 100%;
  }
}

@media (max-width: 768px) {
  .page-container {
    padding: 16px;
  }

  .activity-list,
  .resource-list {
    grid-template-columns: 1fr;
  }

  .activity-item,
  .resource-item {
    padding: 12px;
  }

  .drop-image {
    width: 40px;
    height: 40px;
    margin-right: 8px;
  }

  .proxy-item {
    padding: 12px;
  }

  .proxy-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }

  .proxy-stats :deep(.ant-col) {
    margin-bottom: 8px;
  }
}
</style>
