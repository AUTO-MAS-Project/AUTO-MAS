<template>
  <a-card
    :title="t(section === 'pools' ? 'home.endfield.pools' : 'home.endfield.activities')"
    class="endfield-card"
    :loading="loading"
  >
    <template #extra>
      <div v-if="section === 'activities'" class="card-extra">
        <a-typography-link
          :href="overview.SourceUrl"
          target="_blank"
          rel="noreferrer"
          class="source-link"
          @click="handleExternalLink"
        >
          {{ t('home.sra.poweredBy', { name: 'SRA&AKEData' }) }}
        </a-typography-link>
      </div>
      <a-tag v-else-if="overview.PoolStale" color="orange">{{ t('home.endfield.stale') }}</a-tag>
    </template>

    <!-- 版本主视觉由上方轮播承担；活动和寻访各自展示状态，不再混排。 -->
    <section
      v-if="section === 'activities'"
      class="endfield-section"
      :aria-label="t('home.endfield.activities')"
    >
      <div v-if="overview.Stale" class="section-heading">
        <div class="source-meta">
          <a-tag v-if="overview.Stale" color="orange">{{ t('home.endfield.stale') }}</a-tag>
        </div>
      </div>
      <a-alert
        v-if="completion.errorMessage.value"
        :message="t('home.endfield.completionUnavailable')"
        :description="completion.errorMessage.value"
        type="warning"
        show-icon
        class="status-alert"
      >
        <template #action>
          <a-button size="small" :loading="completion.loading.value" @click="completion.load">
            {{ t('home.endfield.retryCompletion') }}
          </a-button>
        </template>
      </a-alert>
      <a-alert
        v-if="overview.Message"
        :message="overview.Message"
        :type="overview.Available ? 'warning' : 'error'"
        show-icon
        class="status-alert"
      />
      <ul
        v-if="activities.length"
        class="activity-list"
        tabindex="0"
        :aria-label="t('home.endfield.activities')"
      >
        <li v-for="item in activities" :key="item.id" class="activity-card">
          <div
            class="activity-item"
            :class="{
              'is-fallback': !activityImage(item),
              'is-completed': completion.isCompleted(item),
              'is-actionable': canToggleCompletion(item),
              'is-saving': completion.isSaving(item),
            }"
            role="button"
            :tabindex="canToggleCompletion(item) ? 0 : -1"
            :aria-label="
              t(
                completion.isCompleted(item)
                  ? 'home.endfield.undoCompletion'
                  : 'home.endfield.markCompleted',
                { name: item.name }
              )
            "
            :aria-pressed="completion.isCompleted(item)"
            :aria-disabled="!canToggleCompletion(item)"
            :title="
              canToggleCompletion(item)
                ? t(
                    completion.isCompleted(item)
                      ? 'home.endfield.undoCompletion'
                      : 'home.endfield.markCompleted',
                    { name: item.name }
                  )
                : undefined
            "
            @click="toggleCompletion(item)"
            @keydown.enter.prevent="toggleCompletion(item)"
            @keydown.space.prevent="toggleCompletion(item)"
          >
            <img
              v-if="activityImage(item)"
              :key="activityImage(item)"
              :src="activityImage(item)"
              alt=""
              class="activity-image"
              loading="lazy"
              decoding="async"
              referrerpolicy="no-referrer"
              @error="markActivityImageFailed"
            />
            <div class="activity-overlay" />
            <div class="activity-content">
              <div class="activity-head">
                <a-tag
                  :class="{ 'completion-tag': completion.isCompleted(item) }"
                  :color="
                    completion.isCompleted(item) ? undefined : isUpcoming(item) ? 'blue' : 'green'
                  "
                >
                  {{
                    t(
                      completion.isCompleted(item)
                        ? 'home.endfield.completed'
                        : isUpcoming(item)
                          ? 'home.endfield.upcoming'
                          : 'home.endfield.running'
                    )
                  }}
                </a-tag>
                <span v-if="item.kind" class="activity-kind">{{ item.kind }}</span>
              </div>
              <div class="activity-name" :title="item.name">{{ item.name }}</div>
              <div class="activity-meta">
                <a-statistic-countdown
                  :value="countdownTarget(item)"
                  :format="t('home.countdown.dh')"
                  :value-style="activityCountdownStyle(item)"
                  @finish="handleBoundary"
                />
                <time
                  class="activity-end-time"
                  :datetime="isUpcoming(item) ? item.startTime : item.endTime"
                  :title="boundaryLabel(item)"
                  >{{ boundaryLabel(item) }}</time
                >
              </div>
            </div>
            <a-progress
              v-if="isRunning(item)"
              class="activity-progress"
              :percent="activityProgress(item)"
              :show-info="false"
              :stroke-color="activityImage(item) ? '#ffb45a' : undefined"
              :trail-color="activityImage(item) ? 'rgba(255, 255, 255, 0.25)' : undefined"
              :stroke-width="4"
              stroke-linecap="butt"
              status="normal"
            />
          </div>
        </li>
      </ul>
      <a-empty
        v-else-if="!loading && overview.Available"
        :description="t('home.endfield.noActivity')"
      />
    </section>

    <section v-else class="endfield-section pool-section" :aria-label="t('home.endfield.pools')">
      <a-alert
        v-if="overview.PoolMessage"
        :message="overview.PoolMessage"
        type="warning"
        show-icon
        class="status-alert"
      />
      <a-skeleton v-if="overview.PoolLoading && !pools.length" active :paragraph="{ rows: 2 }" />
      <ul v-else-if="pools.length" class="pool-grid">
        <li v-for="item in pools" :key="item.id" class="event-item pool-item">
          <div v-if="item.image && !failedImages.has(item.image)" class="pool-art">
            <img
              :src="item.image"
              alt=""
              loading="lazy"
              decoding="async"
              referrerpolicy="no-referrer"
              @error="markImageFailed(item.image)"
            />
          </div>
          <div class="event-copy">
            <span class="event-kind">{{ item.kind }}</span>
            <h4 :title="item.name">{{ item.name }}</h4>
            <p v-if="item.up" class="pool-up">{{ item.up }}</p>
            <div class="event-countdown">
              <span>{{
                t(isUpcoming(item) ? 'home.countdown.startsIn' : 'home.countdown.left')
              }}</span>
              <a-statistic-countdown
                :value="countdownTarget(item)"
                :format="t('home.countdown.dh')"
                :value-style="countdownStyle"
                @finish="handleBoundary"
              />
            </div>
            <time :datetime="isUpcoming(item) ? item.startTime : item.endTime">
              {{ boundaryLabel(item) }}
            </time>
          </div>
        </li>
      </ul>
      <a-empty v-else-if="!overview.PoolMessage" :description="t('home.endfield.noPools')" />
    </section>
  </a-card>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { CSSProperties } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { useEndfieldActivityCompletionApi } from '@/composables/useEndfieldActivityCompletionApi'
