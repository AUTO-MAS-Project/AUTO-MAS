<script setup lang="ts">
import { computed, ref, watch, type Component, type CSSProperties } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  AimOutlined,
  ApiOutlined,
  AppstoreOutlined,
  CompassOutlined,
  HolderOutlined,
  RocketOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons-vue'
import arknightsNoteImage from '@/assets/community-notes/arknights.png'
import endfieldNoteImage from '@/assets/community-notes/endfield.jpg'
import genshinNoteImage from '@/assets/community-notes/genshin.jpg'
import starRailNoteImage from '@/assets/community-notes/star-rail.jpg'
import zenlessNoteImage from '@/assets/community-notes/zenless.jpg'
import type { ActivitySnapshot } from '../useCommunityActivityApi'
import { presentActivity } from '../communityActivityPresentation'
import CommunityActivityMetric from './CommunityActivityMetric.vue'

interface GameVisual {
  accent: string
  backgroundImage: string
  icon: Component
  image: string
  labelKey: string
  uiClass: string
}

const props = withDefaults(defineProps<{ snapshot: ActivitySnapshot; simplified?: boolean }>(), {
  simplified: false,
})
const { t, locale } = useI18n()
const backgroundAttempt = ref(0)

// 背景由文档站分发；哈希前缀与 public/community-notes/manifest.json 对应，绕过发布前缓存。
const NOTE_BACKGROUND_BASE = 'https://doc.auto-mas.top/community-notes'

// 这些中文值是后端稳定游戏枚举，只用于映射，不参与界面翻译。
const GAME_VISUALS: Record<string, GameVisual> = {
  明日方舟: {
    accent: 'var(--ant-color-primary)',
    backgroundImage: `${NOTE_BACKGROUND_BASE}/arknights-background.webp?v=6a23195b201d`,
    icon: AimOutlined,
    image: arknightsNoteImage,
    labelKey: 'gamesign.activity.game.arknights',
    uiClass: 'activity-card--arknights',
  },
  终末地: {
    accent: 'var(--ant-color-success)',
    backgroundImage: `${NOTE_BACKGROUND_BASE}/endfield-background.webp?v=9d3a6fee469e`,
    icon: ApiOutlined,
    image: endfieldNoteImage,
    labelKey: 'gamesign.activity.game.endfield',
    uiClass: 'activity-card--endfield',
  },
  原神: {
    accent: '#8fe3b0',
    backgroundImage: `${NOTE_BACKGROUND_BASE}/genshin-background.webp?v=f06788a6cb81`,
    icon: CompassOutlined,
    image: genshinNoteImage,
    labelKey: 'gamesign.activity.game.genshin',
    uiClass: 'activity-card--genshin',
  },
  星穹铁道: {
    accent: '#62c4e7',
    backgroundImage: `${NOTE_BACKGROUND_BASE}/star-rail-background.webp?v=1048d29ea88f`,
    icon: RocketOutlined,
    image: starRailNoteImage,
    labelKey: 'gamesign.activity.game.starrail',
    uiClass: 'activity-card--star-rail',
  },
  绝区零: {
    accent: '#ffd24a',
    backgroundImage: `${NOTE_BACKGROUND_BASE}/zenless-background.webp?v=e4f8798de02c`,
    icon: ThunderboltOutlined,
    image: zenlessNoteImage,
    labelKey: 'gamesign.activity.game.zenless',
    uiClass: 'activity-card--zenless',
  },
}

