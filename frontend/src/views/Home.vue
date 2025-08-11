<template>

    <div class="header">
      <a-typography-title>主人早上好喵~</a-typography-title>
    </div>
    
    <div class="content">
      <!-- 当期活动关卡 -->
      <a-card title="当期活动关卡" class="activity-card" :loading="loading">
        <template #extra>
          <a-button type="text" @click="refreshActivity" :loading="loading">
            <template #icon>
              <ReloadOutlined />
            </template>
            刷新
          </a-button>
        </template>
        
        <div v-if="error" class="error-message">
          <a-alert
            :message="error"
            type="error"
            show-icon
            closable
            @close="error = ''"
          />
        </div>
        
        <!-- 活动信息展示 -->
        <div v-if="currentActivity && !loading" class="activity-info">
          <div class="activity-header">
            <div class="activity-name">
<!--              <CalendarOutlined class="activity-icon" />-->
              <span class="activity-title">{{ currentActivity.StageName }}</span>
              <a-tag color="blue" class="activity-tip">{{ currentActivity.Tip }}</a-tag>
            </div>
            <div class="activity-time">
              <div class="time-item">
                <ClockCircleOutlined class="time-icon" />
                <span class="time-label">剩余时间：</span>
                <span class="time-value remaining">{{ getTimeRemaining(currentActivity.UtcExpireTime, currentActivity.TimeZone) }}</span>
              </div>
              <div class="time-item">
                <span class="time-label">结束时间：</span>
                <span class="time-value">{{ formatTime(currentActivity.UtcExpireTime, currentActivity.TimeZone) }}</span>
              </div>
            </div>
          </div>
        </div>
        
        <div v-if="activityData?.length" class="activity-list">
          <div
            v-for="item in activityData"
            :key="item.Value"
            class="activity-item"
          >
            <div class="stage-info">
              <div class="stage-name">{{ item.Display }}</div>
<!--              <div class="stage-value">{{ item.Value }}</div>-->
            </div>
            
            <div class="drop-info">
              <div class="drop-image">
                <img
                  :src="item.DropName.startsWith('DESC:') ? getMaterialImage('固源岩') : getMaterialImage(item.DropName)"
                  :alt="item.DropName.startsWith('DESC:') ? '固源岩' : item.DropName"
                  @error="handleImageError"
                />
              </div>
              
              <div class="drop-details">
                <div class="drop-name">
                  {{ item.DropName.startsWith('DESC:') ? item.DropName.substring(5) : item.DropName }}
                </div>
<!--                <div v-if="item.Drop && !item.DropName.startsWith('DESC:')" class="drop-id">-->
<!--                  ID: {{ item.Drop }}-->
<!--                </div>-->
              </div>
            </div>
          </div>
        </div>
        
        <div v-else-if="!loading" class="empty-state">
          <a-empty description="暂无活动关卡数据" />
        </div>
      </a-card>
    </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { message } from 'ant-design-vue'
import { ReloadOutlined, InfoCircleOutlined, CalendarOutlined, ClockCircleOutlined } from '@ant-design/icons-vue'
import { Service } from '@/api'

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

const loading = ref(false)
const error = ref('')
const activityData = ref<ActivityItem[]>([])

// 获取当前活动信息
const currentActivity = computed(() => {
  if (!activityData.value.length) return null
  return activityData.value[0]?.Activity
})

// 格式化时间显示 - 直接使用给定时间，不进行时区转换
const formatTime = (timeString: string, timeZone: number) => {
  try {
    // 直接使用给定的时间字符串，因为已经是中国时间
    const date = new Date(timeString)
    return date.toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit'
    })
  } catch {
    return timeString
  }
}

// 计算活动剩余时间
const getTimeRemaining = (expireTime: string, timeZone: number) => {
  try {
    const expire = new Date(expireTime)
    const now = new Date()
    const remaining = expire.getTime() - now.getTime()
    
    if (remaining <= 0) return '已结束'
    
    const days = Math.floor(remaining / (1000 * 60 * 60 * 24))
    const hours = Math.floor((remaining % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60))
    
    if (days > 0) {
      return `${days}天${hours}小时`
    } else if (hours > 0) {
      return `${hours}小时`
    } else {
      const minutes = Math.floor((remaining % (1000 * 60 * 60)) / (1000 * 60))
      return `${minutes}分钟`
    }
  } catch {
    return '未知'
  }
}

const getMaterialImage = (dropName: string) => {
  try {
    return new URL(`../assets/materials/${dropName}.png`, import.meta.url).href
  } catch {
    return ''
  }
}

const handleImageError = (event: Event) => {
  const img = event.target as HTMLImageElement
  img.style.display = 'none'
}

const fetchActivityData = async () => {
  loading.value = true
  error.value = ''
  
  try {
    const response = await Service.addOverviewApiInfoGetOverviewPost()
    
    if (response.code === 200 && response.data?.ALL) {
      activityData.value = response.data.ALL
    } else {
      error.value = response.message || '获取活动数据失败'
    }
  } catch (err) {
    console.error('获取活动数据失败:', err)
    error.value = '网络请求失败，请检查连接'
  } finally {
    loading.value = false
  }
}

const refreshActivity = async () => {
  await fetchActivityData()
  if (!error.value) {
    message.success('活动数据已刷新')
  }
}

onMounted(() => {
  fetchActivityData()
})
</script>

<style scoped>

.header {
  margin-bottom: 24px;
}

.header h1 {
  margin: 0;
  color: var(--ant-color-text);
  font-size: 24px;
  font-weight: 600;
}



.activity-card {
  margin-bottom: 24px;
}

.activity-card :deep(.ant-card-head-title) {
  font-size: 18px;
  font-weight: 600;
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
  flex-direction: column;
  gap: 12px;
}

.activity-name {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.activity-icon {
  font-size: 16px;
  color: var(--ant-color-primary);
}

.activity-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.activity-tip {
  font-size: 12px;
}

.activity-time {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.time-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
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
  background: var(--ant-color-fill-quaternary);
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
  .activity-list {
    grid-template-columns: repeat(3, 1fr);
  }
}

@media (max-width: 900px) {
  .activity-list {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .page-container {
    padding: 16px;
  }
  
  .activity-list {
    grid-template-columns: 1fr;
  }
  
  .activity-item {
    padding: 12px;
  }
  
  .drop-image {
    width: 40px;
    height: 40px;
    margin-right: 8px;
  }
}
</style>