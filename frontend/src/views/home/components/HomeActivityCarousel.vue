<template>
  <section
    class="activity-carousel"
    @mouseenter="hovered = true"
    @mouseleave="hovered = false"
    @focusin="focused = true"
    @focusout="onFocusOut"
  >
    <a-card v-if="!items.length" class="carousel-empty">
      <a-empty :description="$t('home.carousel.allHidden')" />
    </a-card>

    <template v-else>
      <div class="activity-header">
        <div class="activity-header-top">
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

          <a-button
            type="link"
            size="small"
            class="activity-all-link"
            @click="navigateTo('/taskboard')"
          >
            {{ $t('taskboard.viewAll') }}
            <ArrowRightOutlined />
          </a-button>
        </div>

        <slot v-if="activeKey" name="community" :module-key="activeKey" />
      </div>

      <div class="activity-layout" :class="{ 'has-detail': activeItem?.extraSections.length }">
        <div v-if="activeItem" class="banner-viewport">
          <HomeActivityBanner
            :key="activeItem.key"
            :item="activeItem"
            @refresh="emit('refresh', activeItem.key)"
          />

          <button
            v-if="items.length > 1"
            type="button"
            class="banner-arrow is-prev"
            :aria-label="$t('home.carousel.prev')"
            @click="select(activeIndex - 1)"
          >
            <LeftOutlined />
          </button>
          <button
            v-if="items.length > 1"
            type="button"
            class="banner-arrow is-next"
            :aria-label="$t('home.carousel.next')"
            @click="select(activeIndex + 1)"
          >
            <RightOutlined />
          </button>
        </div>

        <div v-if="activeKey && activeItem?.extraSections.length" class="activity-detail">
          <HomeActivitySection
            v-for="section in activeItem.extraSections"
            :key="section.id"
            :section="section"
            :accent="activeItem.accent"
            @refresh="emit('refresh', activeKey)"
            @select="emit('select', activeKey, $event)"
            @action="emit('action', activeKey, $event)"
            @dismiss="emit('dismiss', activeKey, $event)"
          />
        </div>
        <aside v-if="activeKey && activeItem" class="activity-sidebar">
          <HomeActivitySection
            :key="activeKey"
            :section="activeItem.activities"
            :accent="activeItem.accent"
            @refresh="emit('refresh', activeKey)"
            @select="emit('select', activeKey, $event)"
            @action="emit('action', activeKey, $event)"
            @dismiss="emit('dismiss', activeKey, $event)"
          />
        </aside>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import type { CSSProperties } from 'vue'
import { ArrowRightOutlined, LeftOutlined, RightOutlined } from '@ant-design/icons-vue'
import { navigateTo } from '@/router'
import type { HomeActivityPanel, HomeModuleKey } from '@/types/home'
import HomeActivityBanner from './HomeActivityBanner.vue'
import HomeActivitySection from './HomeActivitySection.vue'

defineOptions({
  name: 'HomeActivityCarousel',
})

interface Props {
  items: HomeActivityPanel[]
  autoplay: boolean
  autoplayInterval?: number
}

const props = withDefaults(defineProps<Props>(), {
  autoplayInterval: 6000,
})

const emit = defineEmits<{
  refresh: [key: HomeModuleKey]
  select: [key: HomeModuleKey, value: string]
  action: [key: HomeModuleKey, id: string]
  dismiss: [key: HomeModuleKey, id: string]
}>()

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

const activeIndex = computed(() => {
  const index = props.items.findIndex(item => item.key === selectedKey.value)
  return index === -1 ? 0 : index
})

const activeKey = computed<HomeModuleKey | null>(() => props.items[activeIndex.value]?.key ?? null)

const activeItem = computed(() => props.items[activeIndex.value])

const activeChipStyle = (item: HomeActivityPanel): CSSProperties => ({
  '--activity-accent': item.accent,
})

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

.activity-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(320px, 360px);
  align-items: start;
  min-width: 0;
  gap: 12px;
}

.activity-layout > .banner-viewport {
  grid-column: 1;
  grid-row: 1;
}

.activity-layout > .activity-detail {
  grid-column: 1;
  grid-row: 2;
  min-width: 0;
}

.activity-sidebar {
  grid-column: 2;
  grid-row: 1;
  position: relative;
  align-self: stretch;
  min-width: 0;
  min-height: 0;
}

.activity-layout.has-detail > .activity-sidebar {
  grid-row: 1 / 3;
}

/* 侧栏与左侧主图、卡池的总高度对齐，仅活动内容滚动。 */
.activity-sidebar > :deep(.ant-card) {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
}

.activity-sidebar :deep(.ant-card-head) {
  flex-shrink: 0;
}

.activity-sidebar :deep(.ant-card-body) {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior-y: contain;
}

/* 切换条与社区信息跟着页面一起滚：吸顶会一直挡着滚上来的横幅与卡片 */
.activity-header {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* 整条切换栏：外框画在这一行上，游戏标签和「查看全部活动」都在同一条里 */
.activity-header-top {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 5px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 12px;
  background: var(--ant-color-bg-container);
}

.activity-header-top .banner-switcher {
  flex: 1;
  min-width: 0;
  padding: 0;
  border: none;
  border-radius: 0;
  background: transparent;
}

.activity-all-link {
  margin-left: auto;
  flex-shrink: 0;
}

.banner-viewport {
  position: relative;
  overflow: hidden;
  border-radius: 12px;
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
  gap: 12px;
  flex-direction: column;
  min-width: 0;
}

/* 保留空网格列，单张补充卡片也不会被拉伸到整行宽度。 */
.activity-detail :deep(.activity-list.is-activity) {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 260px), 1fr));
  align-items: start;
}

.switcher-chip:focus-visible,
.banner-arrow:focus-visible {
  outline: 2px solid var(--ant-color-primary);
  outline-offset: -2px;
}

@media (prefers-reduced-motion: reduce) {
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

/* 应用侧栏与正文边距还会占用 224px，提前折列以留足主图和时间信息的空间。 */
@media (max-width: 1200px) {
  .activity-layout {
    grid-template-columns: minmax(0, 1fr);
  }

  .activity-layout > .activity-sidebar {
    grid-column: 1;
    grid-row: 2;
  }

  .activity-layout.has-detail > .activity-sidebar {
    grid-row: 3;
  }

  .activity-sidebar > :deep(.ant-card) {
    position: static;
  }

  .activity-layout > .activity-sidebar :deep(.ant-card-body) {
    overflow-y: visible;
  }
}
</style>
