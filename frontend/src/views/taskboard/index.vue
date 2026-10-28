<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import type { TaskboardActivity, TaskboardSection } from '@/types/taskboard'
import { parseActivityTime } from '@/utils/activityTime'
import { useTaskboardStateStore } from '@/stores/taskboardState'
import { useTaskboardData } from './useTaskboardData'
import GamePickerModal from './components/GamePickerModal.vue'
import TaskboardCard from './components/TaskboardCard.vue'
import TaskboardToolbar from './components/TaskboardToolbar.vue'

defineOptions({ name: 'TaskboardPage' })

const { t } = useI18n()

const {
  allEvents,
  completionError,
  completionLoading,
  countByOption,
  countdownOf,
  doneAtOf,
  fmtDate,
  gameMetas,
  gameName,
  isCompletionReady,
  isSaving,
  load,
  loading,
  progressColor,
  progressOf,
  refreshing,
  reloadCompletions,
  sourceIssues,
  stateOf,
  toggleCompletion,
  updatedAt,
} = useTaskboardData(t)

const taskboardState = useTaskboardStateStore()

const tab = ref<'active' | 'done' | 'archived'>('active')
const keyword = ref('')
const gameFilter = ref<string | undefined>(undefined)
const expanded = ref<Record<string, boolean>>({})
const editOpen = ref(false)

const enabledOptions = computed(() => {
  const keys = taskboardState.selectedGames
  if (!keys) return gameMetas.value
  const set = new Set(keys)
  return gameMetas.value.filter(option => set.has(option.key))
})

const enabledKeySet = computed(() => new Set(enabledOptions.value.map(option => option.key)))

const pickerOptions = computed(() =>
  gameMetas.value.map(option => ({ ...option, activeCount: countByOption(option) }))
)

const filtered = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  return allEvents.value.filter(e => {
    if (!enabledKeySet.value.has(e.gameKey)) return false
    if (stateOf(e) !== tab.value) return false
    if (gameFilter.value && e.gameKey !== gameFilter.value) return false
    if (!kw) return true
    return e.title.toLowerCase().includes(kw) || gameName(e.gameKey).toLowerCase().includes(kw)
  })
})

// 时间解析统一走 utils/activityTime，兼容 +08:00 与 +0800
/* 进行中 / 已达成：扁平列表，严格按结束时间从近到远；已归档：按游戏分组。 */
const byEndAsc = (a: TaskboardActivity, b: TaskboardActivity) =>
  parseActivityTime(a.end_time) - parseActivityTime(b.end_time)

const groupOfArchived = (list: TaskboardActivity[]): TaskboardSection[] => {
  const byGame = new Map<string, TaskboardActivity[]>()
  list.forEach(e => {
    const arr = byGame.get(e.gameKey)
    if (arr) arr.push(e)
    else byGame.set(e.gameKey, [e])
  })
  const groups = [...byGame.entries()].map(([key, items]) => ({
    id: key,
    name: gameName(key),
    showHead: true,
    items: [...items].sort((a, b) => parseActivityTime(b.end_time) - parseActivityTime(a.end_time)),
  }))
  groups.sort(
    (a, b) => parseActivityTime(b.items[0]?.end_time) - parseActivityTime(a.items[0]?.end_time)
  )
  return groups
}

const sections = computed<TaskboardSection[]>(() => {
  if (tab.value === 'archived') return groupOfArchived(filtered.value)
  const items = [...filtered.value].sort(byEndAsc)
  return items.length ? [{ id: '', name: '', showHead: false, items }] : []
})

const visibleItems = (sec: TaskboardSection) => {
  if (!sec.showHead || expanded.value[sec.id]) return sec.items
  return sec.items.slice(0, 4)
}

const counts = computed(() => {
  const result = { active: 0, done: 0, archived: 0 }
  allEvents.value.forEach(e => {
    if (!enabledKeySet.value.has(e.gameKey)) return
    if (gameFilter.value && e.gameKey !== gameFilter.value) return
    const state = stateOf(e)
    if (state === 'upcoming') return
    result[state] += 1
  })
  return result
})

const total = computed(() => counts.value.active + counts.value.done + counts.value.archived)

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

const toggleExpand = (id: string) => {
  expanded.value[id] = !expanded.value[id]
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

    <div class="tb-content">
      <TaskboardToolbar
        :keyword="keyword"
        :total="total"
        :options="enabledOptions"
        :filter="gameFilter"
        :counts="counts"
        :tab="tab"
        @update:keyword="keyword = $event"
        @update:filter="gameFilter = $event"
        @update:tab="tab = $event"
        @edit="editOpen = true"
      />

      <a-alert
        v-if="completionError"
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
      <div v-if="tab === 'archived'" class="tb-hint">{{ t('core.taskboard.archiveHint') }}</div>

      <a-spin :spinning="loading && !allEvents.length" class="tb-spin">
        <div v-for="sec in sections" :key="sec.id" class="tb-group">
          <div v-if="sec.showHead" class="tb-group-head">
            <span class="tb-game-name">{{ sec.name }}</span>
            <span class="tb-game-count">{{ sec.items.length }}</span>
          </div>
          <div class="tb-grid">
            <TaskboardCard
              v-for="e in visibleItems(sec)"
              :key="e.id"
              :event="e"
              :state="stateOf(e)"
              :game-name="gameName(e.gameKey)"
              :show-game="!sec.showHead"
              :archived="sec.showHead"
              :countdown="countdownOf(e)"
              :start-text="fmtDate(e.start_time)"
              :end-text="fmtDate(e.end_time)"
              :done-text="doneAtOf(e)"
              :progress="progressOf(e)"
              :progress-color="progressColor(e)"
              :saving="isSaving(e)"
              :ready="isCompletionReady(e)"
              @complete="setStatus(e, 'done')"
              @undo="setStatus(e, 'active')"
            />
          </div>
          <a-button
            v-if="sec.showHead && sec.items.length > 4"
            type="link"
            size="small"
            @click="toggleExpand(sec.id)"
          >
            {{
              expanded[sec.id]
                ? t('core.taskboard.collapse')
                : t('core.taskboard.more', { p0: sec.items.length - 4 })
            }}
          </a-button>
        </div>
        <a-empty v-if="!sections.length && !loading" :description="t('core.taskboard.empty')" />
      </a-spin>
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

.tb-content {
  background: var(--ant-color-bg-container);
  border-radius: 8px;
  padding: 16px;
  width: 100%;
  flex: 1;
}

.tb-alert {
  margin: 0 4px 12px;
}

.tb-hint {
  margin: 0 4px 12px;
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
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

.tb-group-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 4px 10px;
}

.tb-game-name {
  font-weight: 700;
  font-size: 16px;
  color: var(--ant-color-text);
}

.tb-game-count {
  font-size: 12px;
  color: var(--ant-color-text-secondary);
}

.tb-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
  gap: 16px;
}
</style>
