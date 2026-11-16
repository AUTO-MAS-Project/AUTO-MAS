<template>
  <div class="tb-toolbar">
    <a-input-search
      :value="keyword"
      :placeholder="t('core.taskboard.searchPlaceholder')"
      allow-clear
      style="max-width: 300px"
      @update:value="emit('update:keyword', $event)"
    />
    <span class="tb-total">{{ t('core.taskboard.total', { p0: total }) }}</span>
  </div>

  <div class="tb-chips">
    <template v-if="options.length">
      <a-tooltip :title="t('core.taskboard.summaryHint')">
        <a-tag
          class="tb-chip"
          :class="{ 'is-selected': filter === undefined }"
          role="button"
          tabindex="0"
          @click="emit('update:filter', undefined)"
          @keydown.enter.prevent="emit('update:filter', undefined)"
          @keydown.space.prevent="emit('update:filter', undefined)"
        >
          <AppstoreOutlined />
          <span>{{ t('core.taskboard.summary') }}</span>
          <span class="tb-chip-dot" aria-hidden="true"></span>
          <span class="tb-chip-count">{{ counts.active }}</span>
        </a-tag>
      </a-tooltip>
      <a-tag
        v-for="option in options"
        :key="option.key"
        class="tb-chip"
        :class="{ 'is-selected': filter === option.key }"
        role="button"
        tabindex="0"
        @click="emit('update:filter', filter === option.key ? undefined : option.key)"
        @keydown.enter.prevent="
          emit('update:filter', filter === option.key ? undefined : option.key)
        "
        @keydown.space.prevent="
          emit('update:filter', filter === option.key ? undefined : option.key)
        "
      >
        <span>{{ option.name }}</span>
        <span class="tb-chip-dot" aria-hidden="true"></span>
        <span class="tb-chip-count">{{ gameCounts[option.key] ?? 0 }}</span>
      </a-tag>
    </template>
    <span v-else class="tb-no-game">{{ t('core.taskboard.noGames') }}</span>
    <a-tooltip :title="t('core.taskboard.editGamesTip')">
      <a-button class="tb-edit-btn" size="large" @click="emit('edit')">
        <template #icon><PlusOutlined /></template>
        {{ t('core.taskboard.editGames') }}
      </a-button>
    </a-tooltip>
  </div>

  <div class="tb-tabs" role="tablist">
    <button
      type="button"
      role="tab"
      class="tb-tab"
      :class="{ 'is-selected': tab === 'active' }"
      :aria-selected="tab === 'active'"
      @click="changeTab('active')"
    >
      <PlayCircleOutlined />
      <span>{{ t('core.taskboard.tabActive') }}</span>
      <span class="tb-tab-count">{{ counts.active }}</span>
    </button>
    <button
      type="button"
      role="tab"
      class="tb-tab"
      :class="{ 'is-selected': tab === 'done' }"
      :aria-selected="tab === 'done'"
      @click="changeTab('done')"
    >
      <TrophyOutlined />
      <span>{{ t('core.taskboard.tabDone') }}</span>
      <span class="tb-tab-count">{{ counts.done }}</span>
    </button>
    <button
      type="button"
      role="tab"
      class="tb-tab"
      :class="{ 'is-selected': tab === 'archived' }"
      :aria-selected="tab === 'archived'"
      @click="changeTab('archived')"
    >
      <InboxOutlined />
      <span>{{ t('core.taskboard.tabArchived') }}</span>
      <span class="tb-tab-count">{{ counts.archived }}</span>
    </button>
    <button
      type="button"
      role="tab"
      class="tb-tab tb-tab-end"
      :class="{ 'is-selected': tab === 'weekly' }"
      :aria-selected="tab === 'weekly'"
      @click="changeTab('weekly')"
    >
      <CalendarOutlined />
      <span>{{ t('core.taskboard.tabWeekly') }}</span>
      <span class="tb-tab-count">{{ counts.weekly }}</span>
    </button>
    <button
      type="button"
      role="tab"
      class="tb-tab"
      :class="{ 'is-selected': tab === 'version' }"
      :aria-selected="tab === 'version'"
      @click="changeTab('version')"
    >
      <BranchesOutlined />
      <span>{{ t('core.taskboard.tabVersion') }}</span>
      <span class="tb-tab-count">{{ counts.version }}</span>
    </button>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import {
  AppstoreOutlined,
  BranchesOutlined,
  CalendarOutlined,
  InboxOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  TrophyOutlined,
} from '@ant-design/icons-vue'
import type { TaskboardGameOption } from '@/types/taskboard'

