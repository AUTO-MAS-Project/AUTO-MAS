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
import {
  useCommunityActivityApi,
  type ActivitySnapshot,
  type ActivityStatus,
} from './useCommunityActivityApi'

interface GameVisual {
  accent: string
  icon: Component
  labelKey: string
}

const { t, locale } = useI18n()
const snapshots = ref<ActivitySnapshot[]>([])
const loading = ref(false)
const hasLoaded = ref(false)
const errorMessage = ref('')
const lastUpdated = ref('')
let requestId = 0

const { queryActivity } = useCommunityActivityApi()

// 这些中文值是后端稳定游戏枚举，只用于映射，不参与界面翻译。
const GAME_VISUALS: Record<string, GameVisual> = {
  明日方舟: {
    accent: 'var(--ant-color-primary)',
    icon: AimOutlined,
    labelKey: 'gamesign.activity.game.arknights',
  },
  终末地: {
    accent: 'var(--ant-color-success)',
    icon: ApiOutlined,
    labelKey: 'gamesign.activity.game.endfield',
  },
  原神: {
    accent: '#8fe3b0',
    icon: CompassOutlined,
    labelKey: 'gamesign.activity.game.genshin',
  },
  星穹铁道: {
    accent: '#62c4e7',
    icon: RocketOutlined,
    labelKey: 'gamesign.activity.game.starrail',
  },
  绝区零: {
    accent: '#ffd24a',
    icon: ThunderboltOutlined,
    labelKey: 'gamesign.activity.game.zenless',
  },
}

const DEFAULT_GAME_VISUAL: GameVisual = {
  accent: 'var(--ant-color-primary)',
  icon: AppstoreOutlined,
  labelKey: '',
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

const activityCardStyle = (game: string) =>
  ({
    '--activity-accent': gameVisual(game).accent,
  }) as CSSProperties

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

const loadActivity = async () => {
  const currentRequestId = ++requestId
  loading.value = true
  errorMessage.value = ''
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
    errorMessage.value = error instanceof Error ? error.message : t('gamesign.activity.queryFailed')
  } finally {
    if (currentRequestId === requestId) {
      hasLoaded.value = true
      loading.value = false
    }
  }
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
            <a-card :bordered="false" class="activity-card">
              <div class="activity-card-header">
                <span
                  class="activity-drag-handle"
                  :title="t('gamesign.activity.drag')"
                  :aria-label="t('gamesign.activity.drag')"
                >
                  <HolderOutlined />
                </span>
                <span class="activity-game-mark" aria-hidden="true">
                  <component :is="gameVisual(element.game).icon" />
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

              <div class="activity-summary">
                <div class="activity-progress-heading">
                  <span>{{ t('gamesign.activity.dailyProgress') }}</span>
                  <strong v-if="hasProgress(element)">
                    {{ element.completed }} / {{ element.target }}
                  </strong>
                  <span v-else class="activity-muted">
                    {{ t('gamesign.activity.noProgress') }}
                  </span>
                </div>
                <a-progress
                  v-if="hasProgress(element)"
                  :percent="progressPercent(element)"
                  :show-info="false"
                  :status="progressStatus(element.status)"
                  :stroke-color="gameVisual(element.game).accent"
                  size="small"
                />
              </div>

              <div class="activity-section-grid">
                <section class="activity-section">
                  <h3>{{ t('gamesign.activity.tasks') }}</h3>
                  <div v-if="element.tasks.length" class="activity-list">
                    <div
                      v-for="task in element.tasks"
                      :key="`${task.name}-${task.period}`"
                      class="activity-row"
                    >
                      <span class="activity-row-name">{{ task.name }}</span>
                      <strong>{{ task.completed }} / {{ task.target }}</strong>
                    </div>
                  </div>
                  <span v-else class="activity-muted">
                    {{ t('gamesign.activity.noTasks') }}
                  </span>
                </section>

                <section class="activity-section">
                  <h3>{{ t('gamesign.activity.resources') }}</h3>
                  <div v-if="element.resources.length" class="activity-list">
                    <div
                      v-for="resource in element.resources"
                      :key="resource.name"
                      class="activity-row"
                    >
                      <span class="activity-row-name">{{ resource.name }}</span>
                      <strong>{{ resource.current }} / {{ resource.target }}</strong>
                    </div>
                  </div>
                  <span v-else class="activity-muted">
                    {{ t('gamesign.activity.noResources') }}
                  </span>
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
  padding: 24px;
  color: var(--ant-color-text);
}

.activity-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.activity-heading {
  display: flex;
  align-items: baseline;
  gap: 12px;
  min-width: 0;
}

.activity-title {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  line-height: 1.4;
}

.activity-updated,
.activity-muted {
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
}

.activity-alert {
  margin-bottom: 16px;
}

.activity-state {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 220px;
}

.activity-spin {
  display: block;
}

.activity-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  grid-auto-rows: 1fr;
  align-items: stretch;
  gap: 16px;
  min-width: 0;
}

.activity-card-wrap {
  min-width: 0;
  min-height: 320px;
}

.activity-card {
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

.activity-card:hover {
  border-color: var(--activity-accent);
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.08);
}

.activity-card :deep(.ant-card-body) {
  display: flex;
  flex-direction: column;
  height: 100%;
  box-sizing: border-box;
  padding: 16px;
}

.activity-card-header {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.activity-drag-handle {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  width: 20px;
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
  width: 38px;
  height: 38px;
  border: 1px solid color-mix(in srgb, var(--activity-accent) 55%, transparent);
  border-radius: 8px;
  background: color-mix(in srgb, var(--activity-accent) 14%, transparent);
  color: var(--activity-accent);
  font-size: 19px;
}

.activity-card-title {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
  line-height: 1.35;
}

.activity-card-title strong {
  font-size: 16px;
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
  gap: 4px 10px;
  margin: 12px 0;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
}

.activity-identity strong {
  color: var(--ant-color-text);
  font-size: 13px;
}

.activity-summary {
  padding: 12px;
  border-radius: 8px;
  background: var(--ant-color-fill-quaternary);
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
  margin-bottom: 6px;
  font-size: 13px;
}

.activity-section-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  margin-top: 14px;
}

.activity-section {
  min-width: 0;
}

.activity-section h3 {
  margin: 0 0 8px;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  font-weight: 600;
}

.activity-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.activity-row {
  min-width: 0;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
}

.activity-row-name {
  min-width: 0;
}

.activity-row strong {
  flex: 0 0 auto;
  color: var(--ant-color-text);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

.activity-reason {
  margin-top: 14px;
}

.activity-reason :deep(.ant-alert-message) {
  overflow-wrap: anywhere;
  font-size: 12px;
}

.activity-card-footer {
  flex: 0 0 auto;
  margin-top: auto;
  padding-top: 12px;
  color: var(--ant-color-text-tertiary);
  font-size: 11px;
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

@media (max-width: 760px) {
  .activity-view {
    padding: 16px;
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
</style>