import type { EndfieldActivityOverview } from '@/types/home'
import { handleExternalLink } from '@/utils/openExternal'

defineOptions({ name: 'HomeEndfieldOverview' })

interface CardItem {
  id: string
  name: string
  kind: string
  image: string
  up: string
  startTime: string
  endTime: string
}

const props = defineProps<{
  loading: boolean
  overview: EndfieldActivityOverview
  section: 'activities' | 'pools'
}>()
const emit = defineEmits<{ refresh: [] }>()
const { t, locale } = useI18n()
const now = ref(Date.now())
const failedImages = ref(new Set<string>())
const completion = useEndfieldActivityCompletionApi()

// 活动进度按分钟更新，同时刷新活动状态与过期条目。
let progressTimer: ReturnType<typeof setInterval> | undefined
onMounted(() => {
  if (props.section === 'activities') void completion.load()
  progressTimer = setInterval(() => {
    now.value = Date.now()
  }, 60_000)
})
onBeforeUnmount(() => {
  clearInterval(progressTimer)
})

watch(
  () => props.overview,
  () => {
    now.value = Date.now()
  }
)

// 仅素材地址变更才重试失败图片，分钟时钟不触发重复下载。
watch(
  () =>
    [
      props.overview.Version,
      props.overview.VersionCover,
      props.overview.VersionStartTime,
      props.overview.VersionEndTime,
      ...[...props.overview.Activities, ...props.overview.Pools].map(item => item.ImageUrl),
    ].join('\n'),
  () => {
    failedImages.value = new Set()
  }
)

