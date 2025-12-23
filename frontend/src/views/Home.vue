<template>
  <div class="header">
    <a-typography-title>{{ greeting }}</a-typography-title>
    <!-- 右上角公告按钮 -->
    <div class="header-actions">
      <a-button type="primary" ghost :loading="noticeLoading" class="notice-button" @click="showNotice">
        <template #icon>
          <BellOutlined />
        </template>
        查看公告
      </a-button>
    </div>
  </div>

  <!-- 公告模态框 -->
  <NoticeModal v-model:visible="noticeVisible" :notice-data="noticeData" @confirmed="onNoticeConfirmed" />

  <div class="content">
    <!-- 当期活动关卡 -->
    <a-card v-if="activityData?.length" title="当期活动关卡" class="activity-card" :loading="loading">
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
            <!-- 活动已结束时显示提示 -->
            <a-statistic-countdown v-if="getActivityTimeStatus(currentActivity.UtcExpireTime) === 'ended'" title=""
              :value="getCountdownValue(currentActivity.UtcExpireTime)" format="活动已结束" :value-style="{
                color: '#ff4d4f',
                fontWeight: 'bold',
                fontSize: '18px',
              }" @finish="onCountdownFinish" />

            <!-- 剩余时间小于两天时显示炫彩倒计时 -->
            <a-statistic-countdown v-else-if="getActivityTimeStatus(currentActivity.UtcExpireTime) === 'warning'"
              title="当期活动剩余时间" :value="getCountdownValue(currentActivity.UtcExpireTime)"
              format="D 天 H 时 m 分 ss 秒 SSS 毫秒" class="rainbow-text" @finish="onCountdownFinish" />

            <!-- 剩余时间大于等于两天时显示常规倒计时 -->
            <a-statistic-countdown v-else title="当期活动剩余时间" :value="getCountdownValue(currentActivity.UtcExpireTime)"
              format="D 天 H 时 m 分" :value-style="{
                color: 'var(--ant-color-text)',
                fontWeight: '600',
                fontSize: '20px',
              }" @finish="onCountdownFinish" />
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
              <img v-if="getMaterialImage(item.Drop)" :src="getMaterialImage(item.Drop)" :alt="item.DropName"
                @error="handleImageError" />
            </div>

            <div class="drop-details">
              <div class="drop-name">
                {{ item.DropName }}
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
              <img v-if="getMaterialImage(item.Drop)" :src="getMaterialImage(item.Drop)" :alt="item.DropName"
                @error="handleImageError" />
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
                  <a-statistic title="最后代理时间" :value="formatProxyDisplay(proxy.LastProxyDate)" />
                </div>

                <!-- 第二行：代理次数 和 错误次数 -->
                <div class="stat-item half-width">
                  <a-statistic title="代理次数" :value="proxy.ProxyTimes" />
                </div>
                <div class="stat-item half-width">
                  <a-statistic title="错误次数" :value="proxy.ErrorTimes"
                    :value-style="{ color: proxy.ErrorTimes > 0 ? '#ff4d4f' : undefined }" />
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
import { ClockCircleOutlined, UserOutlined, BellOutlined } from '@ant-design/icons-vue'
import { Service } from '@/api/services/Service'
import NoticeModal from '@/components/NoticeModal.vue'
import { useAudioPlayer } from '@/composables/useAudioPlayer'
import dayjs from 'dayjs'
import { mirrorManager } from '@/utils/mirrorManager'
import { getLogger } from '@/utils/logger'

const logger = getLogger('首页')

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

// 音频播放器
const { playSound } = useAudioPlayer()

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

// 检查剩余时间状态：normal（>2天）、warning（<=2天>0）、ended（<=0）
const getActivityTimeStatus = (expireTime: string): 'normal' | 'warning' | 'ended' => {
  try {
    const expire = new Date(expireTime)
    const now = new Date()
    const remaining = expire.getTime() - now.getTime()
    const twoDaysInMs = 2 * 24 * 60 * 60 * 1000
    if (remaining <= 0) return 'ended'
    if (remaining <= twoDaysInMs) return 'warning'
    return 'normal'
  } catch {
    return 'ended'
  }
}