const visual = computed(() => GAME_VISUALS[props.snapshot.game])
const presentation = computed(() => presentActivity(props.snapshot))
const cardStyle = computed(
  () =>
    ({ '--activity-accent': visual.value?.accent ?? 'var(--ant-color-primary)' }) as CSSProperties
)
const backgroundUrl = computed(
  () => `${visual.value?.backgroundImage ?? ''}${backgroundAttempt.value ? '&retry=1' : ''}`
)
const statusMeta = computed(() => {
  const colors = {
    success: 'success',
    empty: 'default',
    limited: 'warning',
    unavailable: 'orange',
    failed: 'error',
  }
  return {
    label: t(`gamesign.activity.status.${props.snapshot.status}`),
    color: colors[props.snapshot.status],
  }
})
const alertType = computed(() => {
  if (props.snapshot.status === 'failed') return 'error'
  if (['limited', 'unavailable'].includes(props.snapshot.status)) return 'warning'
  return 'info'
})
const platform = computed(() => {
  if (props.snapshot.platform === '森空岛') return t('gamesign.activity.platform.skland')
  if (props.snapshot.platform === '米游社') return t('gamesign.activity.platform.miyoushe')
  return props.snapshot.platform
})
const updatedAt = computed(() => {
  const date = new Date(props.snapshot.updatedAt)
  return Number.isNaN(date.getTime())
    ? ''
    : date.toLocaleTimeString(locale.value, { hour: '2-digit', minute: '2-digit' })
})

// 每次手动刷新可重试背景；单轮失败最多重试一次，离线时保留底色与本地图标。
watch(
  () => [props.snapshot.game, props.snapshot.updatedAt],
  () => {
    backgroundAttempt.value = 0
  }
)
</script>

<template>
  <a-card
    :bordered="false"
    :class="['activity-card', visual?.uiClass, { 'activity-card--simple': simplified }]"
    :style="cardStyle"
  >
    <img
      v-if="!simplified && visual?.backgroundImage && backgroundAttempt < 2"
      class="activity-background"
      :src="backgroundUrl"
      alt=""
      aria-hidden="true"
      referrerpolicy="no-referrer"
      loading="lazy"
      decoding="async"
      fetchpriority="low"
      @error="backgroundAttempt++"
    />
    <header class="activity-card-header">
      <span
        class="activity-drag-handle"
        :title="t('gamesign.activity.drag')"
        :aria-label="t('gamesign.activity.drag')"
        ><HolderOutlined
      /></span>
      <span class="activity-game-mark">
        <img v-if="visual?.image" class="activity-game-image" :src="visual.image" alt="" />
        <component v-else :is="visual?.icon ?? AppstoreOutlined" aria-hidden="true" />
      </span>
      <div class="activity-card-title">
        <strong>{{ visual?.labelKey ? t(visual.labelKey) : snapshot.game }}</strong>
        <span>{{ platform }}</span>
      </div>
      <a-tag :color="statusMeta.color">{{ statusMeta.label }}</a-tag>
    </header>
    <div class="activity-identity">
      <strong>{{ snapshot.account }}</strong>
      <span v-if="snapshot.roleName && snapshot.roleName !== snapshot.account">{{
        snapshot.roleName
      }}</span>
      <span v-if="snapshot.server">{{ snapshot.server }}</span>
    </div>

    <div
      v-if="presentation.featured.length || presentation.groups.length"
      class="activity-content"
      :class="{
        'activity-content--overview': presentation.overview,
        'activity-content--details-only': !presentation.featured.length,
      }"
    >
      <div v-if="presentation.featured.length" class="activity-featured">
        <CommunityActivityMetric
          v-for="metric in presentation.featured"
          :key="metric.name"
          :metric="metric"
          :simplified="simplified"
          featured
        />
      </div>
      <div class="activity-details">
        <section
          v-for="group in presentation.groups"
          :key="group.labelKey"
          class="activity-section"
        >
          <h3 v-if="group.labelKey">{{ t(group.labelKey) }}</h3>
          <CommunityActivityMetric
            v-for="metric in group.metrics"
            :key="`${metric.period}-${metric.name}`"
            :metric="metric"
          />
        </section>
      </div>
    </div>

    <a-alert
      v-if="snapshot.reason"
      :type="alertType"
      :message="snapshot.reason"
      show-icon
      class="activity-reason"
    />
    <footer class="activity-card-footer">
      <span v-if="snapshot.roleUid">{{
        t('gamesign.activity.roleUid', { uid: snapshot.roleUid })
      }}</span>
      <span v-else>{{ t('gamesign.activity.noRole') }}</span>
      <span v-if="updatedAt">{{ updatedAt }}</span>
    </footer>
  </a-card>
</template>

<style scoped>
.activity-card {
  position: relative;
  isolation: isolate;
  overflow: hidden;
  height: 100%;
  border: 1px solid var(--ant-color-border-secondary);
  border-top: 3px solid var(--activity-accent);
  border-radius: 8px;
  background: var(--ant-color-bg-container);
}