const timestamp = (value: string) => new Date(value).getTime()
const pending = (items: CardItem[]) =>
  items
    .filter(item => timestamp(item.endTime) > now.value)
    .sort((a, b) => timestamp(a.endTime) - timestamp(b.endTime))

const activities = computed(() =>
  pending(
    props.overview.Activities.map(item => ({
      id: `activity-${item.Id}`,
      name: item.Name,
      kind: item.Tags[0] ?? '',
      image: item.ImageUrl,
      up: '',
      startTime: item.StartTime,
      endTime: item.EndTime,
    }))
  ).sort((a, b) => Number(isUpcoming(a)) - Number(isUpcoming(b)))
)
const pools = computed(() =>
  pending(
    props.overview.Pools.map(item => ({
      id: `pool-${item.Id}`,
      name: item.Name,
      kind: item.Type,
      image: item.ImageUrl,
      up: item.UpCharacters.length
        ? t('home.endfield.upCharacters', { names: item.UpCharacters.join('、') })
        : '',
      startTime: item.StartTime,
      endTime: item.EndTime,
    }))
  )
)

const activityImage = (item: CardItem): string => {
  if (item.image && !failedImages.value.has(item.image)) return item.image
  const version = props.overview
  const cover = version.VersionCover ?? ''
  const validVersion =
    timestamp(version.VersionStartTime ?? '') <= now.value &&
    timestamp(version.VersionEndTime ?? '') > now.value
  return validVersion && cover && !failedImages.value.has(cover) ? cover : ''
}

const markActivityImageFailed = (event: Event) => {
  const url = (event.currentTarget as HTMLImageElement).getAttribute('src')
  if (url) markImageFailed(url)
}

const isUpcoming = (item: CardItem) => timestamp(item.startTime) > now.value
const isRunning = (item: CardItem) =>
  timestamp(item.startTime) <= now.value && timestamp(item.endTime) > now.value
const canToggleCompletion = (item: CardItem) =>
  completion.ready.value && !completion.isSaving(item) && isRunning(item)
const toggleCompletion = async (item: CardItem) => {
  if (!canToggleCompletion(item)) return
  try {
    await completion.toggle(item)
  } catch (error) {
    message.error(error instanceof Error ? error.message : t('home.endfield.completionSaveFailed'))
  }
}
const activityProgress = (item: CardItem) =>
  Math.min(
    100,
    Math.max(
      0,
      ((now.value - timestamp(item.startTime)) /
        (timestamp(item.endTime) - timestamp(item.startTime))) *
        100
    )
  )
const countdownTarget = (item: CardItem) =>
  timestamp(isUpcoming(item) ? item.startTime : item.endTime)
const activityCountdownStyle = (item: CardItem): CSSProperties => ({
  color: activityImage(item) ? '#ffb45a' : 'var(--ant-color-primary)',
  fontSize: '14px',
  fontWeight: 700,
})
const countdownStyle: CSSProperties = {
  color: 'var(--ant-color-text)',
  fontSize: '14px',
  fontWeight: 600,
}

