<template>
  <div class="header">
    <a-typography-title>{{ greeting }}</a-typography-title>
    <!-- 鍙充笂瑙掑叕鍛婃寜閽?-->
    <div class="header-actions">
      <a-button
        type="primary"
        ghost
        :loading="noticeLoading"
        class="notice-button"
        @click="showNotice"
      >
        <template #icon>
          <BellOutlined />
        </template>
        鏌ョ湅鍏憡
      </a-button>
    </div>
  </div>

  <!-- 鍏憡妯℃€佹 -->
  <NoticeModal
    v-model:visible="noticeVisible"
    :notice-data="noticeData"
    @confirmed="onNoticeConfirmed"
  />

  <div class="content">
    <!-- 褰撴湡娲诲姩鍏冲崱 -->
    <a-card
      v-if="activityData?.length"
      title="褰撴湡娲诲姩鍏冲崱"
      class="activity-card"
      :loading="loading"
    >
      <div v-if="error" class="error-message">
        <a-alert :message="error" type="error" show-icon closable @close="error = ''" />
      </div>

      <!-- 娲诲姩淇℃伅灞曠ず -->
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
            <!-- 娲诲姩宸茬粨鏉熸椂鏄剧ず鎻愮ず -->
            <a-statistic-countdown
              v-if="getActivityTimeStatus(currentActivity.UtcExpireTime) === 'ended'"
              title=""
              :value="getCountdownValue(currentActivity.UtcExpireTime)"
              format="活动已结束"
              :value-style="{
                color: '#ff4d4f',
                fontWeight: 'bold',
                fontSize: '18px',
              }"
              @finish="onCountdownFinish"
            />

            <!-- 鍓╀綑鏃堕棿灏忎簬涓ゅぉ鏃舵樉绀虹偒褰╁€掕鏃?-->
            <a-statistic-countdown
              v-else-if="getActivityTimeStatus(currentActivity.UtcExpireTime) === 'warning'"
              title="褰撴湡娲诲姩鍓╀綑鏃堕棿"
              :value="getCountdownValue(currentActivity.UtcExpireTime)"
              format="D 澶?H 鏃?m 鍒?ss 绉?SSS 姣"
              class="rainbow-text"
              @finish="onCountdownFinish"
            />

            <!-- 鍓╀綑鏃堕棿澶т簬绛変簬涓ゅぉ鏃舵樉绀哄父瑙勫€掕鏃?-->
            <a-statistic-countdown
              v-else
              title="褰撴湡娲诲姩鍓╀綑鏃堕棿"
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
                v-if="getMaterialImage(item.Drop)"
                :src="getMaterialImage(item.Drop)"
                :alt="item.DropName"
                @error="handleImageError"
              />
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

    <!-- 璧勬簮鏀堕泦鍏冲崱 -->
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

    <!-- 浠ｇ悊鐘舵€?-->
    <a-card title="代理状态" class="proxy-card" :loading="loading">
      <template #extra>
        <a-tag :color="getProxyStatusColor()">{{ Object.keys(proxyData).length }} 个用户</a-tag>
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
                <!--                    {{ proxy.ErrorTimes > 0 ? '鏈夐敊璇? : '姝ｅ父' }}-->
                <!--                  </a-tag>-->
                <!--                </div>-->
              </div>

              <div class="proxy-stats">
                <!-- 绗竴琛岋細鏈€鍚庝唬鐞嗘椂闂达紝鐙崰涓€琛?-->
                <div class="stat-item full-width">
                  <a-statistic title="最后代理时间" :value="formatProxyDisplay(proxy.LastProxyDate)" />
                </div>

                <!-- 绗簩琛岋細浠ｇ悊娆℃暟 鍜?閿欒娆℃暟 -->
                <div class="stat-item half-width">
                  <a-statistic title="浠ｇ悊娆℃暟" :value="proxy.ProxyTimes" />
                </div>
                <div class="stat-item half-width">
                  <a-statistic
                    title="閿欒娆℃暟"
                    :value="proxy.ErrorTimes"
                    :value-style="{ color: proxy.ErrorTimes > 0 ? '#ff4d4f' : undefined }"
                  />
                </div>
              </div>

              <!--              &lt;!&ndash; 閿欒淇℃伅 &ndash;&gt;-->
              <!--              <div-->
              <!--                v-if="proxy.ErrorTimes > 0 && Object.keys(proxy.ErrorInfo).length > 0"-->
              <!--                class="proxy-errors"-->
              <!--              >-->
              <!--                <a-alert message="閿欒淇℃伅" type="error" show-icon size="small" class="error-alert">-->
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
import { ref, onMounted, computed, watch } from 'vue'
import { message } from 'ant-design-vue'
import { ClockCircleOutlined, UserOutlined, BellOutlined } from '@ant-design/icons-vue'
import { apiRuntime, infoApi } from '@/api'
import NoticeModal from '@/components/NoticeModal.vue'
import { useAudioPlayer } from '@/composables/useAudioPlayer'
import { useAppInitialization } from '@/composables/useAppInitialization'
import { formatBackendDateTime } from '@/utils/dateDisplay'
const logger = window.electronAPI.getLogger('棣栭〉')

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

// 鍏憡绯荤粺鐩稿叧鐘舵€?
const noticeVisible = ref(false)
const noticeData = ref<Record<string, string>>({})
const noticeLoading = ref(false)
const { isBootstrapping } = useAppInitialization()

// 闊抽鎾斁鍣?
const { playSound } = useAudioPlayer()

// 鑾峰彇褰撳墠娲诲姩淇℃伅
const currentActivity = computed(() => {
  if (!activityData.value.length) return null
  return activityData.value[0]?.Activity
})

const formatProxyDisplay = (dateStr: string) => {
  if (dateStr === '鏆傛棤浠ｇ悊鏁版嵁') {
    return dateStr
  }
  return formatBackendDateTime(dateStr)
}

// 鏍煎紡鍖栨椂闂存樉绀?- 鐩存帴浣跨敤缁欏畾鏃堕棿锛屼笉杩涜鏃跺尯杞崲
const formatTime = (timeString: string) => {
  try {
    // 鐩存帴浣跨敤缁欏畾鐨勬椂闂村瓧绗︿覆锛屽洜涓哄凡缁忔槸涓浗鏃堕棿
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

// 鑾峰彇鍊掕鏃剁殑鐩爣鏃堕棿鎴?
const getCountdownValue = (expireTime: string) => {
  try {
    return new Date(expireTime).getTime()
  } catch {
    return Date.now()
  }
}

// 妫€鏌ュ墿浣欐椂闂寸姸鎬侊細normal锛?2澶╋級銆亀arning锛?=2澶?0锛夈€乪nded锛?=0锛?
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

// 鍊掕鏃剁粨鏉熷洖璋?
const onCountdownFinish = () => {
  message.warning('活动已结束')
  // 閲嶆柊鑾峰彇鏁版嵁
  fetchActivityData()
}

const getMaterialImage = (dropName: string) => {
  if (!dropName) {
    return ''
  }
  // 鐩存帴鎷兼帴鍚庣鍥剧墖鎺ュ彛鍦板潃
  return `${apiRuntime.baseUrl}/api/res/materials/${dropName}.png`
}

const handleImageError = (event: Event) => {
  const img = event.target as HTMLImageElement
  img.style.display = 'none'
}

const fetchActivityData = async () => {
  loading.value = true
  error.value = ''

  try {
    const response = await infoApi.getOverview()

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
      error.value = response.message || '鑾峰彇鏁版嵁澶辫触'
    }
  } catch (err) {
    const errorMsg = err instanceof Error ? err.message : String(err)
    logger.error(`鑾峰彇鏁版嵁澶辫触: ${errorMsg}`)
    error.value = '网络请求失败，请检查连接'
  } finally {
    loading.value = false
  }
}

// 鑾峰彇浠ｇ悊鐘舵€侀鑹?
const getProxyStatusColor = () => {
  const hasError = Object.values(proxyData.value).some(proxy => proxy.ErrorTimes > 0)
  return hasError ? 'error' : 'success'
}

const greeting = computed(() => {
  const hour = new Date().getHours()
  if (hour >= 5 && hour < 11) {
    return '鏃╀笂濂斤紝鍗氬＋锛屽挄~'
  } else if (hour >= 11 && hour < 14) {
    return '涓崍濂斤紝鍗氬＋锛屽挄~'
  } else if (hour >= 14 && hour < 18) {
    return '涓嬪崍濂斤紝鍗氬＋锛屽挄~'
  } else if (hour >= 18 && hour < 23) {
    return '鏅氫笂濂斤紝鍗氬＋锛屽挄~'
  } else {
    return '澶滄繁浜嗭紝鍗氬＋锛岃娉ㄦ剰浼戞伅锛屽挄~'
  }
})

// 鑾峰彇鍏憡淇℃伅
const fetchNoticeData = async () => {
  try {
    const response = await infoApi.getNotice()

    if (response.code === 200) {
      // 妫€鏌ユ槸鍚﹂渶瑕佹樉绀哄叕鍛?
      if (response.if_need_show && response.data && Object.keys(response.data).length > 0) {
        noticeData.value = response.data
        noticeVisible.value = true
        // 鎾斁鍏憡灞曠ず闊抽
        await playSound('announcement_display')
      }
    } else {
      logger.warn(`鑾峰彇鍏憡澶辫触: ${response.message}`)
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`鑾峰彇鍏憡澶辫触: ${errorMsg}`)
  }
}

// 鍏憡纭鍥炶皟
const onNoticeConfirmed = () => {
  noticeVisible.value = false
}

// 鏄剧ず鍏憡鐨勫鐞嗗嚱鏁?
const showNotice = async () => {
  noticeLoading.value = true
  try {
    const response = await infoApi.getNotice()

    if (response.code === 200) {
      // 蹇界暐 if_need_show 瀛楁锛屽彧瑕佹湁鍏憡鏁版嵁灏辨樉绀?
      if (response.data && Object.keys(response.data).length > 0) {
        noticeData.value = response.data
        noticeVisible.value = true
        // 鎵嬪姩鏌ョ湅鍏憡鏃朵篃鎾斁闊抽
        await playSound('announcement_display')
      } else {
        message.info('鏆傛棤鍏憡淇℃伅')
      }
    } else {
      message.error(response.message || '鑾峰彇鍏憡澶辫触')
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`鏄剧ず鍏憡澶辫触: ${errorMsg}`)
    message.error('鏄剧ず鍏憡澶辫触锛岃绋嶅悗閲嶈瘯')
  } finally {
    noticeLoading.value = false
  }
}

const loadHomeData = () => {
  fetchActivityData()
  fetchNoticeData()
}

onMounted(() => {
  if (isBootstrapping.value) {
    loading.value = true
    noticeLoading.value = true

    const stopWatching = watch(isBootstrapping, bootstrapping => {
      if (bootstrapping) {
        return
      }

      stopWatching()
      loadHomeData()
    })
    return
  }

  loadHomeData()
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

/* 鍝嶅簲寮忚璁?*/
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