// 获取代理时间戳 - 解析后端返回的中文日期格式
const getProxyTimestamp = (dateStr: string) => {
  if (!dateStr) return Date.now()

  // 处理后端返回的中文日期格式: "2025年11月05日 16:02:00"
  try {
    // 将中文日期格式转换为标准格式
    const standardFormat = dateStr
      .replace(/年/g, '-')
      .replace(/月/g, '-')
      .replace(/日/g, '')
      .trim()

    const t = new Date(standardFormat).getTime()
    return Number.isNaN(t) ? Date.now() : t
  } catch {
    // 兜底：尝试让浏览器自己解析
    const t = new Date(dateStr).getTime()
    return Number.isNaN(t) ? Date.now() : t
  }
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
  return `${mirrorManager.getApiEndpoint('local')}/api/res/materials/${dropName}.png`
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
    logger.error('获取数据失败:', err)
    error.value = '网络请求失败，请检查连接'
  } finally {
    loading.value = false
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
        // 播放公告展示音频
        await playSound('announcement_display')
      }
    } else {
      logger.warn('获取公告失败:', response.message)
    }
  } catch (error) {
    logger.error('获取公告失败:', error)
  }
}

// 公告确认回调
const onNoticeConfirmed = () => {
  noticeVisible.value = false
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
        // 手动查看公告时也播放音频
        await playSound('announcement_display')
      } else {
        message.info('暂无公告信息')
      }
    } else {
      message.error(response.message || '获取公告失败')
    }
  } catch (error) {
    logger.error('显示公告失败:', error)
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

.activity-card,
.resource-card,
.proxy-card {
  margin-bottom: 24px;
}

.activity-card :deep(.ant-card-head-title),
.resource-card :deep(.ant-card-head-title),
.proxy-card :deep(.ant-card-head-title) {
  font-size: 18px;
  font-weight: 600;
}

.resource-list {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 16px;
}

.resource-item,
.activity-item {
  display: flex;
  align-items: center;
  padding: 16px;
  background: var(--ant-color-bg-container);
  border: 1px solid var(--ant-color-border);
  border-radius: 8px;
  transition: all 0.2s ease;
}

.resource-item:hover,
.activity-item:hover {
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

.activity-list {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.stage-info {
  flex: 1;
  margin-right: 16px;
  text-align: center;
  min-width: 50px;
  max-width: 80px;
}

.stage-name {
  font-size: 16px;
  font-weight: 600;
  color: var(--ant-color-text);
  margin-bottom: 4px;
}

.drop-info {
  display: flex;
  align-items: center;
  flex: 2;
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

.drop-details {
  flex: 1;
  min-width: 70px;
}

.drop-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--ant-color-text);
  margin-bottom: 4px;
  word-break: break-all;
}

.empty-state {
  text-align: center;
  padding: 40px 0;
}

.proxy-list .proxy-item {
  padding: 16px;
  background: var(--ant-color-bg-container);
  border: 1px solid var(--ant-color-border);
  border-radius: 8px;
  margin-bottom: 16px;
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
  color: var(--ant-color-text-secondary);
}

.username {
  font-weight: 600;
  color: var(--ant-color-text);
}

.proxy-stats {
  display: grid;
  grid-template-columns: 1fr;
  gap: 16px;
}

.stat-item.full-width {
  grid-column: 1 / -1;
}

.stat-item.half-width {
  display: inline-block;
}

.proxy-stats .stat-item.half-width:nth-child(2),
.proxy-stats .stat-item.half-width:nth-child(3) {
  display: inline-grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.rainbow-text {
  font-weight: bold;
  font-size: 18px;
  background: linear-gradient(270deg, #ff4d4f, #fffa00, #00ffea, #ff4d4f, #ff4d4f);
  background-size: 400% 400%;
  color: transparent;
  background-clip: text;
  -webkit-background-clip: text;
  animation: rainbow-move 4s linear infinite;
}

@keyframes rainbow-move {
  0% {
    background-position: 0 50%;
  }

  100% {
    background-position: 100% 50%;
  }
}

/* 响应式设计 */
@media (max-width: 1500px) {

  .activity-list,
  .resource-list {
    grid-template-columns: repeat(4, 1fr);
  }
}

@media (max-width: 1240px) {

  .activity-list,
  .resource-list {
    grid-template-columns: repeat(3, 1fr);
  }
}

@media (max-width: 800px) {
  .header {
    flex-direction: column;
    gap: 16px;
    align-items: stretch;
  }

  .activity-list,
  .resource-list {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
