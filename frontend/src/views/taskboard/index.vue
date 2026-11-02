<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import type { TaskboardActivity } from '@/types/taskboard'
import { parseActivityTime } from '@/utils/activityTime'
import { matchesKeyword } from '@/utils/searchMatch'
import { useTaskboardStateStore } from '@/stores/taskboardState'
import { useTaskboardData } from './useTaskboardData'
import GamePickerModal from './components/GamePickerModal.vue'
import TaskboardCard from './components/TaskboardCard.vue'
import TaskboardToolbar from './components/TaskboardToolbar.vue'
import VersionStoryPanel from './components/VersionStoryPanel.vue'
import WeeklyTasksPanel from './components/WeeklyTasksPanel.vue'

defineOptions({ name: 'TaskboardPage' })

const { t } = useI18n()

const {
  allEvents,
  completionError,
  completionLoading,
  countByOption,
  archivedNoteOf,
  coverOf,
  doneAtOf,
  endingSoonOf,
  fmtDate,
  gameMetas,
  gameName,
  isCompletionReady,
  isSaving,
  load,
  loading,
  progressOf,
  refreshing,
  reloadCompletions,
  sourceIssues,
  stateOf,
  toggleCompletion,
  updatedAt,
} = useTaskboardData(t)

const cardStateOf = (e: TaskboardActivity): 'active' | 'done' | 'archived' => {
  const state = stateOf(e)
  return state === 'upcoming' ? 'active' : state
}

const taskboardState = useTaskboardStateStore()

const tab = ref<'active' | 'done' | 'archived' | 'weekly' | 'version'>('active')
const keyword = ref('')
const gameFilter = ref<string | undefined>(undefined)
const editOpen = ref(false)

const enabledOptions = computed(() => {
  const keys = taskboardState.selectedGames
  if (!keys) return gameMetas.value
  const set = new Set(keys)
  return gameMetas.value.filter(option => set.has(option.key))
})

const enabledKeySet = computed(() => new Set(enabledOptions.value.map(option => option.key)))

/** 游戏筛选小卡上的活动数，和进行中计数同源。 */
const gameCounts = computed(() => {
  const map: Record<string, number> = {}
  for (const option of enabledOptions.value) map[option.key] = countByOption(option)
  return map
})

/** 周常与版本主线也吃顶部搜索和游戏筛选，只把筛后的游戏交给面板。 */
const panelOptions = computed(() => {
  const kw = keyword.value.trim()
  return enabledOptions.value.filter(option => {
    if (gameFilter.value && option.key !== gameFilter.value) return false
    if (!kw) return true
    return matchesKeyword(option.name, kw)
  })
})

/* 每周任务是主游戏选择下的子集：未单独勾选时跟随主选择，勾选后只显示被选中的游戏。 */
const weeklyVisibleOptions = computed(() => {
  const selected = taskboardState.weeklyGames
  if (!selected) return panelOptions.value
  const allowed = new Set(selected)
  return panelOptions.value.filter(option => allowed.has(option.key))
})

const pickerOptions = computed(() =>
  gameMetas.value.map(option => ({ ...option, activeCount: countByOption(option) }))
)

const searchMatchedEvents = computed(() => {
  const kw = keyword.value.trim()
  return allEvents.value.filter(e => {
    if (!enabledKeySet.value.has(e.gameKey)) return false
    if (gameFilter.value && e.gameKey !== gameFilter.value) return false
    if (!kw) return true
    const doneText = doneAtOf(e).toLowerCase()
    return (
      matchesKeyword(e.title, kw) ||
      matchesKeyword(gameName(e.gameKey), kw) ||
      doneText.includes(kw.toLowerCase())
    )
  })
})

const filtered = computed(() => searchMatchedEvents.value.filter(e => stateOf(e) === tab.value))

