<template>
  <div class="tb-version">
    <a-alert
      v-if="taskboardState.versionStoryError"
      type="warning"
      show-icon
      class="tb-version-alert"
      :message="t('core.taskboard.versionSaveFailed')"
      :description="taskboardState.versionStoryError"
    >
      <template #action>
        <a-button size="small" @click="retry">{{ t('core.taskboard.retry') }}</a-button>
      </template>
    </a-alert>

    <a-spin :spinning="taskboardState.loading" class="tb-version-spin">
      <template v-if="groups.length">
        <section class="tb-version-block">
          <div class="tb-version-block-head">
            <span class="tb-version-section-title">{{ t('core.taskboard.versionCurrent') }}</span>
            <span class="tb-version-section-hint">{{
              t('core.taskboard.versionClickToMark')
            }}</span>
          </div>
          <div class="tb-version-current-row">
            <button
              v-for="card in currentCards"
              :key="card.option.key"
              type="button"
              class="tb-version-current"
              :class="{ done: card.node.done }"
              :disabled="isSaving(card.node.record)"
              @click="toggle(card.node.record)"
            >
              <span class="tb-version-current-cover">
                <img
                  v-if="card.node.record.cover_url"
                  :src="card.node.record.cover_url"
                  :alt="card.option.name"
                  loading="lazy"
                  referrerpolicy="no-referrer"
                  @error="hideCover"
                />
              </span>
              <span class="tb-version-current-main">
                <span class="tb-version-current-name">{{ card.option.name }}</span>
                <span class="tb-version-current-version">{{ card.node.record.version }}</span>
                <span v-if="daysLeftOf(card.node.record) !== null" class="tb-version-current-days">
                  {{ t('core.taskboard.versionDaysLeft', { p0: daysLeftOf(card.node.record) }) }}
                </span>
              </span>
              <span class="tb-version-mark" :class="{ on: card.node.done }">
                <CheckSquareFilled v-if="card.node.done" />
                {{
                  card.node.done ? t('core.taskboard.versionDone') : t('core.taskboard.versionMark')
                }}
              </span>
            </button>
          </div>
        </section>

        <section class="tb-version-block">
          <div class="tb-version-block-head">
            <span class="tb-version-section-title">{{ t('core.taskboard.versionTimeline') }}</span>
            <span class="tb-version-section-hint">
              {{ t('core.taskboard.versionTimelineNote') }} ·
              {{ t('core.taskboard.versionLocalNote') }}
            </span>
          </div>
          <VersionStoryTimeline :groups="groups" @toggle="toggle" />
        </section>
      </template>

      <div v-else-if="!taskboardState.loading" class="tb-version-empty">
        <NoData :description="t('core.taskboard.versionEmpty')" />
        <div class="tb-version-empty-hint">{{ t('core.taskboard.versionLocalOnly') }}</div>
      </div>
    </a-spin>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { CheckSquareFilled } from '@ant-design/icons-vue'
import { useTaskboardStateStore } from '@/stores/taskboardState'
import type {
  TaskboardGameOption,
  TaskboardVersionStoryGroup,
  TaskboardVersionStoryNode,
  TaskboardVersionStoryRecord,
} from '@/types/taskboard'
import { beijingNowText, parseActivityTime } from '@/utils/activityTime'
import { safeCoverUrl } from '@/utils/safeUrl'
import VersionStoryTimeline from './VersionStoryTimeline.vue'

interface Props {
  options: TaskboardGameOption[]
}

interface CurrentCard {
  option: TaskboardGameOption
  node: TaskboardVersionStoryNode
}

const props = defineProps<Props>()
const { t } = useI18n()
const taskboardState = useTaskboardStateStore()

const nowText = () => beijingNowText()

const isDone = (record: TaskboardVersionStoryRecord) =>
  taskboardState.isVersionStoryDone(`${record.game}|${record.version}`)
const isSaving = (record: TaskboardVersionStoryRecord) =>
  taskboardState.versionStorySaving.includes(`${record.game}|${record.version}`)

const recordsByGame = computed(() => {
  const allowed = new Set(props.options.map(option => option.key))
  const grouped = new Map<string, TaskboardVersionStoryRecord[]>()
  for (const record of Object.values(taskboardState.versionStory)) {
    if (!allowed.has(record.game)) continue
    const list = grouped.get(record.game)
    if (list) list.push(record)
    else grouped.set(record.game, [record])
  }
  for (const list of grouped.values()) {
    list.sort((left, right) => parseActivityTime(right.start) - parseActivityTime(left.start))
  }
  return grouped
})

