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
      <div class="activity-sticky-header">
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

      <div v-if="activeItem && !isCompact" class="banner-viewport">
        <div class="banner-track">
          <article v-for="item in [activeItem]" :key="item.key" class="banner-slide">
            <div class="banner-body" :style="bannerStyle(item)">
              <img
                v-if="hasCover(item)"
                :src="coverOf(item)"
                :alt="item.title"
                class="banner-cover"
                :class="[`is-${coverMode(item)}`, { 'is-measured': coverModes.has(coverOf(item)) }]"
                referrerpolicy="no-referrer"
                @load="onCoverLoad(coverOf(item), $event)"
                @error="onCoverError(item)"
              />
              <div class="banner-overlay" />

              <div class="banner-content">
                <div class="banner-heading">
                  <span class="banner-dot" :style="{ background: item.accent }" />
                  <span class="banner-game">{{ item.title }}</span>
                  <a-tag v-if="item.stale" color="orange">{{ t('home.sra.stale') }}</a-tag>
                </div>
                <div class="banner-subtitle">{{ bannerSubtitle(item) }}</div>
              </div>

              <!-- 没有进行中的活动时只剩「后续活动即将开始」一行，倒计时整块不出现 -->
              <div v-if="item.endTime || item.ended" class="banner-remaining">
                <template v-if="item.endTime">
                  <div class="remaining-label">{{ countdownLabel(item) }}</div>
                  <a-statistic-countdown
                    :value="countdownValue(countdownTarget(item))"
                    :format="countdownFormat(item)"
                    :value-style="remainingStyle"
                  />
                </template>
                <div v-if="item.ended" class="remaining-sub">
                  {{ t('home.carousel.endedNote') }}
                </div>
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

const { t } = useI18n()

/**
 * 封面的铺法。横幅只有 300px 高、接近 5:1，而各家给的图形状差得远，
 * 统一裁法必然裁坏其中几张（实测：绝区零居中裁只剩腿，重返 1999 居中裁只剩空海面）。
 */
type CoverMode =
  /** 16:9 主视觉：贴顶裁，游戏 logo 与角色的脸都在图的上半部 */
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
const failedCovers = ref(new Set<HomeModuleKey>())
const coverModes = ref(new Map<string, CoverMode>())
// 主封面加载失败后往后挪的候选下标：key -> 当前用的是第几个候选
const coverIndexes = ref(new Map<HomeModuleKey, number>())

const activeIndex = computed(() => {
  const index = props.items.findIndex(item => item.key === selectedKey.value)
  return index === -1 ? 0 : index
})

const activeKey = computed<HomeModuleKey | null>(() => props.items[activeIndex.value]?.key ?? null)

const activeItem = computed(() => props.items[activeIndex.value])
const isCompact = computed(() =>
  ['endfield', 'arknights', 'bluearchive'].includes(activeKey.value ?? '')
)

const remainingStyle: CSSProperties = {
  color: '#fff',
  fontSize: '20px',
  fontWeight: '600',
  lineHeight: '1.2',
}

const hasCover = (item: ActivityBannerItem) =>
  Boolean(coverOf(item)) && !failedCovers.value.has(item.key)

/** 该卡可用的封面候选：主图在前，备用图依次在后 */
const coverCandidatesOf = (item: ActivityBannerItem): string[] =>
  [item.cover, ...(item.coverCandidates ?? [])].filter(Boolean)

/**
 * 正在用的封面地址：候选图加载失败就往后挪一格（星塔旅人的大图时有时无）。
 *
 * 按游戏记游标而不是按地址记——换图之后尺寸要重新量，不能沿用上一张的铺法。
 */
const coverOf = (item: ActivityBannerItem): string =>
  coverCandidatesOf(item)[coverIndexes.value.get(item.key) ?? 0] ?? ''

const onCoverError = (item: ActivityBannerItem) => {
  const next = (coverIndexes.value.get(item.key) ?? 0) + 1
  if (next < coverCandidatesOf(item).length) {
    coverIndexes.value = new Map(coverIndexes.value).set(item.key, next)
    return
  }
  failedCovers.value = new Set(failedCovers.value).add(item.key)
}

const resolveCoverMode = (width: number, height: number): CoverMode => {
  // 无固有尺寸（例如没写 viewBox 的 SVG）就按满幅铺，别让它卡在透明状态
  if (!width || !height) {
    return 'cover'
  }
  // 640 以下才算「小图」——那才是图标、缩略图的量级。
  // 门槛原先是 800，结果星塔旅人官网那张 795×510 的活动主视觉只差 5px 就被当成贴片，
  // 卡片看着像没有图。
  const ratio = width / height
  if (width < 640 || (ratio >= 0.7 && ratio <= 1.5)) {
    return 'inset'
  }
  return ratio < 0.7 ? 'tall' : 'cover'
}

const onCoverLoad = (cover: string, event: Event) => {
  const image = event.target as HTMLImageElement
  const mode = resolveCoverMode(image.naturalWidth, image.naturalHeight)
  coverModes.value = new Map(coverModes.value).set(cover, mode)
}

// 按封面地址记而不是按游戏记：版本更新换图后要重新量，不能沿用上一张的铺法
const coverMode = (item: ActivityBannerItem): CoverMode =>
  coverModes.value.get(coverOf(item)) ?? 'cover'

const bannerStyle = (item: ActivityBannerItem): CSSProperties => {
  if (hasCover(item) && coverMode(item) !== 'inset' && coverModes.value.has(coverOf(item))) {
    return {}
  }
  // 没有满幅封面时用主题色底纹兜底，文字仍是浅色，观感与有封面的一致
  return {
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

.activity-sticky-header {
  position: sticky;
  top: 0;
  z-index: 10;
  display: flex;
  flex-direction: column;
  gap: 8px;
  background: var(--ant-color-bg-layout);
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

.banner-cover.is-cover,
.banner-cover.is-tall {
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

/* 主视觉的游戏 logo 与角色的脸都在上半部，版本标题在下沿，所以贴顶裁 */
.banner-cover.is-cover {
  object-position: center top;
}

/* 超高竖图内容全挤在顶部一小条里；14% 沿用重返 1999 原卡片验证过的取值 */
.banner-cover.is-tall {
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
  background: linear-gradient(
    90deg,
    rgba(8, 10, 14, 0.88) 0%,
    rgba(8, 10, 14, 0.62) 46%,
    rgba(8, 10, 14, 0.18) 100%
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

.banner-heading {
  display: flex;
  align-items: center;
  gap: 8px;
}

.banner-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.banner-game {
  color: rgba(255, 255, 255, 0.82);
  font-size: 13px;
  font-weight: 500;
  letter-spacing: 0.04em;
}

.banner-subtitle {
  display: -webkit-box;
  overflow: hidden;
  color: #fff;
  font-size: 24px;
  font-weight: 600;
  line-height: 1.25;
  text-overflow: ellipsis;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

/* 亮色封面右侧几乎没有压暗，倒计时单独垫一层才读得清 */
.banner-remaining {
  position: absolute;
  right: 20px;
  bottom: 16px;
  padding: 6px 12px;
  text-align: right;
  background: rgba(8, 10, 14, 0.42);
  border-radius: 10px;
}

.remaining-label {
  margin-bottom: 2px;
  color: rgba(255, 255, 255, 0.72);
  font-size: 12px;
}

/* 「后续活动即将开始」：只在这张卡展示的是刚结束的那场时出现 */
.remaining-sub {
  margin-top: 2px;
  color: rgba(255, 255, 255, 0.6);
  font-size: 12px;
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
}
</style>
