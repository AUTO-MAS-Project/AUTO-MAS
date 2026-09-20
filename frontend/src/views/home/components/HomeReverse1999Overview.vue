<template>
  <a-card :title="t('home.module.reverse1999')" class="r1999-card" :loading="loading">
    <template #extra>
      <div class="card-extra">
        <a-typography-link
          href="https://api.1999.fan"
          target="_blank"
          rel="noreferrer"
          class="source-link"
          @click="handleExternalLink"
        >
          {{ t('home.sra.poweredByM9A') }}
        </a-typography-link>
        <a-tag v-if="overview.Stale" color="orange">{{ t('home.sra.stale') }}</a-tag>
      </div>
    </template>

    <a-alert
      v-if="overview.Message"
      :message="overview.Message"
      :type="overview.Available ? 'warning' : 'error'"
      show-icon
      class="status-alert"
    />

    <!-- 版本封面、版本名与版本倒计时由上方的轮播横幅统一承担，这里只留进行中的活动 -->
    <div v-if="activeActivities.length" class="activity-rows">
      <div
        v-for="activity in activeActivities"
        :key="`${activity.name}-${activity.endTime}`"
        class="activity-row"
      >
        <div class="activity-row-main">
          <div class="activity-row-name">{{ activity.name }}</div>
          <div v-if="activity.description" class="activity-row-desc">
            {{ activity.description }}
          </div>
        </div>

        <div class="activity-row-meta">
          <a-statistic-countdown
            :value="getCountdownValue(activity.endTime)"
            :format="t('home.countdown.dh')"
            :value-style="activityCountdownStyle"
          />
          <div class="activity-row-time">
            {{ t('home.sra.endedAt', { time: formatTime(activity.endTime) }) }}
          </div>
        </div>
      </div>
    </div>

    <a-empty
      v-else-if="!loading && overview.Available"
      :description="t('home.empty.reverse1999')"
    />
  </a-card>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed } from 'vue'
import type { CSSProperties } from 'vue'
import type { Reverse1999ActivityOverview } from '@/types/home'
import { handleExternalLink } from '@/utils/openExternal'

defineOptions({ name: 'HomeReverse1999Overview' })

const { t } = useI18n()

const props = withDefaults(
  defineProps<{
    loading: boolean
    overview: Reverse1999ActivityOverview
  }>(),
  {}
)

const ACCENT = '#e0484f'
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

const activityCountdownStyle = computed<CSSProperties>(() => ({
  color: ACCENT,
  fontSize: '14px',
  fontWeight: 700,
}))

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
.r1999-card {
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);
}

.r1999-card :deep(.ant-card-head-title) {
  font-size: 18px;
  font-weight: 600;
}

.card-extra {
  display: flex;
  align-items: center;
  gap: 8px;
}

.source-link {
  font-size: 13px;
}

.status-alert {
  margin-bottom: 16px;
}

.activity-rows {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.activity-row {
  padding: 12px 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
}

.activity-row-main {
  min-width: 0;
}

.activity-row-name {
  overflow: hidden;
  color: var(--ant-color-text);
  font-size: 15px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.activity-row-desc {
  margin-top: 2px;
  overflow: hidden;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.activity-row-meta {
  flex-shrink: 0;
  text-align: right;
}

.activity-row-meta :deep(.ant-statistic-content) {
  font-size: 14px;
}

.activity-row-time {
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
}
</style>
