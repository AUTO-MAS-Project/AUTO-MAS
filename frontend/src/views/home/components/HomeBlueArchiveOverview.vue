<template>
  <a-card :title="t('home.module.bluearchive')" class="bluearchive-card" :style="cardStyle">
    <template #extra>
      <div class="card-extra">
        <a-typography-link
          href="https://kivo.wiki/timeline"
          target="_blank"
          rel="noreferrer"
          class="source-link"
          @click="handleExternalLink"
        >
          {{ t('home.bluearchive.source') }}
        </a-typography-link>
        <a-tag v-if="overview.Stale" color="orange">{{ t('home.bluearchive.stale') }}</a-tag>
      </div>
    </template>

    <!-- 三个服的数据在数据源里已并行拉好，这里只切显示，不重新请求 -->
    <div class="server-switch" role="group" :aria-label="t('home.bluearchive.serverLabel')">
      <span class="server-switch-label">{{ t('home.bluearchive.serverLabel') }}</span>
      <div class="server-tabs">
        <button
          v-for="server in servers"
          :key="server.key"
          type="button"
          class="server-tab"
          :class="{ 'is-active': server.key === selected }"
          :aria-pressed="server.key === selected"
          @click="emit('select', server.key)"
        >
          {{ server.label }}
        </button>
      </div>
    </div>

    <a-skeleton v-if="currentLoading" active :paragraph="{ rows: 4 }" />

    <!-- 当前服的失败提示：只影响这一个服，切到其它服照常显示 -->
    <a-alert
      v-if="overview.Message"
      :message="overview.Message"
      :type="overview.Available ? 'warning' : 'error'"
      show-icon
      class="status-alert"
    />

    <div
      v-if="overview.Available && !currentLoading && !overview.activities.length"
      class="empty-state"
    >
      <a-empty :description="t('home.bluearchive.noActivity')" />
    </div>

    <!-- 活动 Banner（超高竖图只显示上部条带） -->
    <div v-else-if="overview.Available && !currentLoading && versionCover" class="version-banner">
      <img
        :key="versionCover"
        :src="versionCover"
        :alt="overview.versionName"
        class="version-cover"
        decoding="async"
        @error="failedVersionCover = true"
      />
      <div class="version-overlay" />

      <div class="version-content">
        <div class="version-badge">
          <span class="badge-dot" />
          <span class="badge-text">{{
            t('home.bluearchive.versionBadge', { version: overview.version })
          }}</span>
        </div>

        <div class="version-name">{{ overview.versionName }}</div>

        <div class="version-time">
          <ClockCircleOutlined class="version-time-icon" />
          <span>{{ t('home.bluearchive.endsAt', { time: formatTime(overview.endTime) }) }}</span>
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
        <div class="remaining-label">
          {{ isEnded ? t('home.countdown.ended') : t('home.bluearchive.versionRemaining') }}
        </div>
        <a-statistic-countdown
          v-if="!isEnded"
          :value="getCountdownValue(overview.endTime)"
          :format="t('home.countdown.dh')"
          :value-style="remainingCountdownStyle"
        />
        <div class="remaining-sub">{{ t('home.bluearchive.nextVersionSoon') }}</div>
      </div>
    </div>

    <!-- 无活动封面：简洁信息条 -->
    <div v-else-if="overview.Available && !currentLoading" class="version-info">
      <div class="version-info-left">
        <div class="version-info-name">{{ overview.versionName }}</div>
        <div class="version-info-time">
          <ClockCircleOutlined class="version-info-time-icon" />
          <span class="version-info-time-label">{{ t('home.bluearchive.versionTime') }}</span>
          <span class="version-info-time-value"
            >{{ formatTime(overview.startTime) }} ~ {{ formatTime(overview.endTime) }}</span
          >
        </div>
      </div>

      <div class="version-info-right">
        <a-statistic-countdown
          :title="t('home.bluearchive.versionRemaining')"
          :value="getCountdownValue(overview.endTime)"
          :format="
            getPlainTimeStatus(overview.endTime) === 'ended'
              ? t('home.countdown.ended')
              : t('home.countdown.dh')
          "
          :value-style="plainRemainingCountdownStyle"
        />
      </div>
    </div>
  </a-card>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, ref, watch } from 'vue'
import type { CSSProperties } from 'vue'
import { ClockCircleOutlined } from '@ant-design/icons-vue'
import { blueArchivePresentation } from '@/views/home/blueArchivePresentation'
import { createEmptySraActivityOverview } from '@/types/home'
import type {
  BlueArchiveActivityOverview,
  BlueArchiveServerKey,
  BlueArchiveServerOverview,
} from '@/types/home'
import { handleExternalLink } from '@/utils/openExternal'

defineOptions({ name: 'HomeBlueArchiveOverview' })

const { t } = useI18n()

const props = defineProps<{
  servers: BlueArchiveServerOverview[]
  selected: BlueArchiveServerKey
  loadingByServer: Record<BlueArchiveServerKey, boolean>
}>()

const emit = defineEmits<{
  select: [server: BlueArchiveServerKey]
}>()

const ACCENT = '#3ba9ee'
const MAX_VISIBLE_ACTIVITIES = 4
const failedVersionCover = ref(false)

const cardStyle = computed<CSSProperties>(
  () =>
    ({
      '--bluearchive-accent': ACCENT,
    }) as CSSProperties
)

const currentServer = computed(() => props.servers.find(server => server.key === props.selected))

