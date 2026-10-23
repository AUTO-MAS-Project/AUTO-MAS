<template>
  <div class="tb-toolbar">
    <a-input-search
      :value="keyword"
      :placeholder="t('taskboard.searchPlaceholder')"
      allow-clear
      style="max-width: 300px"
      @update:value="emit('update:keyword', $event)"
    />
    <span class="tb-total">{{ t('taskboard.total', { p0: total }) }}</span>
    <a-tooltip :title="t('taskboard.editGamesTip')">
      <a-button class="tb-edit-btn" @click="emit('edit')">
        <template #icon><EditOutlined /></template>
        {{ t('taskboard.editGames') }}
      </a-button>
    </a-tooltip>
  </div>

  <div class="tb-chips">
    <template v-if="options.length">
      <a-tooltip :title="t('taskboard.summaryHint')">
        <a-tag
          class="tb-chip"
          role="button"
          tabindex="0"
          :color="filter === undefined ? 'blue' : undefined"
          @click="emit('update:filter', undefined)"
          @keydown.enter.prevent="emit('update:filter', undefined)"
          @keydown.space.prevent="emit('update:filter', undefined)"
        >
          <AppstoreOutlined />
          {{ t('taskboard.summary') }}
        </a-tag>
      </a-tooltip>
      <a-tag
        v-for="option in options"
        :key="option.key"
        class="tb-chip"
        role="button"
        tabindex="0"
        :color="filter === option.key ? 'blue' : undefined"
        @click="emit('update:filter', filter === option.key ? undefined : option.key)"
        @keydown.enter.prevent="
          emit('update:filter', filter === option.key ? undefined : option.key)
        "
        @keydown.space.prevent="
          emit('update:filter', filter === option.key ? undefined : option.key)
        "
      >
        {{ option.name }}
      </a-tag>
    </template>
    <span v-else class="tb-no-game">{{ t('taskboard.noGames') }}</span>
  </div>

  <a-tabs :active-key="tab" type="card" class="tb-tabs" @change="changeTab">
    <a-tab-pane key="active" :tab="`${t('taskboard.tabActive')} ${counts.active}`" />
    <a-tab-pane key="done" :tab="`${t('taskboard.tabDone')} ${counts.done}`" />
    <a-tab-pane key="archived" :tab="`${t('taskboard.tabArchived')} ${counts.archived}`" />
  </a-tabs>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { AppstoreOutlined, EditOutlined } from '@ant-design/icons-vue'
import type { TaskboardGameOption } from '@/types/taskboard'

type TabKey = 'active' | 'done' | 'archived'

defineProps<{
  keyword: string
  total: number
  options: TaskboardGameOption[]
  filter: string | undefined
  counts: { active: number; done: number; archived: number }
  tab: TabKey
}>()

const emit = defineEmits<{
  'update:keyword': [value: string]
  'update:filter': [value: string | undefined]
  'update:tab': [value: TabKey]
  edit: []
}>()

const { t } = useI18n()

const changeTab = (value: string | number) => emit('update:tab', value as TabKey)
</script>

<style scoped>
.tb-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0 4px 6px;
}

.tb-total {
  font-size: 12px;
  color: var(--ant-color-text-secondary);
}

.tb-edit-btn {
  margin-left: auto;
}

.tb-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 2px 4px 10px;
}

.tb-chip {
  margin: 0;
  cursor: pointer;
  user-select: none;
  font-size: 16px;
  line-height: 28px;
  padding: 5px 15px;
  border-radius: 8px;
}

.tb-chip:focus-visible {
  outline: 2px solid var(--ant-color-primary);
  outline-offset: 2px;
}

.tb-chip :deep(.anticon) {
  margin-right: 5px;
  vertical-align: -1px;
}

.tb-no-game {
  font-size: 14px;
  color: var(--ant-color-text-secondary);
}

.tb-tabs :deep(.ant-tabs-nav) {
  margin: 0 0 14px;
  padding: 0 4px;
}

.tb-tabs :deep(.ant-tabs-nav .ant-tabs-tab.ant-tabs-tab) {
  font-size: 16px;
  padding: 12px 26px;
}

.tb-tabs :deep(.ant-tabs-nav .ant-tabs-tab .ant-tabs-tab-btn) {
  font-size: 16px;
}

.tb-tabs :deep(.ant-tabs-content-holder) {
  display: none;
}
</style>
