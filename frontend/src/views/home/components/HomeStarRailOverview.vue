<template>
  <a-card title="崩坏：星穹铁道活动信息" class="starrail-card" :loading="loading">
    <template #extra>
      <a-tag v-if="overview.Stale" color="orange">缓存数据</a-tag>
      <a-tag v-else-if="overview.version" color="blue">{{ overview.version }} 版本</a-tag>
    </template>

    <a-alert
      v-if="overview.Message"
      :message="overview.Message"
      :type="overview.Available ? 'warning' : 'error'"
      show-icon
      class="status-alert"
    />

    <div v-if="overview.Available && !loading" class="version-overview">
      <div>
        <div class="version-name">{{ overview.versionName }}</div>
        <div class="version-time">
          <ClockCircleOutlined />
          <span>{{ formatTime(overview.endTime) }} 结束</span>
        </div>
      </div>
      <a-statistic-countdown
        title="当前版本剩余时间"
        :value="getCountdownValue(overview.endTime)"
        format="D 天 H 时 m 分"
        :value-style="countdownValueStyle"
        @finish="emit('refresh')"
      />
    </div>

    <div v-if="activeActivities.length" class="activity-list">
      <div v-for="activity in activeActivities" :key="activity.name" class="activity-item">
        <div class="activity-name">{{ activity.name }}</div>
        <a-statistic-countdown
          :value="getCountdownValue(activity.endTime)"
          format="D 天 H 时"
          :value-style="activityCountdownStyle"
          @finish="emit('refresh')"
        />
        <div class="activity-end-time">{{ formatTime(activity.endTime) }} 结束</div>
      </div>
    </div>

    <a-empty v-else-if="!loading" description="暂无进行中的星穹铁道活动" />
  </a-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { CSSProperties } from 'vue'
import { ClockCircleOutlined } from '@ant-design/icons-vue'
import type { StarRailActivityOverview } from '@/types/home'

defineOptions({ name: 'HomeStarRailOverview' })

const props = defineProps<{
  loading: boolean
  overview: StarRailActivityOverview
}>()

const emit = defineEmits<{ refresh: [] }>()

const MAX_VISIBLE_ACTIVITIES = 4

const activeActivities = computed(() => {
  const now = Date.now()
  return props.overview.activities
    .filter(activity => {
      return (
        getCountdownValue(activity.startTime) <= now && getCountdownValue(activity.endTime) > now
      )
    })
    .sort((left, right) => getCountdownValue(left.endTime) - getCountdownValue(right.endTime))
    .slice(0, MAX_VISIBLE_ACTIVITIES)
})

const countdownValueStyle: CSSProperties = {
  color: 'var(--ant-color-text)',
  fontSize: '18px',
  fontWeight: 600,
}

const activityCountdownStyle: CSSProperties = {
  color: 'var(--ant-color-primary)',
  fontSize: '13px',
  fontWeight: 600,
}

const getCountdownValue = (value: string) => new Date(value).getTime()

const formatTime = (value: string) =>
  new Date(value).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
</script>

<style scoped>
.starrail-card {
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);
}

.starrail-card :deep(.ant-card-head-title) {
  font-size: 18px;
  font-weight: 600;
}

.status-alert {
  margin-bottom: 16px;
}

.version-overview {
  margin-bottom: 16px;
  padding: 16px;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  border: 1px solid var(--ant-color-border);
  border-radius: 8px;
}

.version-name {
  margin-bottom: 10px;
  color: var(--ant-color-text);
  font-size: 18px;
  font-weight: 600;
}

.version-time {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--ant-color-text-secondary);
  font-size: 14px;
}

.activity-list {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
}

.activity-item {
  min-width: 0;
  min-height: 104px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  border: 1px solid var(--ant-color-border);
  border-radius: 8px;
  transition:
    border-color 0.2s ease,
    box-shadow 0.2s ease;
}

.activity-item:hover {
  border-color: var(--ant-color-primary);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.activity-name {
  min-width: 0;
  margin-bottom: 8px;
  overflow: hidden;
  color: var(--ant-color-text);
  font-size: 15px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.activity-end-time {
  margin-top: 4px;
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
}

@media (max-width: 1240px) {
  .activity-list {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 800px) {
  .version-overview {
    flex-direction: column;
  }

  .activity-list {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 560px) {
  .activity-list {
    grid-template-columns: 1fr;
  }
}
</style>
