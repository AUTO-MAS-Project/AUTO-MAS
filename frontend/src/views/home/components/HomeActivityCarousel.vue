<template>
  <section
    class="activity-carousel"
    @mouseenter="hovered = true"
    @mouseleave="hovered = false"
    @focusin="focused = true"
    @focusout="onFocusOut"
  >
    <a-card v-if="!items.length" class="carousel-empty">
      <a-empty :description="t('home.carousel.allHidden')" />
    </a-card>

    <template v-else>
      <div class="activity-header">
        <!-- 没做 tablist 的方向键漫游焦点，就别用 tab 语义许下做不到的承诺 -->
        <div v-if="items.length > 1" class="banner-switcher">
          <button
            v-for="(item, index) in items"
            :key="item.key"
            type="button"
            class="switcher-chip"
            :class="{ 'is-active': index === activeIndex }"
            :style="index === activeIndex ? activeChipStyle(item) : undefined"
            :aria-current="index === activeIndex ? 'true' : undefined"
            @click="select(index)"
          >
            {{ item.title }}
          </button>
        </div>

        <slot v-if="activeKey" name="community" :module-key="activeKey" />
      </div>

      <div v-if="activeItem" class="banner-viewport">
        <div class="banner-track">
          <article v-for="item in [activeItem]" :key="item.key" class="banner-slide">
            <div class="banner-body" :style="bannerStyle(item)">
              <img
                v-if="hasCover(item)"
                :src="item.cover"
                :alt="item.title"
                class="banner-cover"
                :class="[`is-${coverMode(item)}`, { 'is-measured': coverModes.has(item.cover) }]"
                referrerpolicy="no-referrer"
                @load="onCoverLoad(item, $event)"
                @error="onCoverError(item)"
              />
              <div class="banner-overlay" />

              <div class="banner-content">
                <div class="banner-badge">
                  <span class="banner-dot" :style="{ background: item.accent }" />
                  <span class="banner-badge-text">{{ bannerBadge(item) }}</span>
                  <a-tag v-if="item.stale" color="orange">{{ t('home.sra.stale') }}</a-tag>
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
                <span v-if="item.startTime && item.endTime" class="meta-sep" aria-hidden="true">
                  ~
                </span>
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
                />
              </div>
            </div>
          </article>
        </div>

        <button
          v-if="items.length > 1"
          type="button"
          class="banner-arrow is-prev"
          :aria-label="t('home.carousel.prev')"
          @click="select(activeIndex - 1)"
        >
          <LeftOutlined />
        </button>
        <button
          v-if="items.length > 1"
          type="button"
          class="banner-arrow is-next"
          :aria-label="t('home.carousel.next')"
          @click="select(activeIndex + 1)"
        >
          <RightOutlined />
        </button>
      </div>

      <div v-if="activeKey" class="activity-detail">
        <slot name="detail" :module-key="activeKey" />
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import type { CSSProperties } from 'vue'
import { LeftOutlined, RightOutlined } from '@ant-design/icons-vue'
import type { ActivityBannerItem, HomeModuleKey } from '@/types/home'
import { formatActivityTime } from '@/views/home/activityTime'

defineOptions({
  name: 'HomeActivityCarousel',
})

interface Props {
  items: ActivityBannerItem[]
  autoplay: boolean
  autoplayInterval?: number
}

const props = withDefaults(defineProps<Props>(), {
  autoplayInterval: 6000,
})

const { t, locale } = useI18n()

/**
 * 封面的铺法。横幅只有 300px 高、接近 5:1，而各家给的图形状差得远，
 * 统一裁法必然裁坏其中几张（实测：绝区零居中裁只剩腿，重返 1999 居中裁只剩空海面）。
 */
type CoverMode =
  /** 横版主视觉（16:9 那类）：满幅铺开、裁图像中部——横幅接近 5:1，上下必然要裁掉一些，
      裁中间比贴顶稳妥：贴顶会把角色的身子整个切掉，只剩头部与背景 */
  | 'cover'
  /** 超高竖图（重返 1999 官网图 1920×3902）：只取上部条带，取值沿用原卡片里的 14% */
  | 'tall'
  /** 方图或小图（终末地给的是 200×200 卡池头像）：右侧贴片，底纹交给主题色 */
  | 'inset'

