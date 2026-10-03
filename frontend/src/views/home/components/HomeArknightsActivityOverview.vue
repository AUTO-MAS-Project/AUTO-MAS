<template>
  <a-card :title="t('home.module.arknights')" class="arknights-card" :style="cardStyle">
    <template #extra>
      <div class="card-extra">
        <a-typography-link
          href="https://prts.wiki/w/%E6%B4%BB%E5%8A%A8%E4%B8%80%E8%A7%88"
          target="_blank"
          rel="noreferrer"
          class="source-link"
          @click="handleExternalLink"
        >
          {{ t('home.arknights.source') }}
        </a-typography-link>
        <a-tag v-if="overview.Stale" color="orange">{{ t('home.sra.stale') }}</a-tag>
      </div>
    </template>

    <a-skeleton v-if="loading" active :paragraph="{ rows: 4 }" />

    <!-- 首页概览接口失败时来说一句：下面的材料关卡会因此空着，别让它悄无声息 -->
    <a-alert
      v-if="error"
      :message="error"
      type="error"
      show-icon
      closable
      class="status-alert"
      @close="emit('clearError')"
    />

    <a-alert
      v-if="overview.Message"
      :message="overview.Message"
      :type="overview.Available ? 'warning' : 'error'"
      show-icon
      class="status-alert"
    />

    <div v-if="!loading && !displayActivities.length" class="empty-state">
      <a-empty :description="t('home.arknights.noActivity')" />
    </div>

    <!-- 活动卡片：分类打标签，同时进行多场时按结束时间先后的横排 -->
    <div v-else-if="!loading" class="activity-list">
      <div v-for="activity in displayActivities" :key="activity.name" class="activity-card">
        <div class="activity-item">
          <img
            v-if="getActivityImage(activity)"
            :src="getActivityImage(activity)"
            :alt="activity.name"
            class="activity-image"
            referrerpolicy="no-referrer"
            decoding="async"
            @error="handleImageError(activity.name)"
          />
          <div class="activity-overlay" />
          <div class="activity-content">
            <div class="activity-head">
              <span v-if="activity.kind" class="activity-kind">{{ activity.kind }}</span>
              <span class="activity-name">{{ activity.name }}</span>
            </div>
            <div class="activity-meta">
              <span class="activity-countdown">
                <span class="countdown-label">
                  {{
                    isUpcoming(activity)
                      ? t('home.arknights.startsIn')
                      : t('home.arknights.countdownLeft')
                  }}
                </span>
                <a-statistic-countdown
                  :value="getCountdownValue(countdownTarget(activity))"
                  :format="countdownFormat(activity)"
                  :value-style="activityCountdownStyle"
                  @finish="emit('refresh')"
                />
              </span>
              <div class="activity-end-time">
                {{
                  isUpcoming(activity)
                    ? t('home.bluearchive.startsAt', {
                        time: formatActivityTime(activity.startTime, locale),
                      })
                    : t('home.bluearchive.endsAt', {
                        time: formatActivityTime(activity.endTime, locale),
                      })
                }}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 今日开放的资源收集关卡：关卡代号、掉落材料与开放日都由后端那份关卡表给出 -->
    <div v-if="resourceData.length" class="resource-section">
      <div class="resource-title">{{ t('home.arknights.resourceToday') }}</div>
      <div class="resource-list">
        <div v-for="item in resourceData" :key="item.Value" class="resource-item">
          <div class="resource-stage">{{ item.Display }}</div>
          <div class="resource-drop">
            <img
              v-if="getMaterialImage(item.Drop)"
              :src="getMaterialImage(item.Drop)"
              :alt="item.DropName"
              class="resource-icon"
            />
          </div>
          <div class="resource-text">
            <div class="resource-name">{{ item.DropName }}</div>
            <div class="resource-tip">{{ item.Activity.Tip }}</div>
          </div>
        </div>
      </div>
    </div>
  </a-card>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, ref, watch } from 'vue'
import type { CSSProperties } from 'vue'
import { OpenAPI } from '@/api'
import type { ResourceItem, SraActivityOverview } from '@/types/home'
import { handleExternalLink } from '@/utils/openExternal'
import { formatActivityTime } from '@/views/home/activityTime'

defineOptions({ name: 'HomeArknightsActivityOverview' })

const { t, locale } = useI18n()

const props = defineProps<{
  overview: SraActivityOverview
  loading: boolean
  /** 今日开放的资源收集关卡，来自后端那份关卡表 */
  resourceData: ResourceItem[]
  /** 首页概览接口的失败原因，空串表示没出错 */
  error?: string
}>()

const emit = defineEmits<{ refresh: []; clearError: [] }>()

const ACCENT = '#9fb4cc'
const MAX_VISIBLE_ACTIVITIES = 8

const getMaterialImage = (dropName: string) =>
  dropName ? `${OpenAPI.BASE}/api/res/materials/${dropName}.png` : ''

