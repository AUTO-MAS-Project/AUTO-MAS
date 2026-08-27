<template>
  <a-card
    :title="title"
    class="sra-card"
    :class="{ 'is-plain': activityPlain }"
    :style="cardStyle"
    :loading="loading"
  >
    <template #extra>
      <div class="card-extra">
        <a-typography-link
          :href="sourceUrl"
          target="_blank"
          rel="noreferrer"
          class="source-link"
          @click="handleExternalLink"
        >
          由 {{ sourceName }} 强力支持
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

    <!-- 有版本封面：HSR 风格深色大横幅 -->
    <div v-if="overview.Available && !loading && versionCover" class="version-banner">
      <img
        :src="versionCover"
        :alt="overview.versionName"
        class="version-cover"
        :style="{ objectPosition: coverPosition }"
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

    <!-- 无版本封面：MAA 风格浅色简洁信息条 -->
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

    <div
      v-if="activeActivities.length"
      class="activity-list"
      :class="{ 'is-plain': activityPlain }"
    >
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
        <div class="activity-overlay" />
        <div class="activity-content">
          <div class="activity-name">{{ activity.name }}</div>
          <div v-if="activity.description" class="activity-desc">{{ activity.description }}</div>
          <div class="activity-meta">
            <a-statistic-countdown
              :value="getCountdownValue(activity.endTime)"
              format="D 天 H 时"
              :value-style="activityCountdownStyle"
              @finish="emit('refresh')"
            />
            <div class="activity-end-time">结束于 {{ formatTime(activity.endTime) }}</div>
          </div>
        </div>
      </div>
    </div>

    <a-empty v-else-if="!loading && overview.Available" :description="emptyText" />
  </a-card>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { CSSProperties } from 'vue'
import { ClockCircleOutlined } from '@ant-design/icons-vue'
import type { SraActivityOverview } from '@/types/home'
import { handleExternalLink } from '@/utils/openExternal'

defineOptions({ name: 'HomeSraActivityOverview' })

const props = withDefaults(
  defineProps<{
    title: string
    accent: string
    loading: boolean
    overview: SraActivityOverview
    emptyText: string
    /** 活动卡片始终使用无封面浅色样式（Banner 有图时也生效） */
    plainActivities?: boolean
    sourceName?: string
    sourceUrl?: string
    /** 版本封面裁切位置（object-position），用于超高竖图只显示特定条带 */
    coverPosition?: string
  }>(),
  {
    plainActivities: false,
    sourceName: 'SRA',
    sourceUrl: 'https://starrailassistant.top',
    coverPosition: 'right center',
  }
)

const emit = defineEmits<{ refresh: [] }>()

const failedImageNames = ref(new Set<string>())
const failedVersionCover = ref(false)