const selectedKey = ref<HomeModuleKey | null>(null)
const hovered = ref(false)
const focused = ref(false)
const paused = computed(() => hovered.value || focused.value)
const onFocusOut = (event: FocusEvent) => {
  if (!(event.currentTarget as HTMLElement).contains(event.relatedTarget as Node | null)) {
    focused.value = false
  }
}
// 用户手动选过游戏后就不再自动翻页：下方详情卡正在被人阅读
const userTookControl = ref(false)
const failedCovers = ref(new Set<string>())
const coverModes = ref(new Map<string, CoverMode>())

const activeIndex = computed(() => {
  const index = props.items.findIndex(item => item.key === selectedKey.value)
  return index === -1 ? 0 : index
})

const activeKey = computed<HomeModuleKey | null>(() => props.items[activeIndex.value]?.key ?? null)

const activeItem = computed(() => props.items[activeIndex.value])

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

const resolveCoverMode = (width: number, height: number): CoverMode => {
  // 无固有尺寸（例如没写 viewBox 的 SVG）就按满幅铺，别让它卡在透明状态
  if (!width || !height) {
    return 'cover'
  }
  // 所有来源使用相同的尺寸规则；缩略图与方图走贴片，宽图铺满，竖图取顶部。
  const ratio = width / height
  if (width < 640 || (ratio >= 0.7 && ratio <= 1.5)) {
    return 'inset'
  }
  return ratio < 0.7 ? 'tall' : 'cover'
}

const onCoverLoad = (item: ActivityBannerItem, event: Event) => {
  const image = event.target as HTMLImageElement
  const mode = resolveCoverMode(image.naturalWidth, image.naturalHeight)
  coverModes.value = new Map(coverModes.value).set(item.cover, mode)
}

// 封面列表更新后重试失败的图片，避免暂时不可用的地址一直被跳过。
watch(
  () => props.items.map(item => item.cover).join('\u0000'),
  () => {
    failedCovers.value = new Set()
  }
)

// 按封面地址记而不是按游戏记：版本更新换图后要重新量，不能沿用上一张的铺法
const coverMode = (item: ActivityBannerItem): CoverMode =>
  coverModes.value.get(item.cover) ?? 'cover'

const bannerStyle = (item: ActivityBannerItem): CSSProperties => {
  const accent = { '--activity-accent': item.accent } as CSSProperties
  if (hasCover(item) && coverMode(item) !== 'inset' && coverModes.value.has(item.cover)) {
    return accent
  }
  // 没有满幅封面时用主题色底纹兜底，文字仍是浅色，观感与有封面的一致
  return {
    ...accent,
    background: `linear-gradient(120deg, ${item.accent}88 0%, rgba(16, 20, 28, 0.94) 72%)`,
  }
}

const activeChipStyle = (item: ActivityBannerItem): CSSProperties => ({
  '--activity-accent': item.accent,
})

const bannerSubtitle = (item: ActivityBannerItem) => {
  if (item.subtitle) {
    return item.subtitle
  }
  if (item.loading) {
    return t('home.carousel.loading')
  }
  return item.available ? t('home.carousel.noActivity') : t('home.carousel.unavailable')
}

/** 徽章：有版本号就报版本，没有的游戏退回游戏名 */
const bannerBadge = (item: ActivityBannerItem) =>
  item.version ? t('home.carousel.versionBadge', { version: item.version }) : item.title

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
  isUpcoming(item) ? t('home.carousel.startsIn') : t('home.carousel.remaining')

const countdownFormat = (item: ActivityBannerItem) => {
  return countdownValue(countdownTarget(item)) - Date.now() <= 0
    ? t('home.countdown.ended')
    : t('home.countdown.dh')
}

const goTo = (index: number) => {
  if (!props.items.length) {
    return
  }
  const length = props.items.length
  const nextIndex = ((index % length) + length) % length
  selectedKey.value = props.items[nextIndex].key
}

const select = (index: number) => {
  userTookControl.value = true
  goTo(index)
}

let timer: number | null = null

const autoplayActive = computed(
  () => props.autoplay && !paused.value && !userTookControl.value && props.items.length > 1
)

const syncTimer = () => {
  if (timer !== null) {
    window.clearInterval(timer)
    timer = null
  }
  if (autoplayActive.value) {
    timer = window.setInterval(() => goTo(activeIndex.value + 1), props.autoplayInterval)
  }
}

watch(autoplayActive, syncTimer, { immediate: true })
watch(() => props.autoplayInterval, syncTimer)

