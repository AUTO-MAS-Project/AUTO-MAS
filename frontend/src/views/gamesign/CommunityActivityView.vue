<script setup lang="ts">
import { computed, onMounted, ref, type Component, type CSSProperties } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  AimOutlined,
  ApiOutlined,
  AppstoreOutlined,
  CompassOutlined,
  HolderOutlined,
  ReloadOutlined,
  RocketOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons-vue'
import draggable from 'vuedraggable'
import arknightsNoteBackgroundImage from '@/assets/community-notes/arknights-background.png'
import arknightsNoteImage from '@/assets/community-notes/arknights.png'
import endfieldNoteBackgroundImage from '@/assets/community-notes/endfield-background.png'
import endfieldNoteImage from '@/assets/community-notes/endfield.jpg'
import genshinNoteBackgroundImage from '@/assets/community-notes/genshin-background.png'
import genshinNoteImage from '@/assets/community-notes/genshin.jpg'
import starRailNoteBackgroundImage from '@/assets/community-notes/star-rail-background.png'
import starRailNoteImage from '@/assets/community-notes/star-rail.jpg'
import zenlessNoteBackgroundImage from '@/assets/community-notes/zenless-background.png'
import zenlessNoteImage from '@/assets/community-notes/zenless.png'
import {
  useCommunityActivityApi,
  type ActivitySnapshot,
  type ActivityStatus,
} from './useCommunityActivityApi'

interface GameVisual {
  accent: string
  backgroundImage: string
  icon: Component
  image: string
  labelKey: string
  uiClass: string
}

const { t, locale } = useI18n()
const snapshots = ref<ActivitySnapshot[]>([])
const loading = ref(false)
const hasLoaded = ref(false)
const errorMessage = ref('')
const lastUpdated = ref('')
let requestId = 0
let activityRequest: Promise<void> | null = null

const { queryActivity } = useCommunityActivityApi()

// 这些中文值是后端稳定游戏枚举，只用于映射，不参与界面翻译。
const GAME_VISUALS: Record<string, GameVisual> = {
  明日方舟: {
    accent: 'var(--ant-color-primary)',
    backgroundImage: arknightsNoteBackgroundImage,
    icon: AimOutlined,
    image: arknightsNoteImage,
    labelKey: 'gamesign.activity.game.arknights',
    uiClass: 'activity-card--arknights',
  },
  终末地: {
    accent: 'var(--ant-color-success)',
    backgroundImage: endfieldNoteBackgroundImage,
    icon: ApiOutlined,
    image: endfieldNoteImage,
    labelKey: 'gamesign.activity.game.endfield',
    uiClass: 'activity-card--endfield',
  },
  原神: {
    accent: '#8fe3b0',
    backgroundImage: genshinNoteBackgroundImage,
    icon: CompassOutlined,
    image: genshinNoteImage,
    labelKey: 'gamesign.activity.game.genshin',
    uiClass: 'activity-card--genshin',
  },
  星穹铁道: {
    accent: '#62c4e7',
    backgroundImage: starRailNoteBackgroundImage,
    icon: RocketOutlined,
    image: starRailNoteImage,
    labelKey: 'gamesign.activity.game.starrail',
    uiClass: 'activity-card--star-rail',
  },
  绝区零: {
    accent: '#ffd24a',
    backgroundImage: zenlessNoteBackgroundImage,
    icon: ThunderboltOutlined,
    image: zenlessNoteImage,
    labelKey: 'gamesign.activity.game.zenless',
    uiClass: 'activity-card--zenless',
  },
}

const DEFAULT_GAME_VISUAL: GameVisual = {
  accent: 'var(--ant-color-primary)',
  backgroundImage: '',
  icon: AppstoreOutlined,
  image: '',
  labelKey: '',
  uiClass: 'activity-card--default',
}

const gameVisual = (game: string) => GAME_VISUALS[game] || DEFAULT_GAME_VISUAL

