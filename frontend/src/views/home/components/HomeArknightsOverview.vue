<template>
  <div class="arknights-overview">
    <div v-if="error" class="error-message">
      <a-alert :message="error" type="error" show-icon closable @close="emit('clear-error')" />
    </div>

    <a-card
      v-if="activityData.length"
      title="明日方舟活动信息"
      class="arknights-card"
      :loading="loading"
    >
      <div v-if="currentActivity && !loading" class="activity-info">
        <div class="activity-header">
          <div class="activity-left">
            <div class="activity-title">{{ currentActivity.Tip }}</div>
            <div class="activity-end-time">
              <ClockCircleOutlined class="time-icon" />
              <span class="time-label">结束时间：</span>
              <span class="time-value">{{ formatTime(currentActivity.UtcExpireTime) }}</span>
            </div>
          </div>

          <div class="activity-right">
            <a-statistic-countdown
              v-if="getActivityTimeStatus(currentActivity.UtcExpireTime) === 'ended'"
              title=""
              :value="getCountdownValue(currentActivity.UtcExpireTime)"
              format="活动已结束"
              :value-style="{
                color: 'var(--ant-color-error)',
                fontWeight: '600',
                fontSize: '18px',
              }"
              @finish="onCountdownFinish"
            />
            <a-statistic-countdown
              v-else
              title="当期活动剩余时间"
              :value="getCountdownValue(currentActivity.UtcExpireTime)"
              :format="
                getActivityTimeStatus(currentActivity.UtcExpireTime) === 'warning'
                  ? 'D 天 H 时 m 分 ss 秒'
                  : 'D 天 H 时 m 分'
              "
              :value-style="{
                color:
                  getActivityTimeStatus(currentActivity.UtcExpireTime) === 'warning'
                    ? 'var(--ant-color-warning)'
                    : 'var(--ant-color-text)',
                fontWeight: '600',
                fontSize: '18px',
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
              <div class="drop-name">{{ item.DropName }}</div>
            </div>
          </div>
        </div>
      </div>
    </a-card>

    <a-card title="今日开放资源收集关卡" class="resource-card" :loading="loading">
      <div v-if="resourceData.length" class="resource-list">
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
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { message } from 'ant-design-vue'
import { ClockCircleOutlined } from '@ant-design/icons-vue'
import { OpenAPI } from '@/api'
import type { ActivityItem, ResourceItem } from '@/types/home'

defineOptions({
  name: 'HomeArknightsOverview',
})

interface Props {
  loading: boolean
  error: string
  activityData: ActivityItem[]
  resourceData: ResourceItem[]
}

const props = defineProps<Props>()

const emit = defineEmits<{
  refresh: []
  'clear-error': []
}>()

const currentActivity = computed(() => props.activityData[0]?.Activity ?? null)

const formatTime = (timeString: string) => {
  const date = new Date(timeString)
  if (Number.isNaN(date.getTime())) {
    return timeString
  }
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

const getCountdownValue = (expireTime: string) => {
  const timestamp = new Date(expireTime).getTime()
  return Number.isNaN(timestamp) ? Date.now() : timestamp
}

const getActivityTimeStatus = (expireTime: string): 'normal' | 'warning' | 'ended' => {
  const remaining = getCountdownValue(expireTime) - Date.now()
  if (remaining <= 0) return 'ended'
  if (remaining <= 2 * 24 * 60 * 60 * 1000) return 'warning'
  return 'normal'
}

const onCountdownFinish = () => {
  message.warning('活动已结束')
  emit('refresh')
}

const getMaterialImage = (dropName: string) => {
  return dropName ? `${OpenAPI.BASE}/api/res/materials/${dropName}.png` : ''
}

const handleImageError = (event: Event) => {
  const image = event.target as HTMLImageElement
  image.style.display = 'none'
}
</script>

<style scoped>
.arknights-overview {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.arknights-card,
.resource-card {
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);
}

.arknights-card :deep(.ant-card-head-title),
.resource-card :deep(.ant-card-head-title) {
  font-size: 18px;
  font-weight: 600;
}

.resource-list {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 12px;
}

.activity-list {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
}

.resource-item,
.activity-item {
  min-height: 82px;
  padding: 16px;
  display: flex;
  align-items: center;
  border: 1px solid var(--ant-color-border);
  border-radius: 8px;
  transition:
    border-color 0.2s ease,
    box-shadow 0.2s ease;
}

.resource-item:hover,
.activity-item:hover {
  border-color: var(--ant-color-primary);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.error-message {
  margin-bottom: 16px;
}

.activity-info {
  margin-bottom: 24px;
  padding: 16px;
  border: 1px solid var(--ant-color-border);
  border-radius: 8px;
}

.activity-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
}

.activity-left {
  min-width: 0;
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 12px;
}

.activity-right {
  flex-shrink: 0;
  text-align: right;
}

.activity-title {
  color: var(--ant-color-text);
  font-size: 18px;
  font-weight: 600;
}

.activity-end-time {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
}

.time-icon,
.time-label {
  color: var(--ant-color-text-secondary);
}

.time-value {
  color: var(--ant-color-text);
  font-weight: 500;
}

.stage-info {
  min-width: 50px;
  max-width: 80px;
  margin-right: 16px;
  flex: 1;
  text-align: center;
}

.stage-name {
  color: var(--ant-color-text);
  font-size: 16px;
  font-weight: 600;
}

.drop-info {
  min-width: 0;
  display: flex;
  align-items: center;
  flex: 2;
}

.drop-image {
  width: 48px;
  height: 48px;
  margin-right: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  overflow: hidden;
  border-radius: 6px;
}

.drop-image img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.drop-details {
  min-width: 70px;
  flex: 1;
}

.drop-name {
  overflow-wrap: anywhere;
  color: var(--ant-color-text);
  font-size: 14px;
  font-weight: 500;
}

.drop-tip {
  margin-top: 2px;
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
}

.empty-state {
  padding: 40px 0;
  text-align: center;
}

.empty-image {
  width: 48%;
  max-width: 180px;
  opacity: 0.82;
}

@media (max-width: 1240px) {
  .activity-list,
  .resource-list {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 800px) {
  .activity-list,
  .resource-list {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .activity-header {
    flex-direction: column;
  }

  .activity-right {
    text-align: left;
  }
}

@media (max-width: 560px) {
  .activity-list,
  .resource-list {
    grid-template-columns: 1fr;
  }
}
</style>