.activity-card:hover {
  border-color: var(--activity-accent);
}

.activity-card--simple {
  box-shadow: none;
  transition: none;
}

.activity-card :deep(.ant-card-body) {
  position: relative;
  display: flex;
  flex-direction: column;
  height: 100%;
  box-sizing: border-box;
  padding: 8px 10px;
}

.activity-background {
  position: absolute;
  z-index: 0;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: center;
  opacity: 0.22;
  pointer-events: none;
}

.activity-card-header,
.activity-identity,
.activity-content,
.activity-reason,
.activity-card-footer {
  position: relative;
  z-index: 1;
}

.activity-card-header {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.activity-card-header :deep(.ant-tag) {
  flex: 0 0 auto;
  min-width: 58px;
  display: inline-flex;
  justify-content: center;
  margin-inline-end: 0;
  text-align: center;
}

.activity-drag-handle {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  width: 16px;
  color: var(--ant-color-text-tertiary);
  cursor: grab;
}

.activity-drag-handle:active {
  cursor: grabbing;
}

.activity-game-mark {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  width: 26px;
  height: 26px;
  border-radius: 6px;
  color: var(--activity-accent);
}

.activity-game-image {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.activity-card-title {
  display: flex;
  flex: 1;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 2px 8px;
  min-width: 0;
  line-height: 1.35;
}

.activity-card-title strong {
  font-size: 14px;
}

.activity-card-title span {
  color: var(--ant-color-text-secondary);
  font-size: 11px;
}

.activity-card-title,
.activity-identity,
.activity-card-footer {
  overflow-wrap: anywhere;
}

.activity-identity {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 2px 8px;
  margin: 4px 0 6px;
  color: var(--ant-color-text-secondary);
  font-size: 11px;
}

.activity-identity strong {
  color: var(--ant-color-text);
  font-weight: 500;
}

.activity-content {
  display: grid;
  grid-template-columns: minmax(116px, 0.8fr) minmax(0, 2fr);
  align-items: start;
  gap: 12px;
  min-width: 0;
}

.activity-featured {
  display: grid;
  min-width: 0;
  gap: 12px;
  padding: 4px 10px 4px 0;
  border-right: 1px solid var(--ant-color-border-secondary);
}

.activity-details,
.activity-section {
  min-width: 0;
}

.activity-section h3 {
  margin: 0 0 2px;
  color: var(--ant-color-text-secondary);
  font-size: 11px;
  font-weight: 500;
}

.activity-content--overview,
.activity-content--details-only {
  grid-template-columns: minmax(0, 1fr);
  gap: 6px;
}

.activity-content--overview .activity-featured {
  grid-auto-flow: column;
  grid-auto-columns: minmax(0, 1fr);
  padding: 2px 0 6px;
  border-right: 0;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.activity-content--overview .activity-details {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.activity-reason {
  margin: 8px 0;
  padding: 6px 8px;
}

.activity-reason :deep(.ant-alert-message) {
  overflow-wrap: anywhere;
  font-size: 12px;
  line-height: 1.35;
}

.activity-card-footer {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 2px 8px;
  margin-top: auto;
  padding-top: 6px;
  color: var(--ant-color-text-secondary);
  font-size: 11px;
  line-height: 1.3;
}

/* 背景构图按游戏独立调整，避免人物主体被紧凑卡片裁掉。 */
.activity-card--arknights .activity-background {
  opacity: 0.32;
}

.activity-card--endfield .activity-background {
  object-position: 78% center;
  opacity: 0.3;
}

.activity-card--genshin .activity-background {
  object-position: 68% center;
}

.activity-card--star-rail .activity-background {
  object-position: 72% center;
}

.activity-card--zenless .activity-background {
  object-position: 70% center;
  opacity: 0.28;
}

html.dark .activity-card--zenless .activity-background {
  opacity: 0.48;
}

@media (max-width: 400px) {
  .activity-content {
    column-gap: 8px;
  }

  .activity-content--overview .activity-details {
    gap: 8px;
  }
}
</style>