const cardStyle = computed<CSSProperties>(
  () =>
    ({
      '--sra-accent': props.accent,
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
})

const versionCover = computed(() => {
  if (failedVersionCover.value) return ''
  return (
    props.overview.cover || props.overview.activities.find(activity => activity.cover)?.cover || ''
  )
})

const activityPlain = computed(() => props.plainActivities || !versionCover.value)

const getActivityImage = (activity: SraActivityOverview['activities'][number]) => {
  if (failedImageNames.value.has(activity.name)) return ''
  return activity.cover || versionCover.value || ''
}

const handleImageError = (activityName: string) => {
  failedImageNames.value = new Set(failedImageNames.value).add(activityName)
}

const remainingCountdownStyle = computed<CSSProperties>(() => ({
  color: props.accent,
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

const activityCountdownStyle = computed<CSSProperties>(() => ({
  color: props.accent,
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
.sra-card {
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);
}

.sra-card :deep(.ant-card-head-title) {
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

/* ---------- 有封面：HSR 风格顶部版本横幅 ---------- */
.version-banner {
  position: relative;
  display: flex;
  align-items: stretch;
  justify-content: space-between;
  min-height: 300px;
  margin-bottom: 16px;
  overflow: hidden;
  border: 1px solid transparent;
  border-radius: 10px;
  background:
    radial-gradient(
      ellipse at 78% 20%,
      color-mix(in srgb, var(--sra-accent) 14%, transparent),
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
  border: 1px solid color-mix(in srgb, var(--sra-accent) 45%, transparent);
  border-radius: 999px;
  background: rgba(11, 18, 32, 0.55);
}

.badge-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--sra-accent);
  box-shadow: 0 0 8px color-mix(in srgb, var(--sra-accent) 80%, transparent);
}

.badge-text {
  color: var(--sra-accent);
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
  color: var(--sra-accent);
  font-size: 15px;
}

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
  border: 1px solid color-mix(in srgb, var(--sra-accent) 35%, transparent);
  border-radius: 14px;
  background: rgba(11, 18, 32, 0.6);
  backdrop-filter: blur(10px);
  box-shadow:
    0 8px 32px rgba(0, 0, 0, 0.35),
    inset 0 0 24px color-mix(in srgb, var(--sra-accent) 5%, transparent);
  white-space: nowrap;
}

.remaining-label {
  color: rgba(255, 255, 255, 0.75);
  font-size: 13px;
  line-height: 1;
  letter-spacing: 0.08em;
}

.version-remaining :deep(.ant-statistic-content) {
  color: var(--sra-accent);
  font-size: 34px;
  font-weight: 700;
  line-height: 1.1;
  font-variant-numeric: tabular-nums;
  text-shadow: 0 0 20px color-mix(in srgb, var(--sra-accent) 35%, transparent);
}

.remaining-sub {
  color: rgba(255, 255, 255, 0.5);
  font-size: 12px;
  line-height: 1;
}

/* ---------- 无封面：MAA 风格浅色简洁版本信息条 ---------- */
.version-info {
  margin-bottom: 24px;
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

/* ---------- 活动列表（有封面：深色封面卡片） ---------- */
.activity-list {
  display: flex;
  gap: 16px;
  overflow-x: auto;
  scroll-snap-type: x mandatory;
  -webkit-overflow-scrolling: touch;
  scrollbar-width: thin;
}

.activity-item {
  min-width: 0;
  width: 266px;
  flex-shrink: 0;
  height: 150px;
  position: relative;
  display: flex;
  align-items: flex-end;
  overflow: hidden;
  border-radius: 10px;
  scroll-snap-align: start;
  background:
    radial-gradient(
      ellipse at 20% 0%,
      color-mix(in srgb, var(--sra-accent) 16%, transparent),
      transparent 55%
    ),
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

.activity-desc {
  max-height: 0;
  overflow: auto;
  color: rgba(255, 255, 255, 0.9);
  font-size: 12px;
  line-height: 1.5;
  opacity: 0;
  text-shadow:
    0 0 3px #000,
    0 0 6px #000;
  transition:
    max-height 0.3s ease,
    opacity 0.3s ease,
    margin 0.3s ease;
  margin-bottom: 0;
  scrollbar-width: none;
}

.activity-item:hover .activity-desc {
  max-height: 60px;
  opacity: 1;
  margin-bottom: 8px;
}

/* ---------- 活动列表（无封面：MAA 风格浅色边框卡片） ---------- */
.activity-list.is-plain {
  display: flex;
  gap: 12px;
  overflow-x: auto;
  scroll-snap-type: x mandatory;
  -webkit-overflow-scrolling: touch;
  scrollbar-width: thin;
}

.activity-list.is-plain .activity-item {
  min-width: 0;
  width: 240px;
  flex-shrink: 0;
  height: auto;
  min-height: 82px;
  align-items: center;
  padding: 16px;
  border: 1px solid var(--ant-color-border);
  border-radius: 8px;
  background: transparent;
  scroll-snap-align: start;
  transition:
    border-color 0.2s ease,
    box-shadow 0.2s ease;
}

.activity-list.is-plain .activity-item:hover {
  border-color: var(--ant-color-primary);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.activity-list.is-plain .activity-item:hover .activity-image {
  transform: none;
}

.activity-list.is-plain .activity-overlay {
  display: none;
}

.activity-list.is-plain .activity-content {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 0;
}

.activity-list.is-plain .activity-name {
  margin-bottom: 0;
  color: var(--ant-color-text);
  font-size: 16px;
  font-weight: 600;
  text-shadow: none;
}

.activity-list.is-plain .activity-meta {
  flex-shrink: 0;
}

.activity-list.is-plain .activity-end-time {
  color: var(--ant-color-text-secondary);
}

.activity-list.is-plain .activity-desc {
  max-height: 0;
  overflow: hidden;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  line-height: 1.5;
  opacity: 0;
  transition:
    max-height 0.3s ease,
    opacity 0.3s ease;
}

.activity-list.is-plain .activity-item:hover .activity-desc {
  max-height: 60px;
  opacity: 1;
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

@media (max-width: 560px) {
  .activity-item {
    width: 180px;
  }

  .activity-list.is-plain .activity-item {
    width: 200px;
  }
}
</style>
