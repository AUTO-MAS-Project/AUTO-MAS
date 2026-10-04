<template>
  <a-card
    :title="t('home.module.endfield')"
    class="endfield-card"
    :style="cardStyle"
    :loading="loading"
  >
    <template #extra>
      <div class="card-extra">
        <a-typography-link
          :href="overview.SourceUrl"
          target="_blank"
          rel="noreferrer"
          class="source-link"
          @click="handleExternalLink"
        >
          {{ t('home.endfield.source', { name: overview.SourceName }) }}
        </a-typography-link>
        <a-tag v-if="overview.Stale" color="orange">{{ t('home.endfield.stale') }}</a-tag>
      </div>
    </template>

    <a-alert
      v-if="overview.Message"
      :message="overview.Message"
      :type="overview.Available ? 'warning' : 'error'"
      show-icon
      class="status-alert"
    />

    <div v-if="!loading && !displayItems.length" class="empty-state">
      <a-empty :description="t('home.endfield.noActivity')" />
    </div>

    <!-- 卡池和活动放在同一条横排里：都是「一期一会儿就结束」的条目，按结束时间先后排 -->
    <div v-else-if="!loading" class="activity-list">
      <div v-for="item in displayItems" :key="item.id" class="activity-card">
        <div class="activity-item">
          <img
            v-if="getItemImage(item)"
            :src="getItemImage(item)"
            :alt="item.name"
            class="activity-image"
            referrerpolicy="no-referrer"
            decoding="async"
            @error="handleImageError(item.id)"
          />
          <div class="activity-overlay" />
          <div class="activity-content">
            <div class="activity-head">
              <span v-if="item.kind" class="activity-kind">{{ item.kind }}</span>
              <span class="activity-name">{{ item.name }}</span>
            </div>
            <div v-if="item.up" class="activity-desc">{{ item.up }}</div>
            <div class="activity-meta">
              <span class="activity-countdown">
                <span class="countdown-label">
                  {{ isUpcoming(item) ? t('home.countdown.startsIn') : t('home.countdown.left') }}
                </span>
                <a-statistic-countdown
                  :value="getCountdownValue(countdownTarget(item))"
                  :format="t('home.countdown.dh')"
                  :value-style="activityCountdownStyle"
                  @finish="emit('refresh')"
                />
              </span>
              <div class="activity-end-time">
                {{
                  isUpcoming(item)
                    ? t('home.countdown.startsAt', {
                        time: formatActivityTime(item.startTime, locale),
                      })
                    : t('home.endfield.endsAt', {
                        time: formatActivityTime(item.endTime, locale),
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
import { computed, ref, watch } from 'vue'
import type { CSSProperties } from 'vue'
import type { EndfieldActivityOverview } from '@/types/home'
import { handleExternalLink } from '@/utils/openExternal'
import { formatActivityTime } from '@/views/home/activityTime'

defineOptions({
  name: 'HomeEndfieldOverview',
})

interface Props {
  loading: boolean
  overview: EndfieldActivityOverview
}

const props = defineProps<Props>()

/** 倒计时走完就重新取一次：否则这一期结束后卡片会停在「0 天 0 时」 */
const emit = defineEmits<{
  refresh: []
}>()

const { t, locale } = useI18n()

const ACCENT = '#ffb45a'
const MAX_VISIBLE_ITEMS = 10

/** 卡片里的一条：活动和卡池都压成这个形状 */
interface EndfieldCardItem {
  id: string
  name: string
  kind: string
  image: string
  /** 卡池的 UP 角色之类的补充说明，悬停时展开 */
  up: string
  startTime: string
  endTime: string
}

const cardStyle = computed<CSSProperties>(
  () =>
    ({
      '--endfield-accent': ACCENT,
    }) as CSSProperties
)

const failedImageIds = ref(new Set<string>())

watch(
  () => [props.overview.Activities, props.overview.Pools],
  () => {
    failedImageIds.value = new Set()
  }
)

const getCountdownValue = (value: string) => {
  const timestamp = new Date(value).getTime()
  return Number.isNaN(timestamp) ? 0 : timestamp
}

const displayItems = computed<EndfieldCardItem[]>(() => {
  const now = Date.now()

  const activities: EndfieldCardItem[] = props.overview.Activities.map(activity => ({
    id: activity.Id,
    name: activity.Name,
    kind: activity.Tags[0] ?? '',
    image: activity.ImageUrl,
    up: '',
    startTime: activity.StartTime,
    endTime: activity.EndTime,
  }))

  const pools: EndfieldCardItem[] = props.overview.Pools.map(pool => ({
    id: pool.Id,
    name: pool.Name,
    kind: pool.Type,
    image: pool.ImageUrl,
    up: pool.UpCharacters.length
      ? t('home.endfield.upCharacters', { names: pool.UpCharacters.join('、') })
      : '',
    startTime: pool.StartTime,
    endTime: pool.EndTime,
  }))

  return [...activities, ...pools]
    .filter(item => getCountdownValue(item.endTime) > now)
    .sort((left, right) => getCountdownValue(left.endTime) - getCountdownValue(right.endTime))
    .slice(0, MAX_VISIBLE_ITEMS)
})

const getItemImage = (item: EndfieldCardItem) => {
  if (failedImageIds.value.has(item.id)) return ''
  return item.image || ''
}

const handleImageError = (id: string) => {
  failedImageIds.value = new Set(failedImageIds.value).add(id)
}

/** 还没开始的那一条，倒计时数到开始时间 */
const isUpcoming = (item: EndfieldCardItem) => getCountdownValue(item.startTime) > Date.now()

const countdownTarget = (item: EndfieldCardItem) =>
  isUpcoming(item) ? item.startTime : item.endTime

const activityCountdownStyle: CSSProperties = {
  color: ACCENT,
  fontSize: '14px',
  fontWeight: 700,
}
</script>

<style scoped src="./activityCard.css"></style>

<style scoped>
.endfield-card {
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);
}

.endfield-card :deep(.ant-card-head-title) {
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
      color-mix(in srgb, var(--endfield-accent) 16%, transparent),
      transparent 55%
    ),
    linear-gradient(150deg, #2a2118 0%, #16130f 60%, #1c1813 100%);
  transition:
    transform 0.25s ease,
    box-shadow 0.25s ease;
}

.activity-kind {
  flex-shrink: 0;
  padding: 1px 6px;
  border: 1px solid color-mix(in srgb, var(--endfield-accent) 45%, transparent);
  border-radius: 4px;
  background: rgba(11, 18, 32, 0.55);
  color: var(--endfield-accent);
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

.activity-desc {
  max-height: 0;
  overflow: hidden;
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
}

.activity-card:hover .activity-desc {
  max-height: 40px;
  opacity: 1;
  margin-bottom: 8px;
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
</style>
