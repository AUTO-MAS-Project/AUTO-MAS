<template>
  <a-card
    size="small"
    class="tb-card"
    :class="{ done: state === 'done' }"
    :body-style="{ padding: '12px 14px' }"
  >
    <template #cover>
      <div class="tb-cover-wrap">
        <img
          v-if="cover"
          :src="cover"
          :alt="event.title"
          loading="lazy"
          referrerpolicy="no-referrer"
          class="tb-cover"
          @error="hideCover"
        />
      </div>
    </template>
    <div class="tb-card-body">
      <div class="tb-card-top">
        <a-tag class="tb-card-game">{{ gameName }}</a-tag>
        <a-tag v-if="state === 'archived'" class="tb-status">{{ statusText }}</a-tag>
      </div>

      <span class="tb-card-title" :title="event.title">{{ event.title }}</span>

      <a-tooltip
        v-if="event.description"
        :title="event.description"
        placement="topLeft"
        :overlay-style="{ maxWidth: '420px' }"
      >
        <div class="tb-card-desc-wrap">
          <p class="tb-card-desc">{{ event.description }}</p>
        </div>
      </a-tooltip>
      <div v-else class="tb-card-desc-wrap">
        <p class="tb-card-desc is-placeholder">
          {{
            state === 'archived'
              ? t('core.taskboard.stateEnded')
              : state === 'done'
                ? t('core.taskboard.stateDone')
                : t('core.taskboard.openingNow')
          }}
        </p>
      </div>

      <div class="tb-card-times">
        <span class="tb-card-time">{{ startText }} – {{ endText }}</span>
        <span v-if="state === 'done' && doneText" class="tb-card-done-at">
          {{ t('core.taskboard.doneAt', { p0: doneText }) }}
        </span>
      </div>

      <template v-if="state === 'active'">
        <TaskCountdown :end-time="event.end_time" />
        <a-progress
          v-if="progress !== null"
          :percent="progress"
          :show-info="false"
          size="small"
          :stroke-color="'var(--ant-color-primary)'"
          class="tb-progress"
        />
      </template>

      <div v-else-if="state === 'done'" class="tb-state-band">
        <button type="button" class="tb-state-btn" :disabled="saving" @click="emit('undo')">
          <span class="tb-state-line">
            <CheckCircleFilled class="tb-state-icon" />
            {{ t('core.taskboard.stateDone') }}
          </span>
          <span class="tb-state-hint">{{ t('core.taskboard.doneUndoHint') }}</span>
        </button>
      </div>
      <div v-else-if="state === 'archived'" class="tb-state-band">
        <span class="tb-state-hint">{{ archivedNote }}</span>
      </div>

      <div v-if="state === 'active'" class="tb-card-actions">
        <a-tag class="tb-status is-bottom">
          <span class="tb-status-dot" aria-hidden="true"></span>
          {{ statusText }}
        </a-tag>
        <a-button
          size="middle"
          type="primary"
          :loading="saving"
          :disabled="!ready"
          @click="emit('complete')"
        >
          {{ t('core.taskboard.complete') }}
        </a-button>
      </div>
    </div>
  </a-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { CheckCircleFilled } from '@ant-design/icons-vue'
import TaskCountdown from './TaskCountdown.vue'
import type { TaskboardActivity } from '@/types/taskboard'

interface Props {
  event: TaskboardActivity
  cover: string
  state: 'active' | 'done' | 'archived' | 'upcoming'
  gameName: string
  archivedNote: string
  endingSoon: boolean
  startText: string
  endText: string
  doneText: string
  progress: number | null
  saving: boolean
  ready: boolean
}

const props = defineProps<Props>()
const emit = defineEmits<{ complete: []; undo: [] }>()
const { t } = useI18n()

const statusText = computed(() => {
  if (props.state === 'done') return t('core.taskboard.stateDone')
  if (props.state === 'archived') return t('core.taskboard.stateEnded')
  if (props.state === 'upcoming') return t('core.taskboard.stateUpcoming')
  return props.endingSoon ? t('core.taskboard.stateEndingSoon') : t('core.taskboard.stateActive')
})