type TabKey = 'active' | 'done' | 'archived' | 'weekly' | 'version'

defineProps<{
  keyword: string
  total: number
  options: TaskboardGameOption[]
  filter: string | undefined
  counts: { active: number; done: number; archived: number; weekly: number; version: number }
  gameCounts: Record<string, number>
  tab: TabKey
}>()

const emit = defineEmits<{
  'update:keyword': [value: string]
  'update:filter': [value: string | undefined]
  'update:tab': [value: TabKey]
  edit: []
}>()

const { t } = useI18n()

const changeTab = (value: TabKey) => emit('update:tab', value)
</script>

<style scoped>
.tb-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0 4px;
}

.tb-total {
  font-size: 12px;
  color: var(--ant-color-text-secondary);
}

.tb-edit-btn {
  height: 42px;
  padding: 0 18px;
  border: 1px dashed var(--ant-color-border);
  border-radius: 999px;
  background: transparent;
  color: var(--ant-color-text-secondary);
  font-size: 16px;
  box-shadow: none;
}

.tb-chips,
.tb-tabs {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  padding: 0 4px;
}

.tb-chips {
  margin-top: 20px;
}

.tb-tabs {
  margin-top: 20px;
  margin-bottom: 20px;
}

/* 筛选与页签各自是一块独立小卡，和卡片共用同一套表面与描边。 */
.tb-chip,
.tb-tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin: 0;
  padding: 6px 18px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 999px;
  background: var(--app-background-card-bg, var(--ant-color-bg-container));
  color: var(--ant-color-text);
  font-size: 16px;
  line-height: 28px;
  cursor: pointer;
  user-select: none;
  transition:
    transform 0.18s cubic-bezier(0.34, 1.56, 0.64, 1),
    border-color 0.18s ease-out,
    background-color 0.18s ease-out,
    color 0.18s ease-out;
}

.tb-chip:hover,
.tb-tab:hover {
  transform: scale(1.03);
}

.tb-chip:active,
.tb-tab:active {
  transform: scale(0.96);
}

.tb-tab {
  font-family: inherit;
}

.tb-chip:hover,
.tb-tab:hover {
  border-color: var(--ant-color-primary-border);
  color: var(--ant-color-primary);
}

.tb-chip.is-selected,
.tb-tab.is-selected {
  border-color: var(--ant-color-primary);
  background: var(--ant-color-primary);
  color: var(--ant-color-text-light-solid);
  box-shadow: var(--tb-chip-shadow, 0 2px 6px rgb(0 0 0 / 10%));
}

.tb-chip:focus-visible,
.tb-tab:focus-visible {
  outline: 2px solid var(--ant-color-primary);
  outline-offset: 2px;
}

.tb-chip-dot {
  flex-shrink: 0;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--ant-color-primary);
}

.tb-chip.is-selected .tb-chip-dot {
  background: color-mix(in srgb, var(--ant-color-text-light-solid) 80%, transparent);
}

.tb-tab-end {
  margin-left: auto;
}

.tb-chip-count,
.tb-tab-count {
  color: var(--ant-color-text-secondary);
  font-size: 12px;
}

.tb-chip.is-selected .tb-chip-count,
.tb-tab.is-selected .tb-tab-count {
  color: color-mix(in srgb, var(--ant-color-text-light-solid) 80%, transparent);
}

.tb-chip :deep(.anticon) {
  vertical-align: -1px;
}

@media (prefers-reduced-motion: reduce) {
  .tb-chip,
  .tb-tab {
    transition: none;
  }

  .tb-chip:hover,
  .tb-tab:hover,
  .tb-chip:active,
  .tb-tab:active {
    transform: none;
  }
}

.tb-no-game {
  font-size: 14px;
  color: var(--ant-color-text-secondary);
}
</style>