const gameLabel = (game: string) => {
  const labelKey = gameVisual(game).labelKey
  return labelKey ? t(labelKey) : game
}

const platformLabel = (platform: string) => {
  if (platform === '森空岛') return t('gamesign.activity.platform.skland')
  if (platform === '米游社') return t('gamesign.activity.platform.miyoushe')
  return platform
}

const activityCardStyle = (game: string) => {
  const visual = gameVisual(game)
  return {
    '--activity-accent': visual.accent,
    '--activity-background-image': visual.backgroundImage
      ? `url("${visual.backgroundImage}")`
      : 'none',
  } as CSSProperties
}

const statusMeta = (status: ActivityStatus) => {
  switch (status) {
    case 'success':
      return { label: t('gamesign.activity.status.success'), color: 'success' }
    case 'empty':
      return { label: t('gamesign.activity.status.empty'), color: 'default' }
    case 'limited':
      return { label: t('gamesign.activity.status.limited'), color: 'warning' }
    case 'unavailable':
      return { label: t('gamesign.activity.status.unavailable'), color: 'orange' }
    case 'failed':
      return { label: t('gamesign.activity.status.failed'), color: 'error' }
    default:
      return { label: t('gamesign.activity.status.unknown'), color: 'default' }
  }
}

const statusAlertType = (status: ActivityStatus): 'error' | 'warning' | 'info' => {
  if (status === 'failed') return 'error'
  if (status === 'limited' || status === 'unavailable') return 'warning'
  return 'info'
}

const progressStatus = (status: ActivityStatus): 'normal' | 'exception' =>
  status === 'failed' ? 'exception' : 'normal'

const progressPercent = (snapshot: ActivitySnapshot) => {
  if (
    typeof snapshot.completed !== 'number' ||
    typeof snapshot.target !== 'number' ||
    snapshot.target <= 0
  ) {
    return 0
  }
  return Math.min(100, Math.max(0, Math.round((snapshot.completed / snapshot.target) * 100)))
}

const hasProgress = (snapshot: ActivitySnapshot) =>
  typeof snapshot.completed === 'number' &&
  typeof snapshot.target === 'number' &&
  snapshot.target > 0

const dailyTasks = (snapshot: ActivitySnapshot) =>
  snapshot.tasks.filter(task => task.period !== 'weekly')

const weeklyTasks = (snapshot: ActivitySnapshot) =>
  snapshot.tasks.filter(task => task.period === 'weekly')

const hasTaskProgress = (task: ActivitySnapshot['tasks'][number]) => task.target > 0

const hasResourceProgress = (resource: ActivitySnapshot['resources'][number]) => resource.target > 0

const formatTime = (value: string) => {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleTimeString(locale.value, {
    hour: '2-digit',
    minute: '2-digit',
  })
}

const snapshotKey = (snapshot: ActivitySnapshot) =>
  [snapshot.accountUid, snapshot.platform, snapshot.game, snapshot.roleUid, snapshot.roleName]
    .map(value => value || '-')
    .join(':')

const loadActivity = () => {
  if (activityRequest) return activityRequest

  const currentRequestId = ++requestId
  loading.value = true
  errorMessage.value = ''
  const request = (async () => {
    try {
      const data = await queryActivity()
      if (currentRequestId !== requestId) return

      snapshots.value = data
      const updatedValues = data
        .map(snapshot => snapshot.updatedAt)
        .filter(Boolean)
        .sort()
      lastUpdated.value = updatedValues.at(-1) || new Date().toISOString()
    } catch (error) {
      if (currentRequestId !== requestId) return
      errorMessage.value =
        error instanceof Error ? error.message : t('gamesign.activity.queryFailed')
    } finally {
      if (currentRequestId === requestId) {
        hasLoaded.value = true
        loading.value = false
      }
    }
  })()
  activityRequest = request
  void request.then(
    () => {
      if (activityRequest === request) activityRequest = null
    },
    () => {
      if (activityRequest === request) activityRequest = null
    }
  )
  return request
}

