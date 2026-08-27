<template>
  <a-card title="重返未来：1999活动信息" class="r1999-card" :style="cardStyle" :loading="loading">
    <template #extra>
      <div class="card-extra">
        <a-typography-link
          href="https://api.1999.fan"
          target="_blank"
          rel="noreferrer"
          class="source-link"
          @click="handleExternalLink"
        >
          由 M9A 强力支持
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

    <!-- 版本 Banner（超高竖图只显示上部条带） -->
    <div v-if="overview.Available && !loading && versionCover" class="version-banner">
      <img
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

        <div v-if="activeActivities.length" class="activity-tags">
          <a-tag
            v-for="activity in activeActivities"
            :key="`${activity.name}-${activity.endTime}`"
            class="activity-tag"
          >
            {{ activity.name }}
          </a-tag>
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

    <!-- 无版本封面：简洁信息条 -->
    <div v-else-if="overview.Available && !loading" class="version-info">
      <div class="version-info-left">
        <div class="version-info-name">{{ overview.versionName }}</div>
        <div class="version-info-time">
          <ClockCircleOutlined class="version-info-time-icon" />
          <span class="version-info-time-label">版本时间：</span>
          <span class="version-info-time-value"
            >{{ formatTime(overview.startTime) }} ~ {{ formatTime(overview.endTime) }}</span
          >
        </div>
      </div>

      <div class="version-info-right">
        <a-statistic-countdown
          title="版本剩余时间"
          :value="getCountdownValue(overview.endTime)"
          :format="getPlainTimeStatus(overview.endTime) === 'ended' ? '活动已结束' : 'D 天 H 时'"
          :value-style="plainRemainingCountdownStyle"
        />
      </div>
    </div>
  </a-card>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { CSSProperties } from 'vue'
import { ClockCircleOutlined } from '@ant-design/icons-vue'
import type { Reverse1999ActivityOverview } from '@/types/home'
import { handleExternalLink } from '@/utils/openExternal'

defineOptions({ name: 'HomeReverse1999Overview' })

const props = withDefaults(
  defineProps<{
    loading: boolean
    overview: Reverse1999ActivityOverview
  }>(),
  {}
)

const ACCENT = '#e0484f'
const MAX_VISIBLE_ACTIVITIES = 4
const failedVersionCover = ref(false)

const cardStyle = computed<CSSProperties>(
  () =>
    ({
      '--r1999-accent': ACCENT,
    }) as CSSProperties
)

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
  return (
    props.overview.cover || props.overview.activities.find(activity => activity.cover)?.cover || ''
  )
})

const remainingCountdownStyle = computed<CSSProperties>(() => ({
  color: ACCENT,
  fontSize: '34px',
  fontWeight: 700,
  lineHeight: 1.1,
  fontVariantNumeric: 'tabular-nums',
}))

const getPlainTimeStatus = (value: string): 'normal' | 'warning' | 'ended' => {
  const remaining = getCountdownValue(value) - Date.now()
  if (remaining <= 0) return 'ended'
  if (remaining <= 2 * 24 * 60 * 60 * 1000) return 'warning'
  return 'normal'
}

const plainRemainingCountdownStyle = computed<CSSProperties>(() => {
  const status = getPlainTimeStatus(props.overview.endTime)
  if (status === 'ended') {
    return { color: 'var(--ant-color-error)', fontWeight: 600, fontSize: '18px' }
  }
  if (status === 'warning') {
    return { color: 'var(--ant-color-warning)', fontWeight: 600, fontSize: '18px' }
  }
  return { color: 'var(--ant-color-text)', fontWeight: 600, fontSize: '18px' }
})

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

/* ---------- 版本 Banner ---------- */
.version-banner {
  position: relative;
  display: flex;
  align-items: stretch;
  justify-content: space-between;
  min-height: 300px;
  overflow: hidden;
  border: 1px solid transparent;
  border-radius: 10px;
  background:
    radial-gradient(
      ellipse at 78% 20%,
      color-mix(in srgb, var(--r1999-accent) 14%, transparent),
      transparent 55%
    ),
    radial-gradient(ellipse at 90% 85%, rgba(64, 128, 255, 0.18), transparent 60%),
    linear-gradient(135deg, #0b1220 0%, #101a2e 55%, #0e1a2b 100%);
}

.version-cover {
  width: 100%;
  height: 100%;
  position: absolute;
  inset: 0;
  object-fit: cover;
  /* 官网图是 1920x3902 的超高竖图，只显示上部约 14% 处的条带 */
  object-position: right 14%;
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
  border: 1px solid color-mix(in srgb, var(--r1999-accent) 45%, transparent);
  border-radius: 999px;
  background: rgba(11, 18, 32, 0.55);
}

.badge-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--r1999-accent);
  box-shadow: 0 0 8px color-mix(in srgb, var(--r1999-accent) 80%, transparent);
}

.badge-text {
  color: var(--r1999-accent);
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
  color: var(--r1999-accent);
  font-size: 15px;
}

/* ---------- 活动类型标签 ---------- */
.activity-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.activity-tag {
  margin-inline-end: 0;
  border: 1px solid color-mix(in srgb, var(--r1999-accent) 45%, transparent);
  border-radius: 999px;
  background: rgba(11, 18, 32, 0.55);
  color: white;
  font-size: 13px;
  font-weight: 500;
  line-height: 22px;
}

/* ---------- 版本剩余时间 ---------- */
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
  border: 1px solid color-mix(in srgb, var(--r1999-accent) 35%, transparent);
  border-radius: 14px;
  background: rgba(11, 18, 32, 0.6);
  backdrop-filter: blur(10px);
  box-shadow:
    0 8px 32px rgba(0, 0, 0, 0.35),
    inset 0 0 24px color-mix(in srgb, var(--r1999-accent) 5%, transparent);
  white-space: nowrap;
}

.remaining-label {
  color: rgba(255, 255, 255, 0.75);
  font-size: 13px;
  line-height: 1;
  letter-spacing: 0.08em;
}

.version-remaining :deep(.ant-statistic-content) {
  color: var(--r1999-accent);
  font-size: 34px;
  font-weight: 700;
  line-height: 1.1;
  font-variant-numeric: tabular-nums;
  text-shadow: 0 0 20px color-mix(in srgb, var(--r1999-accent) 35%, transparent);
}

.remaining-sub {
  color: rgba(255, 255, 255, 0.5);
  font-size: 12px;
  line-height: 1;
}

/* ---------- 无封面：简洁信息条 ---------- */
.version-info {
  padding: 16px;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  border: 1px solid var(--ant-color-border);
  border-radius: 8px;
}

.version-info-left {
  min-width: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.version-info-name {
  color: var(--ant-color-text);
  font-size: 18px;
  font-weight: 600;
  line-height: 1.2;
  overflow-wrap: anywhere;
}

.version-info-time {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
}

.version-info-time-icon,
.version-info-time-label {
  color: var(--ant-color-text-secondary);
}

.version-info-time-value {
  color: var(--ant-color-text);
  font-weight: 500;
}

.version-info-right {
  flex-shrink: 0;
  text-align: right;
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

  .version-info {
    flex-direction: column;
    align-items: flex-start;
    gap: 16px;
  }

  .version-info-right {
    text-align: left;
  }
}
</style>