const doneTime = (event: TaskboardActivity) => {
  const text = doneAtOf(event)
  if (!text) return 0
  const timestamp = new Date(text.replace(' ', 'T')).getTime()
  return Number.isNaN(timestamp) ? 0 : timestamp
}

const doneEvents = computed(() =>
  [...filtered.value].sort((left, right) => doneTime(right) - doneTime(left))
)

// 时间解析统一走 utils/activityTime，兼容 +08:00 与 +0800
const byEndAsc = (a: TaskboardActivity, b: TaskboardActivity) =>
  parseActivityTime(a.end_time) - parseActivityTime(b.end_time)

const items = computed<TaskboardActivity[]>(() => {
  /* 已达成按完成时间从近到远；进行中与已归档按结束时间从近到远。 */
  if (tab.value === 'archived') {
    return [...filtered.value].sort(
      (a, b) => parseActivityTime(b.end_time) - parseActivityTime(a.end_time)
    )
  }
  return tab.value === 'done' ? [...doneEvents.value] : [...filtered.value].sort(byEndAsc)
})

const counts = computed(() => {
  const result = { active: 0, done: 0, archived: 0, weekly: 0, version: 0 }
  searchMatchedEvents.value.forEach(e => {
    const state = stateOf(e)
    if (state === 'upcoming') return
    result[state] += 1
  })
  const panelKeys = new Set(panelOptions.value.map(option => option.key))
  result.weekly = weeklyVisibleOptions.value.length
  result.version = Object.values(taskboardState.versionStory).filter(record =>
    panelKeys.has(record.game)
  ).length
  return result
})

const isActivityTab = computed(
  () => tab.value === 'active' || tab.value === 'done' || tab.value === 'archived'
)

const emptyText = computed(() =>
  tab.value === 'done' ? t('core.taskboard.doneEmpty') : t('core.taskboard.empty')
)

/* 进行中、已达成、已归档共用一行说明；每周任务与版本主线不显示。 */
const hintText = computed(() => {
  if (tab.value === 'active') return t('core.taskboard.activeHint')
  if (tab.value === 'done') return t('core.taskboard.doneHint')
  if (tab.value === 'weekly' || tab.value === 'version') return ''
  return t('core.taskboard.archiveHint')
})

const total = computed(() => counts.value.active + counts.value.done + counts.value.archived)

const toolbarTotal = computed(() => {
  if (tab.value === 'weekly') return weeklyVisibleOptions.value.length
  if (tab.value === 'version') return counts.value.version
  return total.value
})

const setStatus = async (e: TaskboardActivity, target: 'active' | 'done') => {
  try {
    await toggleCompletion(e, target)
  } catch (error) {
    message.error(error instanceof Error ? error.message : t('core.taskboard.saveFailed'))
  }
}

const saveGames = async (keys: string[]) => {
  const error = await taskboardState.saveSelection(keys)
  if (error) {
    message.error(t('core.taskboard.saveFailedWithReason', { p0: error }))
    return
  }
  if (gameFilter.value && !enabledOptions.value.some(option => option.key === gameFilter.value)) {
    gameFilter.value = undefined
  }
  editOpen.value = false
}
</script>

