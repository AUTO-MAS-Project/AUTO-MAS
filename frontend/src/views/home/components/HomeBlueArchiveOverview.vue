<template>
  <a-card :title="t('home.module.bluearchive')" class="bluearchive-card" :style="cardStyle">
    <template #extra>
      <div class="card-extra">
        <a-typography-link
          href="https://www.gamekee.com/ba/huodong/16"
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
      v-if="overview.Available && !currentLoading && !displayActivities.length"
      class="empty-state"
    >
      <a-empty :description="t('home.bluearchive.noActivity')" />
    </div>

    <!-- 同时可能有好几场活动在跑，按结束时间先后的卡片横排，与其它游戏的活动卡一致 -->
    <div v-else-if="overview.Available && !currentLoading" class="activity-list">
      <div
        v-for="activity in displayActivities"
        :key="activity.name"
        class="activity-card"
        :class="{ 'is-upcoming': isUpcoming(activity) }"
      >
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
            <div v-if="activity.description" class="activity-desc">
              {{ activity.description }}
            </div>
            <div class="activity-meta">
              <a-statistic-countdown
                :value="getCountdownValue(countdownTarget(activity))"
                :format="t('home.countdown.dh')"
                :value-style="activityCountdownStyle"
              />
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
  </a-card>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import type { CSSProperties } from 'vue'
import { blueArchivePresentation } from '@/views/home/blueArchivePresentation'
import { createEmptySraActivityOverview } from '@/types/home'
import type {
  BlueArchiveActivityOverview,
  BlueArchiveServerKey,
  BlueArchiveServerOverview,
} from '@/types/home'
import { handleExternalLink } from '@/utils/openExternal'
import { formatActivityTime } from '@/views/home/activityTime'

defineOptions({ name: 'HomeBlueArchiveOverview' })

const { t, locale } = useI18n()

const props = defineProps<{
  servers: BlueArchiveServerOverview[]
  selected: BlueArchiveServerKey
  loadingByServer: Record<BlueArchiveServerKey, boolean>
}>()

const emit = defineEmits<{
  select: [server: BlueArchiveServerKey]
}>()

const ACCENT = '#3ba9ee'
const MAX_VISIBLE_ACTIVITIES = 6

// 倒计时归零要立刻反映到列表上，而 Date.now() 不是响应式的：用每秒走一格的时钟驱动
const now = ref(Date.now())
const clockTimer = window.setInterval(() => {
  now.value = Date.now()
}, 1000)
onBeforeUnmount(() => window.clearInterval(clockTimer))

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

const failedImageNames = ref(new Set<string>())

// 换服或活动刷新后，失败的封面图要重新尝试
watch([() => props.selected, () => overview.value.activities], () => {
  failedImageNames.value = new Set()
})

const isUpcoming = (activity: BlueArchiveActivityOverview['activities'][number]) =>
  getCountdownValue(activity.startTime) > now.value

const countdownTarget = (activity: BlueArchiveActivityOverview['activities'][number]) =>
  isUpcoming(activity) ? activity.startTime : activity.endTime

const displayActivities = computed(() => {
  const running = overview.value.activities
    .filter(
      activity =>
        getCountdownValue(activity.startTime) <= now.value &&
        getCountdownValue(activity.endTime) > now.value
    )
    .sort((left, right) => getCountdownValue(left.endTime) - getCountdownValue(right.endTime))
  // 只列进行中的话，长草期整片卡片是空的；即将开始的按开始时间跟在后头，卡片上另有标记
  const upcoming = overview.value.activities
    .filter(activity => getCountdownValue(activity.startTime) > now.value)
    .sort((left, right) => getCountdownValue(left.startTime) - getCountdownValue(right.startTime))
  return [...running, ...upcoming].slice(0, MAX_VISIBLE_ACTIVITIES)
})

const getActivityImage = (activity: BlueArchiveActivityOverview['activities'][number]) => {
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

const getCountdownValue = (value: string) => new Date(value).getTime()
</script>

<style scoped src="./activityCard.css"></style>

<style scoped>
.bluearchive-card {
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);
}

.bluearchive-card :deep(.ant-card-head-title) {
  font-size: 18px;
  font-weight: 600;
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
      color-mix(in srgb, var(--bluearchive-accent) 16%, transparent),
      transparent 55%
    ),
    linear-gradient(150deg, #14203a 0%, #0b1220 60%, #101a2e 100%);
  transition:
    transform 0.25s ease,
    box-shadow 0.25s ease;
}

/* 分类标签：活动 / 总力大决 / 爬塔 / 多倍活动 … */
.activity-kind {
  flex-shrink: 0;
  padding: 1px 6px;
  border: 1px solid color-mix(in srgb, var(--bluearchive-accent) 45%, transparent);
  border-radius: 4px;
  background: rgba(11, 18, 32, 0.55);
  color: var(--bluearchive-accent);
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

.activity-card:hover .activity-desc {
  max-height: 60px;
  opacity: 1;
  margin-bottom: 8px;
}

/* 还没开场的那几张压暗一点，一眼能看出哪个正在跑 */
.activity-card.is-upcoming {
  opacity: 0.72;
}

.activity-card.is-upcoming:hover {
  opacity: 1;
}
</style>
