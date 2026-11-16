<template>
  <component
    :is="item.url ? 'a' : 'div'"
    class="banner-body"
    :style="bannerStyle(item)"
    :href="item.url"
    :target="item.url ? '_blank' : undefined"
    :rel="item.url ? 'noreferrer' : undefined"
    @click="item.url && handleExternalLink($event)"
  >
    <img
      v-if="hasCover(item)"
      :src="item.cover"
      :alt="item.title"
      class="banner-cover"
      :class="{ 'is-loaded': loadedCovers.has(item.cover) }"
      referrerpolicy="no-referrer"
      @load="onCoverLoad(item)"
      @error="onCoverError(item)"
    />
    <div class="banner-overlay" />

    <div class="banner-content">
      <div class="banner-badge">
        <span class="banner-dot" :style="{ background: item.accent }" />
        <span class="banner-badge-text">{{ bannerBadge(item) }}</span>
        <a-tag v-if="item.stale" color="orange">{{ t('core.home.sra.stale') }}</a-tag>
      </div>
      <div class="banner-subtitle">{{ bannerSubtitle(item) }}</div>
    </div>

    <!--
  左下角给起止时间，右下角是倒计时（相对时间）：
  两角各占一处，绝对时间与倒计时可对照着看。
  版本号已经在上面那枚徽章里，这里不再重复一遍
-->
    <div
      v-if="item.startTime || item.endTime"
      class="banner-meta"
      :class="{ 'has-remaining': item.endTime }"
    >
      <span v-if="item.startTime" class="meta-time">
        {{ formatActivityTime(item.startTime, locale) }}
      </span>
      <span v-if="item.startTime && item.endTime" class="meta-sep" aria-hidden="true"> ~ </span>
      <span v-if="item.endTime" class="meta-time">
        {{ formatActivityTime(item.endTime, locale) }}
      </span>
    </div>

    <div v-if="item.endTime" class="banner-remaining">
      <div class="remaining-label">{{ countdownLabel(item) }}</div>
      <a-statistic-countdown
        :value="countdownValue(countdownTarget(item))"
        :format="countdownFormat(item)"
        :value-style="remainingStyle"
        @finish="emit('refresh')"
      />
    </div>
  </component>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { ref, watch, type CSSProperties } from 'vue'
import type { ActivityBannerItem } from '@/types/home'
import { handleExternalLink } from '@/utils/openExternal'
import { formatActivityTime } from '@/views/home/activityTime'

const props = defineProps<{ item: ActivityBannerItem }>()
const emit = defineEmits<{ refresh: [] }>()
const { t, locale } = useI18n()
const failedCovers = ref(new Set<string>())
const loadedCovers = ref(new Set<string>())
const remainingStyle: CSSProperties = {
  color: 'var(--activity-accent)',
  fontSize: '28px',
  fontWeight: '700',
  lineHeight: '1.1',
  // 数字逐秒变化时宽度不抖
  fontVariantNumeric: 'tabular-nums',
}

const hasCover = (item: ActivityBannerItem) =>
  Boolean(item.cover) && !failedCovers.value.has(item.cover)

const onCoverError = (item: ActivityBannerItem) => {
  failedCovers.value = new Set(failedCovers.value).add(item.cover)
}

const onCoverLoad = (item: ActivityBannerItem) => {
  loadedCovers.value = new Set(loadedCovers.value).add(item.cover)
}

// 封面地址更新后重试失败图片。
watch(
  () => props.item.cover,
  () => {
    failedCovers.value = new Set()
  }
)

const bannerStyle = (item: ActivityBannerItem): CSSProperties => {
  const accent = { '--activity-accent': item.accent } as CSSProperties
  if (hasCover(item) && loadedCovers.value.has(item.cover)) {
    return accent
  }
  // 没有满幅封面时用主题色底纹兜底，文字仍是浅色，观感与有封面的一致
  return {
    ...accent,
    background: `linear-gradient(120deg, ${item.accent}88 0%, rgba(16, 20, 28, 0.94) 72%)`,
  }
}

const bannerSubtitle = (item: ActivityBannerItem) => {
  if (item.subtitle) {
    return item.subtitle
  }
  if (item.loading) {
    return t('core.home.carousel.loading')
  }
  return item.available ? t('core.home.carousel.noActivity') : t('core.home.carousel.unavailable')
}

/** 徽章：有版本号就报版本，没有的游戏退回游戏名 */
const bannerBadge = (item: ActivityBannerItem) =>
  item.version ? t('core.home.carousel.versionBadge', { version: item.version }) : item.title

