<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { storeToRefs } from 'pinia'
import { EditOutlined, ReloadOutlined } from '@ant-design/icons-vue'
import type { CSSProperties } from 'vue'
import { usePerformanceStore } from '@/stores/performance'
import type { ActivitySnapshot } from './useCommunityActivityApi'
import { useCommunityActivityStore } from '@/stores/communityActivity'
import CommunityActivityCard from './components/CommunityActivityCard.vue'

const { t, locale } = useI18n()
const performanceStore = usePerformanceStore()
const activityStore = useCommunityActivityStore()
const { snapshots, loading, hasLoaded, errorMessage } = storeToRefs(activityStore)
const lastUpdated = computed(
  () =>
    snapshots.value
      .map(snapshot => snapshot.updatedAt)
      .filter(Boolean)
      .sort()
      .at(-1) ?? ''
)

// 分区展示：只列出「有数据的游戏」，无数据的游戏自动不出现；可关闭不需要的游戏（存本地）。
// 中文名是后端便笺合同的稳定枚举，只用于匹配与过滤，不参与界面翻译。
const NOTE_GAMES = ['明日方舟', '终末地', '原神', '星穹铁道', '绝区零']
const ACTIVITY_HIDDEN_GAMES_KEY = 'auto-mas.gamesign.activity-hidden-games'

const readHiddenGames = (): string[] => {
  try {
    const raw = localStorage.getItem(ACTIVITY_HIDDEN_GAMES_KEY)
    const parsed = raw ? (JSON.parse(raw) as unknown) : []
    return Array.isArray(parsed)
      ? parsed.filter((game): game is string => typeof game === 'string')
      : []
  } catch {
    return []
  }
}

const hiddenGames = ref<string[]>(readHiddenGames())
const isGameHidden = (game: string) => hiddenGames.value.includes(game)
const toggleGame = (game: string) => {
  hiddenGames.value = isGameHidden(game)
    ? hiddenGames.value.filter(g => g !== game)
    : [...hiddenGames.value, game]
  localStorage.setItem(ACTIVITY_HIDDEN_GAMES_KEY, JSON.stringify(hiddenGames.value))
}

/** 有便笺数据的游戏，按固定顺序排（其余游戏按出现顺序追加） */
const availableGames = computed(() => {
  const present = new Set(snapshots.value.map(snapshot => snapshot.game))
  const ordered = NOTE_GAMES.filter(game => present.has(game))
  for (const snapshot of snapshots.value) {
    if (!ordered.includes(snapshot.game)) ordered.push(snapshot.game)
  }
  return ordered
})

/** 关闭掉的游戏不进切换条 */
const visibleGames = computed(() =>
  availableGames.value.filter(game => !hiddenGames.value.includes(game))
)

/** 当前选中的游戏；被关闭或无数据时回退到第一个可见游戏 */
const activeGame = ref<string | null>(null)
watch(
  visibleGames,
  games => {
    if (activeGame.value === null || !games.includes(activeGame.value)) {
      activeGame.value = games[0] ?? null
    }
  },
  { immediate: true }
)

const activeSnapshots = computed(() =>
  activeGame.value ? snapshots.value.filter(snapshot => snapshot.game === activeGame.value) : []
)

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

const loadActivity = () => activityStore.load()

const showEmpty = computed(() => hasLoaded.value && snapshots.value.length === 0)
const showAllHidden = computed(
  () => hasLoaded.value && snapshots.value.length > 0 && visibleGames.value.length === 0
)

const editPopoverStyle: CSSProperties = {
  maxWidth: '260px',
}

onMounted(() => {
  void activityStore.load()
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
      <div class="activity-actions">
        <a-popover trigger="click" placement="bottomRight" :overlay-inner-style="editPopoverStyle">
          <template #title>
            <span class="activity-edit-title">{{ t('gamesign.activity.editTitle') }}</span>
          </template>
          <template #content>
            <div class="activity-edit-list">
              <div v-for="game in availableGames" :key="game" class="activity-edit-item">
                <span class="activity-edit-name">{{ game }}</span>
                <a-switch
                  size="small"
                  :checked="!isGameHidden(game)"
                  :aria-label="t('gamesign.activity.editGame', { game })"
                  @change="toggleGame(game)"
                />
              </div>
              <div v-if="!availableGames.length" class="activity-edit-empty">
                {{ t('gamesign.activity.empty') }}
              </div>
            </div>
          </template>
          <a-button type="text" size="small" :disabled="!availableGames.length">
            <template #icon><EditOutlined /></template>
            {{ t('gamesign.activity.edit') }}
          </a-button>
        </a-popover>
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
      </div>
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
      v-else-if="showEmpty"
      :description="t('gamesign.activity.empty')"
      class="activity-state"
    />

    <template v-else>
      <div
        v-if="visibleGames.length"
        class="activity-switcher"
        role="tablist"
        :aria-label="t('gamesign.activity.switchTitle')"
      >
        <button
          v-for="game in visibleGames"
          :key="game"
          type="button"
          role="tab"
          class="activity-chip"
          :class="{ 'is-active': game === activeGame }"
          :aria-selected="game === activeGame"
          @click="activeGame = game"
        >
          {{ game }}
        </button>
      </div>

      <a-empty
        v-if="showAllHidden"
        :description="t('gamesign.activity.allHidden')"
        class="activity-state"
      />

      <div v-else class="activity-grid">
        <article
          v-for="snapshot in activeSnapshots"
          :key="snapshotKey(snapshot)"
          class="activity-card-wrap"
        >
          <CommunityActivityCard
            :snapshot="snapshot"
            :simplified="performanceStore.lowPerformanceMode"
          />
        </article>
      </div>
    </template>
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

.activity-actions {
  display: flex;
  align-items: center;
  gap: 4px;
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

.activity-switcher {
  display: flex;
  gap: 4px;
  overflow-x: auto;
  margin-bottom: 10px;
  padding: 5px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 12px;
  background: var(--ant-color-bg-container);
  scrollbar-width: thin;
}

.activity-chip {
  flex: 0 0 auto;
  padding: 6px 14px;
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

.activity-chip:hover {
  color: var(--ant-color-text);
}

.activity-chip.is-active {
  font-weight: 600;
  color: var(--ant-color-text);
  background: var(--ant-color-fill-secondary);
  box-shadow: inset 0 -2px var(--ant-color-primary);
}

.activity-chip:focus-visible {
  outline: 2px solid var(--ant-color-primary);
  outline-offset: -2px;
}

.activity-edit-title {
  font-weight: 600;
}

.activity-edit-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.activity-edit-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.activity-edit-name {
  min-width: 0;
  overflow: hidden;
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.activity-edit-empty {
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
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
</style>
