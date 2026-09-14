<template>
  <section
    class="activity-carousel"
    @mouseenter="paused = true"
    @mouseleave="paused = false"
    @focusin="paused = true"
    @focusout="paused = false"
  >
    <a-card v-if="!items.length" class="carousel-empty">
      <a-empty :description="t('home.carousel.allHidden')" />
    </a-card>

    <template v-else>
      <div class="banner-viewport">
        <div class="banner-track" :style="trackStyle">
          <article
            v-for="(item, index) in items"
            :key="item.key"
            class="banner-slide"
            :aria-hidden="index !== activeIndex"
          >
            <div class="banner-body" :style="bannerStyle(item)">
              <img
                v-if="hasCover(item)"
                :src="item.cover"
                :alt="item.title"
                class="banner-cover"
                :class="[`is-${coverMode(item)}`, { 'is-measured': coverModes.has(item.cover) }]"
                referrerpolicy="no-referrer"
                @load="onCoverLoad(item.cover, $event)"
                @error="onCoverError(item.key)"
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

              <div v-if="item.endTime" class="banner-remaining">
                <div class="remaining-label">{{ t('home.carousel.remaining') }}</div>
                <a-statistic-countdown
                  :value="countdownValue(item.endTime)"
                  :format="countdownFormat(item.endTime)"
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
const paused = ref(false)
// 用户手动选过游戏后就不再自动翻页：下方详情卡正在被人阅读
const userTookControl = ref(false)
const failedCovers = ref(new Set<HomeModuleKey>())
const coverModes = ref(new Map<string, CoverMode>())

const activeIndex = computed(() => {
  const index = props.items.findIndex(item => item.key === selectedKey.value)
  return index === -1 ? 0 : index
})

const activeKey = computed<HomeModuleKey | null>(() => props.items[activeIndex.value]?.key ?? null)

const trackStyle = computed<CSSProperties>(() => ({
  transform: `translateX(-${activeIndex.value * 100}%)`,
}))

const remainingStyle: CSSProperties = {
  color: '#fff',
  fontSize: '20px',
  fontWeight: '600',
  lineHeight: '1.2',
}

const hasCover = (item: ActivityBannerItem) =>
  Boolean(item.cover) && !failedCovers.value.has(item.key)

const onCoverError = (key: HomeModuleKey) => {
  failedCovers.value = new Set(failedCovers.value).add(key)
}

const resolveCoverMode = (width: number, height: number): CoverMode => {
  // 无固有尺寸（例如没写 viewBox 的 SVG）就按满幅铺，别让它卡在透明状态
  if (!width || !height) {
    return 'cover'
  }
  const ratio = width / height
  if (width < 800 || (ratio >= 0.7 && ratio <= 1.5)) {
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
  coverModes.value.get(item.cover) ?? 'cover'

const bannerStyle = (item: ActivityBannerItem): CSSProperties => {
  if (hasCover(item) && coverMode(item) !== 'inset' && coverModes.value.has(item.cover)) {
    return {}
  }
  // 没有满幅封面时用主题色底纹兜底，文字仍是浅色，观感与有封面的一致
  return {
    background: `linear-gradient(120deg, ${item.accent}88 0%, rgba(16, 20, 28, 0.94) 72%)`,
  }
}

const activeChipStyle = (item: ActivityBannerItem): CSSProperties => ({
  borderColor: item.accent,
  color: item.accent,
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

const countdownFormat = (time: string) => {
  return countdownValue(time) - Date.now() <= 0 ? t('home.countdown.ended') : t('home.countdown.dh')
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
  height: 300px;
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
  gap: 8px;
  overflow-x: auto;
  padding-bottom: 2px;
  scrollbar-width: thin;
}

.switcher-chip {
  flex: 0 0 auto;
  padding: 4px 12px;
  color: var(--ant-color-text-secondary);
  font-size: 13px;
  background: var(--ant-color-fill-quaternary);
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 999px;
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
  background: var(--ant-color-fill-tertiary);
}

.activity-detail {
  display: flex;
  flex-direction: column;
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