const overview = computed<BlueArchiveActivityOverview>(() =>
  blueArchivePresentation(currentServer.value?.overview ?? createEmptySraActivityOverview())
)

// 每个服各有自己的加载态，卡片只关心当前选中的这个服
const currentLoading = computed(() => props.loadingByServer[props.selected] === true)

// 失败状态只属于当前封面；同服活动刷新换图或切服后都应重新尝试。
watch([() => props.selected, () => overview.value.cover], () => {
  failedVersionCover.value = false
})

const activeActivities = computed(() => {
  const now = Date.now()
  return overview.value.activities
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
  return overview.value.cover || ''
})

const remainingCountdownStyle = computed<CSSProperties>(() => ({
  color: ACCENT,
  fontSize: '28px',
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
  const status = getPlainTimeStatus(overview.value.endTime)
  if (status === 'ended') {
    return { color: 'var(--ant-color-error)', fontWeight: 600, fontSize: '18px' }
  }
  if (status === 'warning') {
    return { color: 'var(--ant-color-warning)', fontWeight: 600, fontSize: '18px' }
  }
  return { color: 'var(--ant-color-text)', fontWeight: 600, fontSize: '18px' }
})

// 活动间隙会退回展示最近结束的那一场，这时不能再报「剩余时间」
const isEnded = computed(() => getPlainTimeStatus(overview.value.endTime) === 'ended')

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
.bluearchive-card {
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);
}

.bluearchive-card :deep(.ant-card-head-title) {
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

.server-switch {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
}

.server-switch-label {
  color: var(--ant-color-text-secondary);
  font-size: 13px;
}

/* 服务器胶囊切换条 */
.server-tabs {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 4px;
  border-radius: 999px;
  max-width: 100%;
  overflow-x: auto;
  background: var(--ant-color-fill-tertiary);
}

.server-tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 16px;
  flex-shrink: 0;
  border: none;
  border-radius: 999px;
  background: transparent;
  color: var(--ant-color-text);
  font-size: 14px;
  line-height: 22px;
  cursor: pointer;
  user-select: none;
  transition: box-shadow 0.12s;
}

.server-tab:hover {
  color: var(--bluearchive-accent);
}

.server-tab.is-active {
  background: var(--ant-color-bg-container);
  color: var(--bluearchive-accent);
  font-weight: 600;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.15);
}

.server-tab:focus-visible {
  outline: 2px solid var(--ant-color-primary);
  outline-offset: -2px;
}

.status-alert {
  margin-bottom: 16px;
}

.empty-state {
  padding: 24px 0;
}

/* ---------- 活动 Banner ---------- */
.version-banner {
  position: relative;
  display: flex;
  align-items: stretch;
  justify-content: space-between;
  min-height: 380px;
  overflow: hidden;
  border: 1px solid transparent;
  border-radius: 10px;
  background:
    radial-gradient(
      ellipse at 78% 20%,
      color-mix(in srgb, var(--bluearchive-accent) 14%, transparent),
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
  /* Kivo 时间轴配图多为竖图，只显示上部约 14% 处的条带 */
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
  border: 1px solid color-mix(in srgb, var(--bluearchive-accent) 45%, transparent);
  border-radius: 999px;
  background: rgba(11, 18, 32, 0.55);
}

.badge-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--bluearchive-accent);
  box-shadow: 0 0 8px color-mix(in srgb, var(--bluearchive-accent) 80%, transparent);
}

.badge-text {
  color: var(--bluearchive-accent);
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
  color: var(--bluearchive-accent);
  font-size: 15px;
}

/* ---------- 活动标签 ---------- */
.activity-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.activity-tag {
  margin-inline-end: 0;
  border: 1px solid color-mix(in srgb, var(--bluearchive-accent) 45%, transparent);
  border-radius: 999px;
  background: rgba(11, 18, 32, 0.55);
  color: white;
  font-size: 13px;
  font-weight: 500;
  line-height: 22px;
}

/* ---------- 剩余时间 ---------- */
/* 贴右下角、压成一行：封面里的人物多在画面中部，浮层居中会挡脸 */
.version-remaining {
  position: relative;
  z-index: 1;
  align-self: flex-end;
  margin: 0 28px 20px 0;
  padding: 12px 22px;
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
  border: 1px solid color-mix(in srgb, var(--bluearchive-accent) 35%, transparent);
  border-radius: 12px;
  background: rgba(11, 18, 32, 0.6);
  backdrop-filter: blur(10px);
  box-shadow:
    0 8px 32px rgba(0, 0, 0, 0.35),
    inset 0 0 24px color-mix(in srgb, var(--bluearchive-accent) 5%, transparent);
  white-space: nowrap;
}

.remaining-label {
  color: rgba(255, 255, 255, 0.75);
  font-size: 13px;
  line-height: 1;
  letter-spacing: 0.08em;
}

.version-remaining :deep(.ant-statistic-content) {
  color: var(--bluearchive-accent);
  font-size: 28px;
  font-weight: 700;
  line-height: 1.1;
  font-variant-numeric: tabular-nums;
  text-shadow: 0 0 20px color-mix(in srgb, var(--bluearchive-accent) 35%, transparent);
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
    min-height: 320px;
  }

  .version-name {
    font-size: 26px;
  }

  .version-remaining {
    align-self: stretch;
    justify-content: flex-end;
    margin: 0 24px 20px;
  }

  .version-info {
    flex-direction: column;
    gap: 16px;
  }

  .version-info-right {
    text-align: left;
  }
}
</style>