const isEmpty = computed(() => hasLoaded.value && snapshots.value.length === 0)

onMounted(() => {
  void loadActivity()
})
</script>

<template>
  <section class="activity-view" :aria-label="t('gamesign.activity.title')">
    <header class="activity-toolbar">
      <div class="activity-heading">
        <h2 class="activity-title">{{ t('gamesign.activity.title') }}</h2>
        <span v-if="lastUpdated" class="activity-updated">
          {{
            t('gamesign.activity.queriedAt', {
              time: formatTime(lastUpdated),
            })
          }}
        </span>
      </div>
      <a-tooltip :title="t('gamesign.activity.refresh')">
        <a-button
          type="text"
          shape="circle"
          :loading="loading"
          :aria-label="t('gamesign.activity.refresh')"
          @click="loadActivity"
        >
          <ReloadOutlined />
        </a-button>
      </a-tooltip>
    </header>

    <a-alert
      v-if="errorMessage"
      type="error"
      show-icon
      :message="errorMessage"
      class="activity-alert"
    />

    <div v-if="loading && !hasLoaded" class="activity-state">
      <a-spin size="large" />
    </div>

    <a-empty
      v-else-if="isEmpty"
      :description="t('gamesign.activity.empty')"
      class="activity-state"
    />

    <a-spin v-else-if="snapshots.length" :spinning="loading" class="activity-spin">
      <draggable
        v-model="snapshots"
        :item-key="snapshotKey"
        :animation="180"
        handle=".activity-drag-handle"
        ghost-class="activity-card-ghost"
        chosen-class="activity-card-chosen"
        class="activity-grid"
      >
        <template #item="{ element }">
          <article class="activity-card-wrap" :style="activityCardStyle(element.game)">
            <a-card :bordered="false" :class="['activity-card', gameVisual(element.game).uiClass]">
              <div class="activity-card-header">
                <span
                  class="activity-drag-handle"
                  :title="t('gamesign.activity.drag')"
                  :aria-label="t('gamesign.activity.drag')"
                >
                  <HolderOutlined />
                </span>
                <span class="activity-game-mark">
                  <img
                    v-if="gameVisual(element.game).image"
                    class="activity-game-image"
                    :src="gameVisual(element.game).image"
                    alt=""
                  />
                  <component v-else :is="gameVisual(element.game).icon" aria-hidden="true" />
                </span>
                <div class="activity-card-title">
                  <strong>{{ gameLabel(element.game) }}</strong>
                  <span>{{ platformLabel(element.platform) }}</span>
                </div>
                <a-tag :color="statusMeta(element.status).color">
                  {{ statusMeta(element.status).label }}
                </a-tag>
              </div>

              <div class="activity-identity">
                <strong>{{ element.account }}</strong>
                <span v-if="element.roleName">{{ element.roleName }}</span>
                <span v-if="element.server">{{ element.server }}</span>
              </div>

              <div v-if="hasProgress(element)" class="activity-summary">
                <div class="activity-progress-heading">
                  <span>{{ t('gamesign.activity.dailyProgress') }}</span>
                  <strong>{{ element.completed }} / {{ element.target }}</strong>
                </div>
                <a-progress
                  :percent="progressPercent(element)"
                  :show-info="false"
                  :status="progressStatus(element.status)"
                  :stroke-color="gameVisual(element.game).accent"
                  size="small"
                />
              </div>

              <div
                v-if="element.tasks.length || element.resources.length"
                class="activity-section-grid"
              >
                <section v-if="dailyTasks(element).length" class="activity-section">
                  <h3>{{ t('gamesign.activity.tasks') }}</h3>
                  <div class="activity-list">
                    <div
                      v-for="task in dailyTasks(element)"
                      :key="`${task.name}-${task.period}`"
                      class="activity-row"
                    >
                      <span class="activity-row-copy">
                        <span class="activity-row-name">{{ task.name }}</span>
                        <small v-if="task.status" class="activity-row-status">
                          {{ task.status }}
                        </small>
                      </span>
                      <strong v-if="hasTaskProgress(task)">
                        {{ task.completed }} / {{ task.target }}
                      </strong>
                    </div>
                  </div>
                </section>

                <section v-if="weeklyTasks(element).length" class="activity-section">
                  <h3>{{ t('gamesign.activity.weeklyTasks') }}</h3>
                  <div class="activity-list">
                    <div
                      v-for="task in weeklyTasks(element)"
                      :key="`${task.name}-${task.period}`"
                      class="activity-row"
                    >
                      <span class="activity-row-copy">
                        <span class="activity-row-name">{{ task.name }}</span>
                        <small v-if="task.status" class="activity-row-status">
                          {{ task.status }}
                        </small>
                      </span>
                      <strong v-if="hasTaskProgress(task)">
                        {{ task.completed }} / {{ task.target }}
                      </strong>
                    </div>
                  </div>
                </section>

                <section
                  v-if="element.resources.length"
                  class="activity-section activity-section--resources"
                >
                  <h3>{{ t('gamesign.activity.resources') }}</h3>
                  <div class="activity-list">
                    <div
                      v-for="resource in element.resources"
                      :key="resource.name"
                      class="activity-row"
                    >
                      <span class="activity-row-copy">
                        <span class="activity-row-name">{{ resource.name }}</span>
                        <small v-if="resource.status" class="activity-row-status">
                          {{ resource.status }}
                        </small>
                      </span>
                      <strong v-if="hasResourceProgress(resource)">
                        {{ resource.current }} / {{ resource.target }}
                      </strong>
                    </div>
                  </div>
                </section>
              </div>

              <a-alert
                v-if="element.reason"
                :type="statusAlertType(element.status)"
                :message="element.reason"
                show-icon
                class="activity-reason"
              />

              <footer class="activity-card-footer">
                <span v-if="element.roleUid">
                  {{ t('gamesign.activity.roleUid', { uid: element.roleUid }) }}
                </span>
                <span v-else>{{ t('gamesign.activity.noRole') }}</span>
                <span v-if="formatTime(element.updatedAt)">
                  {{ formatTime(element.updatedAt) }}
                </span>
              </footer>
            </a-card>
          </article>
        </template>
      </draggable>
    </a-spin>
  </section>