const hideCover = (ev: Event) => {
  const img = ev.target as HTMLImageElement
  img.style.display = 'none'
}
</script>

<style scoped>
.tb-card {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border-color: var(--tb-card-border, var(--ant-color-border-secondary));
  border-radius: var(--tb-card-radius, 10px);
  background: var(--ant-color-bg-container);
  transition:
    border-color 0.15s,
    box-shadow 0.15s,
    transform 0.15s;
}

.tb-card:hover {
  border-color: var(--ant-color-primary-border);
  box-shadow: var(--tb-card-shadow-hover, 0 4px 14px rgb(0 0 0 / 6%));
  transform: translateY(-2px);
}

.tb-card:active {
  box-shadow: var(--tb-card-shadow-active, 0 2px 6px rgb(0 0 0 / 5%));
  transform: translateY(0);
}

.tb-card :deep(.ant-card-body) {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.tb-cover-wrap {
  aspect-ratio: var(--tb-cover-ratio, 2.2);
  background: var(--ant-color-fill-secondary);
}

.tb-cover {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.tb-card-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.tb-card-top {
  display: flex;
  align-items: center;
  gap: 8px;
}

.tb-card-game {
  display: inline-flex;
  align-items: center;
  height: 32px;
  margin: 0;
  padding: 0 12px;
  overflow: hidden;
  border-color: var(--ant-color-border-secondary);
  border-radius: 6px;
  background: var(--tb-tag-bg, var(--ant-color-bg-container));
  color: var(--ant-color-text);
  font-size: 12px;
  font-weight: 500;
  line-height: 30px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tb-card-title {
  display: -webkit-box;
  overflow: hidden;
  color: var(--ant-color-text);
  font-size: 16px;
  font-weight: 600;
  line-height: 1.4;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  line-clamp: 2;
}

.tb-card.done .tb-card-title {
  color: var(--ant-color-text-secondary);
}

.tb-card-desc-wrap {
  display: flex;
  align-items: center;
  min-height: 38px;
}

.tb-card-desc {
  display: -webkit-box;
  width: 100%;
  margin: 0;
  overflow: hidden;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  line-height: 1.6;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  line-clamp: 2;
}

.tb-card-desc.is-placeholder {
  color: var(--ant-color-text-tertiary);
  text-align: left;
}

.tb-card-times {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 12px;
  line-height: 18px;
  white-space: nowrap;
}

.tb-card-time {
  overflow: hidden;
  color: var(--ant-color-text-tertiary);
  text-overflow: ellipsis;
}

.tb-card-done-at {
  color: var(--ant-color-text-secondary);
  font-weight: 600;
}

.tb-progress {
  margin: 0;
  line-height: 1;
}

.tb-progress :deep(.ant-progress-outer) {
  margin: 0;
  padding: 0;
}

.tb-state-band {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 10px 0;
  border-radius: 6px;
  background: var(--ant-color-fill-quaternary);
}

.tb-state-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  width: 100%;
  padding: 0;
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  cursor: pointer;
}

.tb-state-btn:disabled {
  cursor: default;
  opacity: 0.6;
}

.tb-state-btn:focus-visible {
  outline: 2px solid var(--ant-color-primary);
  outline-offset: 2px;
}

.tb-state-line {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--ant-color-primary);
  font-size: 14px;
  font-weight: 600;
}

.tb-state-icon {
  font-size: 16px;
}

.tb-state-hint {
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
  line-height: 18px;
}

.tb-card-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-height: 32px;
  margin-top: auto;
}

.tb-status {
  display: inline-flex;
  flex-shrink: 0;
  align-items: center;
  gap: 6px;
  height: 32px;
  margin: 0 0 0 auto;
  padding: 0 12px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 6px;
  background: var(--tb-tag-bg, var(--ant-color-bg-container));
  color: var(--ant-color-text);
  font-size: 12px;
  line-height: 30px;
}

.tb-status-dot {
  flex-shrink: 0;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--ant-color-primary);
}

.tb-status.is-bottom {
  margin: 0;
}

@media (prefers-reduced-motion: reduce) {
  .tb-card {
    transition: none;
  }

  .tb-card:hover,
  .tb-card:active {
    transform: none;
  }
}
</style>
