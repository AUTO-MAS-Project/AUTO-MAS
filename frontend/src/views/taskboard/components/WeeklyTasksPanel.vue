<template>
  <div class="tb-weekly">
    <div class="tb-weekly-head">
      <div class="tb-weekly-tools">
        <a-button
          :disabled="taskboardState.loading || !taskboardState.loaded"
          @click="editOpen = true"
        >
          <template #icon><EditOutlined /></template>
          {{ t('core.taskboard.weeklyEdit') }}
        </a-button>
        <span class="tb-weekly-hint">{{ t('core.taskboard.weeklyReset') }}</span>
      </div>
    </div>

    <a-spin :spinning="taskboardState.loading" class="tb-weekly-spin">
      <template v-if="options.length">
        <div class="tb-weekly-grid">
          <a-card
            v-for="option in options"
            :key="option.key"
            class="tb-weekly-card"
            :class="{ done: isDone(option.key) }"
            :body-style="{ padding: '10px 12px' }"
            @click="toggle(option.key)"
          >
            <template #cover>
              <div class="tb-weekly-cover">
                <img
                  v-if="option.cover"
                  :src="option.cover"
                  :alt="option.name"
                  loading="lazy"
                  referrerpolicy="no-referrer"
                  @error="hideCover"
                />
                <a-checkbox
                  class="tb-weekly-check"
                  :checked="isDone(option.key)"
                  :disabled="isSaving(option.key)"
                  @click.stop
                  @change="toggle(option.key)"
                />
              </div>
            </template>
            <div class="tb-weekly-body">
              <div class="tb-weekly-name" :title="option.name">{{ option.name }}</div>
              <div class="tb-weekly-hint">{{ t('core.taskboard.weeklyCycle') }}</div>
            </div>
          </a-card>
        </div>
      </template>
      <NoData v-else-if="!taskboardState.loading" :description="t('core.taskboard.weeklyEmpty')" />
    </a-spin>

    <GamePickerModal
      :open="editOpen"
      :title="t('core.taskboard.weeklyEdit')"
      :hint="t('core.taskboard.weeklyEditHint')"
      :show-counts="false"
      :options="allOptions"
      :selected="weeklySelection"
      @update:open="editOpen = $event"
      @save="saveWeekly"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { EditOutlined } from '@ant-design/icons-vue'
import GamePickerModal from './GamePickerModal.vue'
import { useTaskboardStateStore } from '@/stores/taskboardState'
import type { TaskboardGameOption } from '@/types/taskboard'

interface Props {
  options: TaskboardGameOption[]
  allOptions: TaskboardGameOption[]
}

const props = defineProps<Props>()
const { t } = useI18n()
const taskboardState = useTaskboardStateStore()
const editOpen = ref(false)

/* 未单独勾选时跟随任务台游戏选择。 */
const weeklySelection = computed(
  () => taskboardState.weeklyGames ?? props.allOptions.map(option => option.key)
)

const saveWeekly = async (keys: string[]) => {
  const result = await taskboardState.saveWeeklySelection(keys)
  if (result.error) {
    message.error(t('core.taskboard.weeklySaveFailed', { p0: result.error }))
    return
  }
  if (!result.applied) {
    message.warning(t('core.taskboard.weeklySelectionWeekChanged'))
    return
  }
  editOpen.value = false
}

const isDone = (key: string) => taskboardState.isWeeklyDone(key)
const isSaving = (key: string) => taskboardState.weeklySaving.includes(key)

const toggle = async (key: string) => {
  if (isSaving(key)) return
  const result = await taskboardState.saveWeekly(key, !isDone(key))
  if (result.error) message.error(t('core.taskboard.weeklySaveFailed', { p0: result.error }))
  else if (!result.applied) message.warning(t('core.taskboard.weeklyWeekExpired'))
}

const hideCover = (event: Event) => {
  const image = event.target as HTMLImageElement
  image.style.display = 'none'
}
</script>

<style scoped>
.tb-weekly-spin {
  display: block;
  min-height: 120px;
}

.tb-weekly-head {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  flex-wrap: wrap;
  gap: 12px;
  margin: 0 4px 10px;
}

.tb-weekly-hint {
  padding: 5px 14px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 999px;
  background: var(--app-background-card-bg, var(--ant-color-bg-container));
  color: var(--ant-color-text-secondary);
  font-size: 12px;
}

.tb-weekly-tools {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}

.tb-weekly-grid {
  display: grid;
  grid-template-columns: var(--tb-grid, repeat(4, minmax(0, 1fr)));
  gap: var(--tb-gap, 16px);
}

.tb-weekly-card {
  cursor: pointer;
  overflow: hidden;
  border-color: var(--tb-card-border, var(--ant-color-border-secondary));
  border-radius: var(--tb-card-radius, 10px);
  background: var(--ant-color-bg-container);
  transition:
    border-color 0.15s,
    box-shadow 0.15s,
    transform 0.15s;
}

.tb-weekly-card:active {
  transform: translateY(0);
}

.tb-weekly-card:hover {
  border-color: var(--ant-color-primary-border);
  box-shadow: var(--tb-card-shadow-hover, 0 4px 14px rgb(0 0 0 / 6%));
  transform: translateY(-2px);
}

.tb-weekly-cover {
  position: relative;
  aspect-ratio: var(--tb-cover-ratio, 2.2);
  overflow: hidden;
  background: var(--ant-color-fill-secondary);
}

.tb-weekly-cover img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: filter 0.15s;
}

.tb-weekly-card.done .tb-weekly-cover img {
  filter: grayscale(0.7) opacity(0.7);
}

.tb-weekly-check {
  position: absolute;
  top: 8px;
  right: 8px;
  padding: 2px 6px;
  border-radius: 6px;
  background: var(--ant-color-bg-container);
}

.tb-weekly-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.tb-weekly-name {
  font-size: 16px;
  font-weight: 600;
  line-height: 1.4;
  color: var(--ant-color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tb-weekly-card.done .tb-weekly-name {
  color: var(--ant-color-text-secondary);
}
</style>

@media (prefers-reduced-motion: reduce) { .tb-weekly-card, .tb-weekly-cover img { transition: none;
} .tb-weekly-card:hover, .tb-weekly-card:active { transform: none; } }