</template>

<style scoped>
.activity-view {
  min-height: 100%;
  box-sizing: border-box;
  padding: 8px 12px;
  color: var(--ant-color-text);
}

.activity-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 6px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.activity-heading {
  display: flex;
  align-items: baseline;
  gap: 8px;
  min-width: 0;
}

.activity-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  line-height: 1.3;
}

.activity-updated,
.activity-muted {
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
}

.activity-alert {
  margin-bottom: 6px;
}

.activity-state {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 120px;
}

.activity-spin {
  display: block;
}

.activity-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  grid-auto-rows: 1fr;
  align-items: stretch;
  gap: 8px;
  min-width: 0;
}

.activity-card-wrap {
  min-width: 0;
  min-height: 0;
}

.activity-card {
  position: relative;
  isolation: isolate;
  overflow: hidden;
  height: 100%;
  border: 1px solid var(--ant-color-border-secondary);
  border-top: 3px solid var(--activity-accent);
  border-radius: 8px;
  background: var(--ant-color-bg-container);
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);
  transition:
    border-color 0.2s ease,
    box-shadow 0.2s ease;
}

.activity-card::before {
  position: absolute;
  z-index: 0;
  inset: 0;
  background-image: var(--activity-background-image);
  background-position: center;
  background-repeat: no-repeat;
  background-size: cover;
  content: '';
  filter: saturate(0.78);
  opacity: 0.24;
  pointer-events: none;
}

