<template>
  <div class="tb-version-timeline">
    <div v-for="group in groups" :key="group.option.key" class="tb-version-group">
      <div class="tb-version-game">
        <span class="tb-version-game-name">{{ group.option.name }}</span>
        <span class="tb-version-game-count">
          {{ t('core.taskboard.versionCount', { p0: group.records.length }) }}
        </span>
      </div>
      <div class="tb-version-track">
        <button
          v-for="node in group.records"
          :key="keyOf(node)"
          type="button"
          class="tb-version-card"
          :class="{
            done: node.done,
            current: node.current,
            future: node.future,
            ended: node.ended,
          }"
          :disabled="isSaving(node.record)"
          @click="emit('toggle', node.record)"
        >
          <span class="tb-version-dot" />
          <span class="tb-version-cover">
            <img
              v-if="node.record.cover_url"
              :src="node.record.cover_url"
              :alt="node.record.version_name"
              loading="lazy"
              referrerpolicy="no-referrer"
              @error="hideCover"
            />
          </span>
          <span class="tb-version-card-body">
            <span class="tb-version-card-head">
              <span class="tb-version-card-version">{{ node.record.version }}</span>
              <span class="tb-version-mark" :class="{ on: node.done }">
                <CheckSquareFilled v-if="node.done" />
                {{ node.done ? t('core.taskboard.versionDone') : t('core.taskboard.versionMark') }}
              </span>
            </span>
            <span class="tb-version-card-name" :title="node.record.version_name">
              {{ node.record.version_name }}
            </span>
            <span class="tb-version-card-foot" :class="{ urgent: node.current && !node.ended }">
              <ClockCircleOutlined v-if="node.current && !node.ended" />
              {{ footText(node) }}
            </span>
          </span>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { CheckSquareFilled, ClockCircleOutlined } from '@ant-design/icons-vue'
import { useTaskboardStateStore } from '@/stores/taskboardState'
import type {
  TaskboardVersionStoryGroup,
  TaskboardVersionStoryNode,
  TaskboardVersionStoryRecord,
} from '@/types/taskboard'
import { parseActivityTime } from '@/utils/activityTime'

interface Props {
  groups: TaskboardVersionStoryGroup[]
}

defineProps<Props>()
const emit = defineEmits<{ toggle: [record: TaskboardVersionStoryRecord] }>()
const { t } = useI18n()
const taskboardState = useTaskboardStateStore()

const keyOf = (node: TaskboardVersionStoryNode) => `${node.record.game}|${node.record.version}`
const isSaving = (record: TaskboardVersionStoryRecord) =>
  taskboardState.versionStorySaving.includes(`${record.game}|${record.version}`)

const DAY = 86_400_000

const formatDate = (value: string) => {
  const timestamp = parseActivityTime(value)
  if (!timestamp) return ''
  const date = new Date(timestamp)
  return `${date.getMonth() + 1}/${date.getDate()}`
}

/** 当前版本显示「截止 X · 还有 N 天」，其余显示起止日期。 */
const footText = (node: TaskboardVersionStoryNode) => {
  const end = parseActivityTime(node.record.end)
  if (node.current && !node.ended && end) {
    const days = Math.max(0, Math.ceil((end - Date.now()) / DAY))
    return `${t('core.taskboard.versionEndsAt', { p0: formatDate(node.record.end) })} · ${t('core.taskboard.versionDaysLeft', { p0: days })}`
  }
  return `${formatDate(node.record.start)} → ${formatDate(node.record.end)}`
}

const hideCover = (ev: Event) => {
  const img = ev.target as HTMLImageElement
  img.style.display = 'none'
}
</script>

<style scoped>
.tb-version-timeline {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.tb-version-group {
  display: grid;
  grid-template-columns: 132px minmax(0, 1fr);
  gap: 16px;
  padding: 16px;
  border: 1px solid var(--tb-card-border, var(--ant-color-border-secondary));
  border-radius: var(--tb-card-radius, 10px);
  background: var(--app-background-card-bg, var(--ant-color-bg-container));
}

.tb-version-game {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding-top: 4px;
  border-right: 1px dashed var(--ant-color-border);
  padding-right: 12px;
}

.tb-version-game-name {
  color: var(--ant-color-text);
  font-size: 14px;
  font-weight: 600;
  line-height: 1.5;
}

.tb-version-game-count {
  color: var(--ant-color-text-secondary);
  font-size: 12px;
}

.tb-version-track {
  position: relative;
  display: flex;
  gap: 16px;
  overflow-x: auto;
  padding: 24px 4px 4px;
}

.tb-version-track::before {
  content: '';
  position: absolute;
  top: 14px;
  left: 6px;
  right: 6px;
  border-top: 1px dashed var(--ant-color-border);
}

.tb-version-card {
  position: relative;
  display: flex;
  flex: 0 0 280px;
  flex-direction: column;
  overflow: hidden;
  padding: 0;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: var(--tb-card-radius, 10px);
  background: var(--ant-color-bg-container);
  color: var(--ant-color-text);
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition:
    transform 0.15s,
    border-color 0.15s,
    box-shadow 0.15s;
}

.tb-version-card:hover {
  border-color: var(--ant-color-primary-border);
  box-shadow: 0 4px 14px rgb(0 0 0 / 6%);
  transform: translateY(-2px);
}

.tb-version-card:active {
  transform: translateY(0);
}

.tb-version-card:focus-visible {
  outline: 2px solid var(--ant-color-primary);
  outline-offset: 2px;
}

.tb-version-card.done {
  border-color: var(--ant-color-primary-border);
  background: var(--ant-color-primary-bg);
}

.tb-version-card.future {
  opacity: 0.55;
}

.tb-version-dot {
  position: absolute;
  top: -18px;
  left: 14px;
  z-index: 1;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--ant-color-text-quaternary);
}

.tb-version-card.done .tb-version-dot {
  background: var(--ant-color-primary);
}

.tb-version-card.current .tb-version-dot {
  background: var(--ant-color-primary);
  box-shadow: 0 0 0 3px var(--ant-color-primary-bg);
}

.tb-version-cover {
  display: block;
  aspect-ratio: 2.2;
  background: var(--ant-color-fill-secondary);
}

.tb-version-cover img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.tb-version-card-body {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px 12px 12px;
}

.tb-version-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.tb-version-card-version {
  color: var(--ant-color-text);
  font-size: 20px;
  font-weight: 700;
  line-height: 1.2;
}

.tb-version-card.done .tb-version-card-version {
  color: var(--ant-color-primary);
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

.tb-version-card-name {
  overflow: hidden;
  color: var(--ant-color-text);
  font-size: 14px;
  line-height: 1.4;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tb-version-card-foot {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
  line-height: 18px;
}

.tb-version-card-foot.urgent {
  color: var(--ant-color-primary);
}

@media (max-width: 720px) {
  .tb-version-group {
    grid-template-columns: 1fr;
    gap: 8px;
  }

  .tb-version-game {
    flex-direction: row;
    align-items: baseline;
    gap: 8px;
    border-right: none;
    padding-right: 0;
  }
}
</style>
