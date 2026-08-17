<template>
  <a-card title="崩坏：星穹铁道活动信息" class="starrail-card" :loading="loading">
    <template #extra>
      <div class="card-extra">
        <a-typography-link
          :href="STAR_RAIL_ASSISTANT_URL"
          target="_blank"
          rel="noreferrer"
          class="source-link"
          @click="handleExternalLink"
        >
          由 SRA 强力支持
        </a-typography-link>
        <a-tag v-if="overview.Stale" color="orange">缓存数据</a-tag>
      </div>
    </template>

    <a-alert
      v-if="overview.Message"
      :message="overview.Message"
      :type="overview.Available ? 'warning' : 'error'"
      show-icon
      class="status-alert"
    />

    <div
      v-if="overview.Available && !loading"
      class="version-banner"
      :class="{ 'has-cover': versionCover }"
    >
      <img
        v-if="versionCover"
        :src="versionCover"
        :alt="overview.versionName"
        class="version-cover"
        @error="failedVersionCover = true"
      />
      <div class="version-overlay" />

      <div class="version-content">
        <div class="version-badge">
          <span class="badge-dot" />
          <span class="badge-text">{{ overview.version }} 版本</span>
        </div>

        <div class="version-name">{{ overview.versionName }}</div>

        <div class="version-time">
          <ClockCircleOutlined class="version-time-icon" />
          <span>{{ formatTime(overview.endTime) }} 结束</span>
        </div>
      </div>

      <div class="version-remaining">
        <div class="remaining-label">版本剩余时间</div>
        <a-statistic-countdown
          :value="getCountdownValue(overview.endTime)"
          format="D 天 H 时"
          :value-style="remainingCountdownStyle"
        />
        <div class="remaining-sub">即将进入下个版本</div>
      </div>
    </div>

    <div v-if="activeActivities.length" class="activity-list">
      <div
        v-for="activity in activeActivities"
        :key="activity.name"
        class="activity-item"
        :class="{ 'is-fallback': !getActivityImage(activity) }"
      >
        <img
          v-if="getActivityImage(activity)"
          :src="getActivityImage(activity)"
          :alt="activity.name"
          class="activity-image"
          @error="handleImageError(activity.name)"
        />
        <div v-if="getActivityImage(activity)" class="activity-overlay" />
        <div class="activity-content">
          <div class="activity-name">{{ activity.name }}</div>
          <div class="activity-meta">
            <a-statistic-countdown
              :value="getCountdownValue(activity.endTime)"
              format="D 天 H 时"
              :value-style="activityCountdownStyle"
              @finish="emit('refresh')"
            />
            <div class="activity-end-time">{{ formatTime(activity.endTime) }}</div>
          </div>
        </div>
      </div>
    </div>

    <a-empty v-else-if="!loading && overview.Available" description="暂无进行中的星穹铁道活动" />
  </a-card>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { CSSProperties } from 'vue'
import { ClockCircleOutlined } from '@ant-design/icons-vue'
import type { StarRailActivityOverview } from '@/types/home'
import { handleExternalLink } from '@/utils/openExternal'

defineOptions({ name: 'HomeStarRailOverview' })

const props = defineProps<{
  loading: boolean
  overview: StarRailActivityOverview
}>()

const emit = defineEmits<{ refresh: [] }>()

const STAR_RAIL_ASSISTANT_URL = 'https://starrailassistant.top'
const MAX_VISIBLE_ACTIVITIES = 4
const failedImageNames = ref(new Set<string>())
const failedVersionCover = ref(false)

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

const versionCover = computed(() => {
  if (failedVersionCover.value) return ''
  return props.overview.cover || props.overview.activities.find(activity => activity.cover)?.cover || ''
})

const getActivityImage = (activity: StarRailActivityOverview['activities'][number]) => {
  if (failedImageNames.value.has(activity.name)) return ''
  return activity.cover || ''
}

const handleImageError = (activityName: string) => {
  failedImageNames.value = new Set(failedImageNames.value).add(activityName)
}

const remainingCountdownStyle: CSSProperties = {
  color: '#f5d76e',
  fontSize: '34px',
  fontWeight: 700,
  lineHeight: 1.1,
  fontVariantNumeric: 'tabular-nums',
}

const activityCountdownStyle: CSSProperties = {
  color: '#f5d76e',
  fontSize: '14px',
  fontWeight: 700,
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

/* ---------- 顶部版本横幅（Endfield 风格双栏） ---------- */
.version-banner {
  position: relative;
  display: flex;
  align-items: stretch;
  justify-content: space-between;
  min-height: 300px;
  margin-bottom: 16px;
  overflow: hidden;
  border: 1px solid var(--ant-color-border);
  border-radius: 10px;
  background:
    radial-gradient(ellipse at 78% 20%, rgba(245, 215, 110, 0.14), transparent 55%),
    radial-gradient(ellipse at 90% 85%, rgba(64, 128, 255, 0.18), transparent 60%),
    linear-gradient(135deg, #0b1220 0%, #101a2e 55%, #0e1a2b 100%);
}

.version-banner.has-cover {
  border-color: transparent;
}

.version-cover {
  width: 100%;
  height: 100%;
  position: absolute;
  inset: 0;
  object-fit: cover;
  object-position: right center;
}

.version-overlay {
  position: absolute;
  inset: 0;
  background: linear-gradient(
    90deg,
    rgba(11, 18, 32, 0.9) 0%,
    rgba(11, 18, 32, 0.72) 42%,
    rgba(11, 18, 32, 0.15) 100%
  );
}

.version-content {
  position: relative;
  z-index: 1;
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 28px 32px;
  color: white;
}

.version-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  align-self: flex-start;
  padding: 4px 12px;
  margin-bottom: 12px;
  border: 1px solid rgba(245, 215, 110, 0.45);
  border-radius: 999px;
  background: rgba(11, 18, 32, 0.55);
}

.badge-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #f5d76e;
  box-shadow: 0 0 8px rgba(245, 215, 110, 0.8);
}

