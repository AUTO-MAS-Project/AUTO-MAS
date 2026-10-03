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
          {{ t('home.sra.poweredBy', { name: sourceName }) }}
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

    <!-- 版本封面、版本名与版本倒计时由上方的轮播横幅统一承担，这里只留活动列表 -->
    <div
      v-if="activeActivities.length"
      class="activity-list"
      :class="{ 'is-plain': activityPlain }"
    >
      <div v-for="activity in activeActivities" :key="activity.name" class="activity-card">
        <div class="activity-item" :class="{ 'is-fallback': !getActivityImage(activity) }">
          <img
            v-if="getActivityImage(activity)"
            :src="getActivityImage(activity)"
            :alt="activity.name"
            class="activity-image"
            referrerpolicy="no-referrer"
            @error="handleImageError(activity.name)"
          />
          <div class="activity-overlay" />
          <div class="activity-content">
            <div class="activity-name">{{ activity.name }}</div>
            <div v-if="activity.description" class="activity-desc">{{ activity.description }}</div>
            <div class="activity-meta">
              <a-statistic-countdown
                :value="getCountdownValue(activity.endTime)"
                :format="t('home.countdown.dh')"
                :value-style="activityCountdownStyle"
                @finish="emit('refresh')"
              />
              <div class="activity-end-time">
                {{
                  t('home.sra.endedAt', {
                    time: formatActivityTime(activity.endTime, locale),
                  })
                }}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <a-empty v-else-if="!loading && overview.Available" :description="emptyText" />
  </a-card>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, ref } from 'vue'
import type { CSSProperties } from 'vue'
import type { SraActivityOverview } from '@/types/home'
import { handleExternalLink } from '@/utils/openExternal'
import { formatActivityTime } from '@/views/home/activityTime'

defineOptions({ name: 'HomeSraActivityOverview' })

const { t, locale } = useI18n()

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
  }>(),
  {
    plainActivities: false,
    sourceName: 'SRA',
    sourceUrl: 'https://starrailassistant.top',
  }
)

const emit = defineEmits<{ refresh: [] }>()

const failedImageNames = ref(new Set<string>())

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

// 版本封面本身不再渲染，只用来给没有自带图的活动卡片兜底，并决定活动列表用哪套样式
const versionCover = computed(
  () =>
    props.overview.cover || props.overview.activities.find(activity => activity.cover)?.cover || ''
)

const activityPlain = computed(() => props.plainActivities || !versionCover.value)

const getActivityImage = (activity: SraActivityOverview['activities'][number]) => {
  if (failedImageNames.value.has(activity.name)) return ''
  return activity.cover || versionCover.value || ''
}

const handleImageError = (activityName: string) => {
  failedImageNames.value = new Set(failedImageNames.value).add(activityName)
}

const activityCountdownStyle = computed<CSSProperties>(() => ({
  color: props.accent,
  fontSize: '14px',
  fontWeight: 700,
}))

const getCountdownValue = (value: string) => new Date(value).getTime()
</script>

<style scoped src="./activityCard.css"></style>

<style scoped>
.sra-card {
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);
}

.sra-card :deep(.ant-card-head-title) {
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
      color-mix(in srgb, var(--sra-accent) 16%, transparent),
      transparent 55%
    ),
    linear-gradient(150deg, #14203a 0%, #0b1220 60%, #101a2e 100%);
  transition:
    transform 0.25s ease,
    box-shadow 0.25s ease;
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
/* 公共样式已给 .activity-card 兜了 180px，这里只补素色列表在窄屏下更宽的取值 */
@media (max-width: 560px) {
  .activity-list.is-plain .activity-card {
    width: 200px;
  }
}
</style>