const groups = computed<TaskboardVersionStoryGroup[]>(() => {
  const now = Date.now()
  return props.options.flatMap(option => {
    const records = recordsByGame.value.get(option.key)
    if (!records?.length) return []
    const nodes = records.map<TaskboardVersionStoryNode>((record, index) => {
      const end = parseActivityTime(record.end)
      return {
        record,
        done: isDone(record),
        current: index === 0,
        future: parseActivityTime(record.start) > now,
        ended: end > 0 && end <= now,
      }
    })
    return [
      {
        option,
        records: nodes,
        current: nodes[0],
      },
    ]
  })
})

const DAY = 86_400_000

const remainingOf = (record: TaskboardVersionStoryRecord) => {
  const end = parseActivityTime(record.end)
  return end ? Math.max(0, end - Date.now()) : Number.POSITIVE_INFINITY
}

const daysLeftOf = (record: TaskboardVersionStoryRecord) => {
  const left = remainingOf(record)
  return Number.isFinite(left) ? Math.ceil(left / DAY) : null
}

/* 倒计时最短的排在最前面，没有结束时间的排最后。 */
const currentCards = computed<CurrentCard[]>(() =>
  groups.value
    .map(group => ({ option: group.option, node: group.current }))
    .sort((left, right) => remainingOf(left.node.record) - remainingOf(right.node.record))
)

const toggle = async (record: TaskboardVersionStoryRecord) => {
  if (isSaving(record)) return
  const key = `${record.game}|${record.version}`
  const next = isDone(record) ? null : { at: nowText(), end: record.end }
  const error = await taskboardState.setVersionStoryDone(key, next)
  if (error) message.error(t('core.taskboard.versionSaveFailedWithReason', { p0: error }))
}

const retry = () => {
  void taskboardState.retryVersionStory()
}

const hideCover = (event: Event) => {
  const image = event.target as HTMLImageElement
  image.style.display = 'none'
}
</script>

<style scoped>
.tb-version-spin {
  display: block;
  min-height: 120px;
}

.tb-version {
  display: flex;
  flex-direction: column;
  gap: 20px;
  padding: 0 4px;
}

.tb-version-alert {
  margin: 0 0 4px;
}

.tb-version-block {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.tb-version-block-head {
  display: flex;
  align-self: flex-start;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 10px;
  padding: 6px 14px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 999px;
  background: var(--app-background-card-bg, var(--ant-color-bg-container));
}

.tb-version-section-title {
  color: var(--ant-color-text);
  font-size: 16px;
  font-weight: 700;
}

.tb-version-section-hint {
  color: var(--ant-color-text-secondary);
  font-size: 12px;
}

.tb-version-current-row {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.tb-version-current {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  min-width: 220px;
  padding: 8px 12px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: var(--tb-card-radius, 10px);
  background: var(--app-background-card-bg, var(--ant-color-bg-container));
  color: var(--ant-color-text);
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition:
    transform 0.15s,
    border-color 0.15s,
    box-shadow 0.15s;
}

.tb-version-current:hover {
  border-color: var(--ant-color-primary-border);
  box-shadow: var(--tb-card-shadow-hover, 0 4px 14px rgb(0 0 0 / 6%));
  transform: translateY(-2px);
}

.tb-version-current:active {
  transform: translateY(0);
}

.tb-version-current:focus-visible {
  outline: 2px solid var(--ant-color-primary);
  outline-offset: 2px;
}

.tb-version-current.done {
  border-color: var(--ant-color-primary-border);
  background: var(--ant-color-primary-bg);
}

.tb-version-current-cover {
  display: block;
  flex-shrink: 0;
  width: 48px;
  height: 48px;
  overflow: hidden;
  border-radius: 8px;
  background: var(--ant-color-fill-secondary);
}

.tb-version-current-cover img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.tb-version-current-main {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.tb-version-current-name {
  overflow: hidden;
  color: var(--ant-color-text);
  font-size: 14px;
  font-weight: 600;
  line-height: 1.4;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tb-version-current-version {
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  line-height: 1.4;
}

.tb-version-current.done .tb-version-current-version {
  color: var(--ant-color-primary);
}

.tb-version-current-days {
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  line-height: 1.4;
}

.tb-version-mark {
  display: inline-flex;
  flex-shrink: 0;
  align-items: center;
  gap: 4px;
  padding: 0 7px;
  border: 1px solid var(--ant-color-border);
  border-radius: 4px;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  line-height: 18px;
}

.tb-version-mark.on {
  border-color: var(--ant-color-primary-border);
  background: var(--ant-color-bg-container);
  color: var(--ant-color-primary);
}

.tb-version-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 32px 0;
}

.tb-version-empty-hint {
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
}

@media (prefers-reduced-motion: reduce) {
  .tb-version-current {
    transition: none;
  }

  .tb-version-current:hover,
  .tb-version-current:active {
    transform: none;
  }
}
</style>