.activity-card:hover {
  border-color: var(--activity-accent);
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.08);
}

.activity-card :deep(.ant-card-body) {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  height: 100%;
  box-sizing: border-box;
  padding: 8px;
}

.activity-card-header {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.activity-card-header :deep(.ant-tag) {
  flex: 0 0 auto;
  min-width: 64px;
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
  width: 18px;
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
  width: 28px;
  height: 28px;
  border: 1px solid color-mix(in srgb, var(--activity-accent) 55%, transparent);
  border-radius: 6px;
  background: color-mix(in srgb, var(--activity-accent) 14%, transparent);
  color: var(--activity-accent);
  font-size: 15px;
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
  flex-direction: column;
  min-width: 0;
  line-height: 1.35;
}

.activity-card-title strong {
  font-size: 14px;
}

.activity-card-title span {
  color: var(--ant-color-text-secondary);
  font-size: 12px;
}

.activity-card-title strong,
.activity-card-title span,
.activity-identity span,
.activity-row-name {
  overflow-wrap: anywhere;
}

.activity-identity {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 3px 8px;
  margin: 5px 0;
  color: var(--ant-color-text-secondary);
  font-size: 11px;
}

.activity-identity strong {
  color: var(--ant-color-text);
  font-size: 12px;
}

.activity-summary {
  padding: 6px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 6px;
  background: color-mix(in srgb, var(--ant-color-bg-container) 82%, transparent);
}

.activity-progress-heading,
.activity-row,
.activity-card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.activity-progress-heading {
  margin-bottom: 4px;
  font-size: 12px;
}

.activity-section-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin-top: 8px;
}

.activity-section {
  min-width: 0;
}

.activity-section--resources {
  grid-column: 1 / -1;
}

.activity-section h3 {
  margin: 0 0 3px;
  color: var(--ant-color-text-secondary);
  font-size: 11px;
  font-weight: 600;
}

.activity-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.activity-section--resources .activity-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  column-gap: 12px;
  row-gap: 2px;
}

.activity-row {
  min-width: 0;
  color: var(--ant-color-text-secondary);
  font-size: 11px;
  line-height: 1.3;
}

.activity-row-name {
  min-width: 0;
}

.activity-row-copy {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
}

.activity-row-status {
  color: var(--ant-color-text-tertiary);
  font-size: 10px;
  line-height: 1.25;
  overflow-wrap: anywhere;
}

.activity-row strong {
  flex: 0 0 auto;
  color: var(--ant-color-text);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}

.activity-reason {
  margin-top: 8px;
  padding: 6px 8px;
}

.activity-reason :deep(.ant-alert-message) {
  overflow-wrap: anywhere;
  font-size: 11px;
  line-height: 1.3;
}

.activity-card-footer {
  flex: 0 0 auto;
  flex-wrap: wrap;
  margin-top: 8px;
  padding-top: 6px;
  color: var(--ant-color-text-tertiary);
  font-size: 11px;
  line-height: 1.2;
}

/* 背景构图按游戏独立调整，避免人物主体被紧凑卡片裁掉。 */
.activity-card--arknights::before {
  background-position: center;
}

.activity-card--endfield::before {
  background-position: 78% center;
}

.activity-card--genshin::before {
  background-position: 68% center;
}

.activity-card--star-rail::before {
  background-position: 72% center;
}

.activity-card--zenless::before {
  background-position: 70% center;
}

.activity-card-ghost {
  opacity: 0.45;
}

.activity-card-chosen {
  box-shadow: 0 0 0 2px var(--ant-color-primary-bg);
}

@media (max-width: 1100px) {
  .activity-section-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (max-width: 860px) {
  .activity-view {
    padding: 8px;
  }

  .activity-heading {
    align-items: flex-start;
    flex-direction: column;
    gap: 2px;
  }

  .activity-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (max-width: 560px) {
  .activity-section--resources {
    grid-column: auto;
  }

  .activity-section--resources .activity-list {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