const boundaryLabel = (item: CardItem) => {
  const upcoming = isUpcoming(item)
  const date = new Date(upcoming ? item.startTime : item.endTime)
  const time = date.toLocaleString(locale.value, {
    timeZone: 'Asia/Shanghai',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
  return t(upcoming ? 'home.countdown.startsAt' : 'home.endfield.endsAt', { time }) + ' (UTC+8)'
}

const markImageFailed = (url: string) => {
  failedImages.value = new Set(failedImages.value).add(url)
}

/** 同一时刻多个倒计时结束只发一次请求，同时立即移除过期条目。 */
let refreshQueued = false
const handleBoundary = () => {
  now.value = Date.now()
  if (refreshQueued) return
  refreshQueued = true
  queueMicrotask(() => {
    emit('refresh')
    refreshQueued = false
  })
}
</script>

<style scoped src="./activityCard.css"></style>
<style scoped>
.section-heading,
.source-meta,
.event-countdown {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}
.section-heading {
  justify-content: space-between;
  margin-bottom: 12px;
}
.section-heading h3,
.event-copy h4 {
  margin: 0;
  color: var(--ant-color-text);
  font-size: 14px;
  font-weight: 600;
  line-height: 1.6;
  overflow-wrap: anywhere;
}
.source-meta,
.event-kind,
.event-copy time,
.pool-up,
.event-countdown > span {
  color: var(--ant-color-text-secondary);
  font-size: 12px;
}
.source-meta :deep(.ant-tag),
.activity-head :deep(.ant-tag) {
  margin-inline-end: 0;
}
.activity-list {
  flex-direction: column;
  overflow-x: visible;
  margin: 0;
  padding: 4px 0 8px;
  list-style: none;
  overscroll-behavior-x: contain;
}
.activity-list:focus-visible {
  outline: 2px solid var(--ant-color-primary);
  outline-offset: 2px;
}
.activity-card {
  flex: 0 0 auto;
  width: 100%;
  min-width: 0;
}
.activity-item {
  min-width: 0;
  height: 150px;
  position: relative;
  display: flex;
  align-items: flex-end;
  overflow: hidden;
  border-radius: 10px;
  scroll-snap-align: start;
  background: linear-gradient(150deg, #14203a 0%, #0b1220 60%, #101a2e 100%);
  transition:
    transform 0.25s ease,
    box-shadow 0.25s ease;
}
.activity-kind {
  color: rgba(255, 255, 255, 0.85);
  font-size: 12px;
}
.activity-item.is-actionable {
  cursor: pointer;
}
.activity-item.is-saving {
  cursor: progress;
}
.is-completed .activity-image {
  filter: grayscale(1);
  opacity: 0.6;
}
.activity-head :deep(.completion-tag) {
  color: var(--ant-color-text);
  background: var(--ant-color-bg-container);
  border-color: var(--ant-color-border);
  font-weight: 600;
}
.activity-item:focus-visible {
  outline: 2px solid var(--ant-color-primary);
  outline-offset: 2px;
}
.activity-name {
  margin-bottom: 8px;
  overflow: hidden;
  color: #fff;
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
.activity-progress {
  position: absolute;
  inset: auto 0 0;
  z-index: 2;
  width: 100%;
  margin: 0;
  line-height: 0;
}
.activity-progress :deep(.ant-progress-outer),
.activity-progress :deep(.ant-progress-inner) {
  display: block;
}
.activity-item.is-fallback {
  background: var(--ant-color-fill-quaternary);
  border: 1px solid var(--ant-color-border);
}
.is-fallback .activity-overlay {
  display: none;
}
.is-fallback .activity-name {
  color: var(--ant-color-text);
  text-shadow: none;
}
.is-fallback .activity-kind,
.is-fallback .activity-end-time {
  color: var(--ant-color-text-secondary);
}
.pool-grid {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 0;
  margin: 0;
  list-style: none;
}
.pool-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  min-width: 0;
  padding: 12px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-fill-quaternary);
}
.pool-art {
  flex: 0 0 88px;
  width: 88px;
  height: 88px;
  overflow: hidden;
  border-radius: 4px;
  background: var(--ant-color-bg-container);
}
.pool-art img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}
.event-copy {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}
.event-copy time,
.pool-up {
  line-height: 1.5;
  overflow-wrap: anywhere;
}
.pool-up {
  margin: 0;
}
@media (max-width: 560px) {
  .pool-art {
    flex-basis: 64px;
    width: 64px;
    height: 64px;
  }
}
@media (prefers-reduced-motion: reduce) {
  .activity-item,
  .activity-image {
    transition: none;
  }
}
</style>