<template>
  <div class="taskboard-container">
    <div class="tb-header">
      <h1 class="page-title">{{ t('core.taskboard.title') }}</h1>
      <span class="tb-updated">
        {{
          updatedAt
            ? t('core.taskboard.dataUpdated', { p0: updatedAt })
            : loading || completionLoading
              ? t('core.taskboard.loading')
              : t('core.taskboard.notUpdated')
        }}
      </span>
      <a-button :loading="refreshing || loading" @click="load">
        {{ t('core.taskboard.refresh') }}
      </a-button>
    </div>

    <TaskboardToolbar
      :keyword="keyword"
      :total="toolbarTotal"
      :options="enabledOptions"
      :filter="gameFilter"
      :counts="counts"
      :game-counts="gameCounts"
      :tab="tab"
      @update:keyword="keyword = $event"
      @update:filter="gameFilter = $event"
      @update:tab="tab = $event"
      @edit="editOpen = true"
    />

    <div class="tb-body">
      <a-alert
        v-if="isActivityTab && completionError"
        type="warning"
        show-icon
        class="tb-alert"
        :message="t('core.taskboard.completionFailed')"
        :description="completionError"
      >
        <template #action>
          <a-button size="small" :loading="completionLoading" @click="reloadCompletions">
            {{ t('core.taskboard.retry') }}
          </a-button>
        </template>
      </a-alert>
      <a-alert
        v-if="sourceIssues.length"
        type="warning"
        show-icon
        class="tb-alert"
        :message="t('core.taskboard.sourceIssue')"
        :description="sourceIssues.join('；')"
      />
      <div v-if="hintText" class="tb-hint">{{ hintText }}</div>

      <template v-if="isActivityTab">
        <a-spin :spinning="loading && !allEvents.length" class="tb-spin">
          <div class="tb-group">
            <div class="tb-grid">
              <TaskboardCard
                v-for="e in items"
                :key="e.id"
                :event="e"
                :cover="coverOf(e)"
                :state="cardStateOf(e)"
                :game-name="gameName(e.gameKey)"
                :archived-note="archivedNoteOf(e)"
                :ending-soon="endingSoonOf(e)"
                :start-text="fmtDate(e.start_time)"
                :end-text="fmtDate(e.end_time)"
                :done-text="doneAtOf(e)"
                :progress="progressOf(e)"
                :saving="isSaving(e)"
                :ready="isCompletionReady(e)"
                @complete="setStatus(e, 'done')"
                @undo="setStatus(e, 'active')"
              />
            </div>
          </div>
          <NoData v-if="!items.length && !loading" :description="emptyText" />
        </a-spin>
      </template>

      <WeeklyTasksPanel
        v-else-if="tab === 'weekly'"
        :options="weeklyVisibleOptions"
        :all-options="enabledOptions"
      />
      <VersionStoryPanel v-else-if="tab === 'version'" :options="panelOptions" />
    </div>

    <GamePickerModal
      :open="editOpen"
      :options="pickerOptions"
      :selected="enabledOptions.map(option => option.key)"
      @update:open="editOpen = $event"
      @save="saveGames"
    />
  </div>
</template>

<style scoped>
.taskboard-container {
  width: 100%;
  max-width: 1600px;
  margin: 0 auto;
  padding: 0;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  min-height: 100%;
}

.tb-header {
  margin-bottom: 16px;
  padding: 0 4px;
  display: flex;
  align-items: center;
  gap: 12px;
}

.page-title {
  margin: 0;
  font-size: 32px;
  font-weight: 700;
  color: var(--app-page-title-color, var(--ant-color-text));
}

.tb-updated {
  margin-right: auto;
  font-size: 12px;
  color: var(--ant-color-text-secondary);
}

.tb-body {
  width: 100%;
  flex: 1;
}

.tb-alert {
  margin: 0 4px 12px;
}

.tb-hint {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  align-self: flex-start;
  margin: 0 0 12px;
  padding: 5px 14px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 999px;
  background: var(--app-background-card-bg, var(--ant-color-bg-container));
  color: var(--ant-color-text-secondary);
  font-size: 12px;
}

.tb-spin {
  display: block;
  min-height: 240px;
}

.tb-spin :deep(.ant-spin-container) {
  min-height: 240px;
}

.tb-group {
  margin-bottom: 24px;
}

.tb-grid {
  display: grid;
  grid-template-columns: var(--tb-grid, repeat(4, minmax(0, 1fr)));
  align-items: start;
  gap: var(--tb-gap);
}

@media (max-width: 1280px) {
  .taskboard-container {
    --tb-grid: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 900px) {
  .taskboard-container {
    --tb-grid: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 600px) {
  .taskboard-container {
    --tb-grid: minmax(0, 1fr);
  }
}
</style>