const countdownValue = (time: string) => {
  const timestamp = new Date(time).getTime()
  return Number.isNaN(timestamp) ? Date.now() : timestamp
}

/** 活动间隙可能轮到还没开始的那一场，此时倒计时要数到开始时间 */
const isUpcoming = (item: ActivityBannerItem) =>
  Boolean(item.startTime) &&
  countdownValue(item.startTime) > Date.now() &&
  countdownValue(item.endTime) > Date.now()

const countdownTarget = (item: ActivityBannerItem) =>
  isUpcoming(item) ? item.startTime : item.endTime

const countdownLabel = (item: ActivityBannerItem) =>
  isUpcoming(item) ? t('core.home.carousel.startsIn') : t('core.home.carousel.remaining')

const countdownFormat = (item: ActivityBannerItem) => {
  return countdownValue(countdownTarget(item)) - Date.now() <= 0
    ? t('core.home.countdown.ended')
    : t('core.home.countdown.dh')
}
</script>

<style scoped>
.banner-body {
  position: relative;
  display: block;
  aspect-ratio: 16 / 7;
  min-height: 240px;
  overflow: hidden;
  background: var(--ant-color-fill-secondary);
  border-radius: 12px;
}

.banner-cover {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: center top;
  opacity: 0;
  transition: opacity 0.3s ease;
}

.banner-cover.is-loaded {
  opacity: 1;
}

.banner-overlay {
  position: absolute;
  inset: 0;
  /* 只在放标题的左侧压暗，越往右越透：原来 0.88 起的整条压暗会把主图盖掉大半，
     看着像“只露一角”；右下角的倒计时有自己的底衬，不靠这层 */
  background: linear-gradient(
    90deg,
    rgba(8, 10, 14, 0.78) 0%,
    rgba(8, 10, 14, 0.42) 46%,
    rgba(8, 10, 14, 0.08) 100%
  );
}

.banner-content {
  position: absolute;
  top: 0;
  bottom: 0;
  left: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 10px;
  max-width: 62%;
  padding: 0 24px;
}

.banner-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  align-self: flex-start;
  padding: 4px 12px;
  border: 1px solid color-mix(in srgb, var(--activity-accent) 45%, transparent);
  border-radius: 999px;
  background: rgba(11, 18, 32, 0.55);
}

.banner-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}

.banner-badge-text {
  color: var(--activity-accent);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.04em;
}

.banner-subtitle {
  display: -webkit-box;
  overflow: hidden;
  color: #fff;
  font-size: 30px;
  font-weight: 700;
  line-height: 1.2;
  text-overflow: ellipsis;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  /* 压暗减了一层，亮封面上的白字靠自身阴影保证读得清 */
  text-shadow: 0 2px 10px rgba(0, 0, 0, 0.55);
}

/* 亮色封面几乎没有压暗，左右两角的时间信息共用同一套底衬才读得清 */
.banner-meta,
.banner-remaining {
  position: absolute;
  bottom: 16px;
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 12px 22px;
  background: rgba(8, 10, 14, 0.5);
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 14px;
  backdrop-filter: blur(10px);
}

.banner-remaining {
  right: 20px;
  border-color: color-mix(in srgb, var(--activity-accent) 35%, transparent);
}

/* 左下角的起止时间，与右下角的倒计时各占一角 */
.banner-meta {
  left: 24px;
  flex-wrap: wrap;
  gap: 4px 8px;
  padding: 8px 16px;
  color: rgba(255, 255, 255, 0.8);
  font-size: 12px;
  line-height: 1.4;
}

/* 右下角有倒计时时收窄，放不下就换行，不压到倒计时上 */
.banner-meta.has-remaining {
  max-width: calc(100% - 260px);
}

/* 每端时间是一个整体，不从日期中间折行 */
.meta-time {
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}

/* 连接符弱化，左右间距收紧，读起来是一整段起止时间 */
.meta-sep {
  margin: 0 -3px;
  color: rgba(255, 255, 255, 0.4);
}

.remaining-label {
  color: rgba(255, 255, 255, 0.75);
  font-size: 13px;
  letter-spacing: 0.04em;
  white-space: nowrap;
}

@media (prefers-reduced-motion: reduce) {
  .banner-cover {
    transition: none;
  }
}
@media (max-width: 800px) {
  .banner-content {
    max-width: 100%;
    padding: 0 16px;
  }
  .banner-subtitle {
    font-size: 19px;
  }
  .banner-remaining {
    right: 16px;
    bottom: 12px;
  }
  .banner-meta {
    bottom: 12px;
    left: 16px;
  }
}
</style>