const cardStyle = computed<CSSProperties>(
  () =>
    ({
      '--arknights-accent': ACCENT,
    }) as CSSProperties
)

const failedImageNames = ref(new Set<string>())

watch(
  () => props.overview.activities,
  () => {
    failedImageNames.value = new Set()
  }
)

/** 一开就是大半年的玩法（生息演算、集成战略）排到当期活动后面，别挤掉真正当期的那几张 */
const LONG_RUNNING_DAYS = 60
const MS_PER_DAY = 86_400_000

const isLongRunning = (activity: SraActivityOverview['activities'][number]) =>
  (getCountdownValue(activity.endTime) - getCountdownValue(activity.startTime)) / MS_PER_DAY >
  LONG_RUNNING_DAYS

/** 列表把还没开始的那几场也放进来，长期的排在后面，其余按开始时间先后 */
const displayActivities = computed(() => {
  const now = Date.now()
  return props.overview.activities
    .filter(item => getCountdownValue(item.endTime) > now)
    .sort((left, right) => {
      const longDiff = Number(isLongRunning(left)) - Number(isLongRunning(right))
      if (longDiff !== 0) return longDiff
      return getCountdownValue(left.startTime) - getCountdownValue(right.startTime)
    })
    .slice(0, MAX_VISIBLE_ACTIVITIES)
})

/** 还没开始的那一场，倒计时数到开始时间，右边也改说「几点开始」 */
const isUpcoming = (activity: SraActivityOverview['activities'][number]) =>
  getCountdownValue(activity.startTime) > Date.now()

const countdownTarget = (activity: SraActivityOverview['activities'][number]) =>
  isUpcoming(activity) ? activity.startTime : activity.endTime

/** 长期玩法动辄大半年，倒计时只报到天，否则一行放不下会换行 */
const countdownFormat = (activity: SraActivityOverview['activities'][number]) =>
  isLongRunning(activity) ? t('home.countdown.d') : t('home.countdown.dh')

const getActivityImage = (activity: SraActivityOverview['activities'][number]) => {
  if (failedImageNames.value.has(activity.name)) return ''
  return activity.cover || ''
}

const handleImageError = (activityName: string) => {
  failedImageNames.value = new Set(failedImageNames.value).add(activityName)
}

const activityCountdownStyle = computed<CSSProperties>(() => ({
  color: ACCENT,
  fontSize: '14px',
  fontWeight: 700,
}))

/** 时间串解析不出来时按 0 处理：否则倒计时与「剩余」判断会吃到 NaN */
const getCountdownValue = (value: string) => {
  const timestamp = new Date(value).getTime()
  return Number.isNaN(timestamp) ? 0 : timestamp
}
</script>

<style scoped src="./activityCard.css"></style>

<style scoped>
.arknights-card {
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);
}

.arknights-card :deep(.ant-card-head-title) {
  font-size: 18px;
  font-weight: 600;
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
      color-mix(in srgb, var(--arknights-accent) 16%, transparent),
      transparent 55%
    ),
    linear-gradient(150deg, #1b1f28 0%, #12151b 60%, #171b23 100%);
  transition:
    transform 0.25s ease,
    box-shadow 0.25s ease;
}

.activity-kind {
  flex-shrink: 0;
  padding: 1px 6px;
  border: 1px solid color-mix(in srgb, var(--arknights-accent) 45%, transparent);
  border-radius: 4px;
  background: rgba(11, 18, 32, 0.55);
  color: var(--arknights-accent);
  font-size: 11px;
  line-height: 16px;
}

.activity-name {
  min-width: 0;
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
  min-width: 0;
  flex-wrap: nowrap;
}

.activity-countdown {
  display: inline-flex;
  align-items: baseline;
  gap: 6px;
  min-width: 0;
  white-space: nowrap;
}

.countdown-label {
  flex-shrink: 0;
  color: rgba(255, 255, 255, 0.75);
  font-size: 12px;
}

/* ---------- 今日开放资源收集 ---------- */
.resource-section {
  margin-top: 18px;
  padding-top: 16px;
  border-top: 1px solid var(--ant-color-border-secondary);
}

.resource-title {
  margin-bottom: 10px;
  color: var(--ant-color-text-secondary);
  font-size: 13px;
}

.resource-list {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.resource-item {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 220px;
  padding: 12px 16px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
}

.resource-stage {
  flex-shrink: 0;
  color: var(--ant-color-text);
  font-size: 15px;
  font-weight: 600;
}

.resource-drop {
  flex-shrink: 0;
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.resource-icon {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
}

.resource-text {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.resource-name {
  color: var(--ant-color-text);
  font-size: 14px;
  font-weight: 600;
}

.resource-tip {
  color: var(--ant-color-text-secondary);
  font-size: 12px;
}
</style>