.badge-text {
  color: #f5d76e;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.04em;
}

.version-name {
  margin-bottom: 14px;
  color: white;
  font-size: 30px;
  font-weight: 700;
  line-height: 1.2;
  letter-spacing: 0.01em;
  overflow-wrap: anywhere;
}

.version-time {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  align-self: flex-start;
  padding: 6px 16px;
  border: 1px solid rgba(255, 255, 255, 0.16);
  border-radius: 999px;
  background: rgba(11, 18, 32, 0.5);
  color: white;
  font-size: 15px;
  font-weight: 500;
}

.version-time-icon {
  color: #f5d76e;
  font-size: 15px;
}

/* ---------- 右侧大倒计时浮层 ---------- */
.version-remaining {
  position: relative;
  z-index: 1;
  align-self: center;
  margin-right: 28px;
  padding: 18px 28px;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 6px;
  border: 1px solid rgba(245, 215, 110, 0.35);
  border-radius: 14px;
  background: rgba(11, 18, 32, 0.6);
  backdrop-filter: blur(10px);
  box-shadow:
    0 8px 32px rgba(0, 0, 0, 0.35),
    inset 0 0 24px rgba(245, 215, 110, 0.05);
  white-space: nowrap;
}

.remaining-label {
  color: rgba(255, 255, 255, 0.75);
  font-size: 13px;
  line-height: 1;
  letter-spacing: 0.08em;
}

.version-remaining :deep(.ant-statistic-content) {
  color: #f5d76e;
  font-size: 34px;
  font-weight: 700;
  line-height: 1.1;
  font-variant-numeric: tabular-nums;
  text-shadow: 0 0 20px rgba(245, 215, 110, 0.35);
}

.remaining-sub {
  color: rgba(255, 255, 255, 0.5);
  font-size: 12px;
  line-height: 1;
}

/* ---------- 活动列表（封面铺满 4 列网格） ---------- */
.activity-list {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
}

.activity-item {
  min-width: 0;
  height: 150px;
  position: relative;
  display: flex;
  align-items: flex-end;
  overflow: hidden;
  border-radius: 10px;
  background:
    radial-gradient(ellipse at 20% 0%, rgba(245, 215, 110, 0.16), transparent 55%),
    linear-gradient(150deg, #14203a 0%, #0b1220 60%, #101a2e 100%);
  transition:
    transform 0.25s ease,
    box-shadow 0.25s ease;
}

.activity-item:hover {
  transform: translateY(-3px);
  box-shadow: 0 10px 28px rgba(0, 0, 0, 0.18);
}

.activity-image {
  width: 100%;
  height: 100%;
  position: absolute;
  inset: 0;
  object-fit: cover;
  transition: transform 0.35s ease;
}

.activity-item:hover .activity-image {
  transform: scale(1.05);
}

.activity-overlay {
  position: absolute;
  inset: 0;
  background: linear-gradient(
    180deg,
    rgba(11, 18, 32, 0.05) 0%,
    rgba(11, 18, 32, 0.3) 40%,
    rgba(11, 18, 32, 0.88) 100%
  );
}

.activity-content {
  width: 100%;
  min-width: 0;
  position: relative;
  z-index: 1;
  padding: 14px 16px;
}

.activity-name {
  min-width: 0;
  margin-bottom: 8px;
  overflow: hidden;
  color: white;
  font-size: 15px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
  text-shadow: 0 1px 3px rgba(0, 0, 0, 0.5);
}

.activity-meta {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}

.activity-meta :deep(.ant-statistic-content) {
  line-height: 1.4;
}

.activity-end-time {
  min-width: 0;
  overflow: hidden;
  color: rgba(255, 255, 255, 0.8);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 无图卡片：文字排布与有图卡片一致（底部靠左） */
.activity-item.is-fallback {
  border: 1px solid rgba(255, 255, 255, 0.1);
  background:
    radial-gradient(ellipse at 20% 0%, rgba(245, 215, 110, 0.16), transparent 55%),
    linear-gradient(150deg, #14203a 0%, #0b1220 60%, #101a2e 100%);
}

.activity-item.is-fallback:hover {
  border-color: rgba(245, 215, 110, 0.5);
  box-shadow: 0 10px 28px rgba(0, 0, 0, 0.18);
}

.activity-item.is-fallback .activity-content {
  width: 100%;
  padding: 14px 16px;
}

.activity-item.is-fallback .activity-name {
  color: white;
  white-space: normal;
  overflow-wrap: anywhere;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  overflow: hidden;
}

.activity-item.is-fallback .activity-meta {
  justify-content: space-between;
  gap: 8px;
}

.activity-item.is-fallback .activity-end-time {
  color: rgba(255, 255, 255, 0.8);
}

@media (max-width: 1240px) {
  .activity-list {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 800px) {
  .version-banner {
    flex-direction: column;
  }

  .version-name {
    font-size: 26px;
  }

  .version-remaining {
    align-self: stretch;
    align-items: flex-start;
    margin: 0 28px 24px;
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