// 在「编辑布局」里重新打开自动轮播，视为用户想再让它转起来
watch(
  () => props.autoplay,
  enabled => {
    if (enabled) {
      userTookControl.value = false
    }
  }
)

onBeforeUnmount(() => {
  if (timer !== null) {
    window.clearInterval(timer)
    timer = null
  }
})
</script>

<style scoped>
.activity-carousel {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* 切换条与社区信息跟着页面一起滚：吸顶会一直挡着滚上来的横幅与卡片 */
.activity-header {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.banner-viewport {
  position: relative;
  overflow: hidden;
  border-radius: 12px;
}

.banner-track {
  display: flex;
  transition: transform 0.45s cubic-bezier(0.4, 0, 0.2, 1);
}

.banner-slide {
  flex: 0 0 100%;
  min-width: 0;
}

/* 各游戏卡里的版本大图已经撤掉，这张横幅接手它的高度，裁得没那么狠 */
.banner-body {
  position: relative;
  height: clamp(220px, 24vw, 320px);
  overflow: hidden;
  background: var(--ant-color-fill-secondary);
  border-radius: 12px;
}

.banner-cover {
  position: absolute;
  opacity: 0;
  transition: opacity 0.3s ease;
}

/* 量出尺寸、定下铺法之后才淡入，免得先满幅铺一下再跳成贴片 */
.banner-cover.is-measured {
  opacity: 1;
}

/* 横版主视觉：满幅铺开、裁图像中部。横幅接近 5:1，上下必然要裁掉一些，
   裁中间比贴顶稳妥——贴顶会把角色的身子整个切掉，只剩头部与背景 */
.banner-cover.is-cover {
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: center;
}

.banner-cover.is-tall {
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  /* 超高竖图内容全挤在顶部一小条里；14% 沿用重返 1999 原卡片验证过的取值 */
  object-position: center 14%;
}

.banner-cover.is-inset {
  top: 50%;
  right: 0;
  width: auto;
  max-width: 46%;
  height: auto;
  max-height: 100%;
  object-fit: contain;
  object-position: right center;
  transform: translateY(-50%);
  -webkit-mask-image: linear-gradient(90deg, transparent 0%, #000 38%);
  mask-image: linear-gradient(90deg, transparent 0%, #000 38%);
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

.banner-arrow {
  position: absolute;
  top: 50%;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  background: rgba(8, 10, 14, 0.42);
  border: none;
  border-radius: 50%;
  cursor: pointer;
  opacity: 0;
  transform: translateY(-50%);
  transition:
    opacity 0.2s ease,
    background 0.2s ease;
}

.banner-arrow.is-prev {
  left: 12px;
}

.banner-arrow.is-next {
  right: 12px;
}

.banner-viewport:hover .banner-arrow,
.banner-arrow:focus-visible {
  opacity: 1;
}

.banner-arrow:hover {
  background: rgba(8, 10, 14, 0.68);
}

.banner-switcher {
  display: flex;
  gap: 4px;
  overflow-x: auto;
  padding: 5px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 12px;
  background: var(--ant-color-bg-container);
  scrollbar-width: thin;
}

.switcher-chip {
  flex: 0 0 auto;
  padding: 9px 16px;
  color: var(--ant-color-text-secondary);
  font-size: 13px;
  background: var(--ant-color-fill-quaternary);
  border: 1px solid transparent;
  border-radius: 8px;
  cursor: pointer;
  transition:
    color 0.2s ease,
    border-color 0.2s ease;
}

.switcher-chip:hover {
  color: var(--ant-color-text);
}

.switcher-chip.is-active {
  font-weight: 600;
  color: var(--ant-color-text);
  background: var(--ant-color-fill-secondary);
  box-shadow: inset 0 -2px var(--activity-accent);
}

.activity-detail {
  display: flex;
  flex-direction: column;
}

.switcher-chip:focus-visible,
.banner-arrow:focus-visible {
  outline: 2px solid var(--ant-color-primary);
  outline-offset: -2px;
}

@media (prefers-reduced-motion: reduce) {
  .banner-track,
  .banner-cover,
  .banner-arrow,
  .switcher-chip {
    transition: none;
  }
}

@media (hover: none) {
  .banner-arrow {
    opacity: 1;
  }
}

@media (max-width: 800px) {
  .banner-body {
    height: 220px;
  }

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
