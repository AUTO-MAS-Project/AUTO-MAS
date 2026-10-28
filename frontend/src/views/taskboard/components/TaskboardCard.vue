<template>
  <a-card size="small" class="tb-card" :class="{ done: state === 'done', archived }">
    <template #cover>
      <div class="tb-cover-wrap">
        <img
          v-if="event.image_url"
          :src="event.image_url"
          :alt="event.title"
          loading="lazy"
          referrerpolicy="no-referrer"
          class="tb-cover"
          @error="hideCover"
        />
      </div>
    </template>
    <div class="tb-card-body">
      <div v-if="showGame" class="tb-card-game">{{ gameName }}</div>
      <div class="tb-card-head">
        <a-tooltip
          v-if="event.description"
          :title="event.description"
          placement="topLeft"
          :overlay-style="{ maxWidth: '420px' }"
        >
          <span class="tb-card-title">{{ event.title }}</span>
        </a-tooltip>
        <span v-else class="tb-card-title" :title="event.title">{{ event.title }}</span>
        <span v-if="countdown.text" class="tb-countdown" :class="`is-${countdown.tone}`">
          {{ countdown.text }}
        </span>
      </div>
      <div class="tb-card-time">
        <span>{{ t('core.taskboard.startsAt') }} {{ startText }}</span>
        <span>{{ t('core.taskboard.endsAt') }} {{ endText }}</span>
        <span v-if="state === 'done' && doneText" class="tb-card-done">
          {{ t('core.taskboard.doneAt', { p0: doneText }) }}
        </span>
      </div>
      <a-progress
        v-if="state === 'active' && progress !== null"
        :percent="progress ?? 0"
        :show-info="false"
        size="small"
        :stroke-color="progressColor"
        class="tb-progress"
      />
      <div v-if="!archived" class="tb-card-actions">
        <a-button
          v-if="state === 'active'"
          size="small"
          type="primary"
          ghost
          :loading="saving"
          :disabled="!ready"
          @click="emit('complete')"
        >
          {{ t('core.taskboard.complete') }}
        </a-button>
        <a-button v-else-if="state === 'done'" size="small" :loading="saving" @click="emit('undo')">
          {{ t('core.taskboard.undo') }}
        </a-button>
      </div>
    </div>
  </a-card>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { TaskboardActivity } from '@/types/taskboard'

interface Props {
  event: TaskboardActivity
  state: 'active' | 'done' | 'archived' | 'upcoming'
  gameName: string
  showGame: boolean
  archived: boolean
  countdown: { tone: 'muted' | 'normal' | 'urgent'; text: string }
  startText: string
  endText: string
  doneText: string
  progress: number | null
  progressColor: string
  saving: boolean
  ready: boolean
}

defineProps<Props>()
const emit = defineEmits<{ complete: []; undo: [] }>()
const { t } = useI18n()

const hideCover = (ev: Event) => {
  const img = ev.target as HTMLImageElement
  img.style.display = 'none'
}
</script>

<style scoped>
.tb-card {
  display: flex;
  flex-direction: column;
  border-color: var(--ant-color-border-secondary);
  background: var(--ant-color-bg-container);
}

.tb-card :deep(.ant-card-body) {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 12px 16px;
}

.tb-card.done {
  border-color: var(--ant-color-success-border);
}

/* 归档卡片没有按钮和进度条，收紧封面与标题，避免下半截大片留白 */
.tb-card.archived .tb-cover-wrap {
  height: 128px;
}

.tb-card.archived .tb-card-title {
  min-height: 0;
  -webkit-line-clamp: 1;
  line-clamp: 1;
}

.tb-cover-wrap {
  height: 170px;
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

.tb-card-game {
  font-size: 12px;
  color: var(--ant-color-text-secondary);
}

.tb-card-head {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

.tb-card-title {
  flex: 1;
  min-height: 2.8em;
  font-weight: 600;
  font-size: 16px;
  line-height: 1.45;
  color: var(--ant-color-text);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.tb-countdown {
  flex-shrink: 0;
  font-size: 14px;
  line-height: 22px;
}

.tb-countdown.is-urgent {
  color: var(--ant-color-error);
}

.tb-countdown.is-normal {
  color: var(--ant-color-primary);
}

.tb-countdown.is-muted {
  color: var(--ant-color-text-tertiary);
}

.tb-card-time {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 12px;
  color: var(--ant-color-text-secondary);
}

.tb-card-done {
  color: var(--ant-color-success);
}

.tb-progress {
  margin: 0;
  line-height: 1;
}

.tb-progress :deep(.ant-progress-outer) {
  margin: 0;
  padding: 0;
}

.tb-card-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  min-height: 26px;
  margin-top: auto;
}
</style>
